"""
Day 10 — FastAPI backend.

Wraps the existing LangGraph agent (graph.py) with REST endpoints for the
frontend. Does NOT change any node/graph logic — purely a thin HTTP layer
over what Days 7-9 already built and verified.

The compiled graph + its PostgresSaver checkpointer are created ONCE at
app startup (FastAPI lifespan) and reused across all requests — not
re-created per request, which would mean opening/closing a fresh DB
connection on every single call.

KNOWN SIMPLIFICATION (not solved here, flagged rather than hidden):
/run only cleanly supports invoices that have never been run before. An
invoice that HALTED (not interrupted — e.g. outside_contact_window,
pending_promise) has a completed checkpoint with no pending interrupt;
re-invoking it to "try again once the contact window reopens" isn't
implemented as its own flow yet. For the current demo scope (walking
through a handful of invoices live) this doesn't block anything, but a
real "retry on next window" scheduler is future work, not built here.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.bridge import invoice_to_state
from src.agent.graph import build_graph
from src.data.schema import Invoice

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_BATCH_PATH = PROJECT_ROOT / "data" / "synthetic" / "demo_batch.json"

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

_pool = None
_app_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from langgraph.checkpoint.postgres import PostgresSaver

    global _pool, _app_graph
    _pool = ConnectionPool(
        conninfo=os.environ["DATABASE_URL"],
        max_size=5,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )
    checkpointer = PostgresSaver(_pool)
    checkpointer.setup()
    _app_graph = build_graph(checkpointer)
    yield
    _pool.close()

app = FastAPI(title="Chaser Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: tighten to the real frontend origin once deployed
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_demo_batch() -> list[dict]:
    with open(DEMO_BATCH_PATH) as f:
        return json.load(f)


def _get_invoice_record(invoice_id: str) -> dict:
    for rec in _load_demo_batch():
        if rec["invoice_id"] == invoice_id:
            return rec
    raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")


def _derive_state(invoice_id: str) -> dict:
    """
    Current InvoiceState for this invoice — the real checkpointed state if
    the graph has ever run for it, otherwise a fresh unrun preview
    (computed, not persisted) via invoice_to_state.
    """
    config = {"configurable": {"thread_id": invoice_id}}
    snapshot = _app_graph.get_state(config)

    if snapshot.values:
        state = dict(snapshot.values)
        awaiting_reply = any(getattr(task, "interrupts", None) for task in snapshot.tasks)
        state["_awaiting_reply"] = bool(awaiting_reply)
        state["_has_run"] = True
        return state

    rec = _get_invoice_record(invoice_id)
    inv = Invoice(**rec)
    state = dict(invoice_to_state(inv))
    state["_awaiting_reply"] = False
    state["_has_run"] = False
    return state


class InvoiceSummary(BaseModel):
    invoice_id: str
    customer_id: str
    amount: float
    risk_tier: Optional[str]
    overdue_ratio: Optional[float]
    status: str
    awaiting_reply: bool
    has_run: bool


class RunResponse(BaseModel):
    invoice_id: str
    status: str
    awaiting_reply: bool


class ReplyRequest(BaseModel):
    reply_text: str


class ReplyResponse(BaseModel):
    invoice_id: str
    status: str
    stop_reason: Optional[str]
    last_extracted_intent: Optional[str]
    extraction_confidence: Optional[float]
    promise_keep_score: Optional[float]


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/api/invoices", response_model=list[InvoiceSummary])
def list_invoices():
    summaries = []
    for rec in _load_demo_batch():
        state = _derive_state(rec["invoice_id"])
        summaries.append(InvoiceSummary(
            invoice_id=state["invoice_id"],
            customer_id=state["customer_id"],
            amount=state["amount"],
            risk_tier=state.get("risk_tier"),
            overdue_ratio=state.get("overdue_ratio"),
            status=state["status"],
            awaiting_reply=state["_awaiting_reply"],
            has_run=state["_has_run"],
        ))
    return summaries


@app.get("/api/invoices/{invoice_id}")
def get_invoice_detail(invoice_id: str):
    state = _derive_state(invoice_id)  # 404s via _get_invoice_record if truly unknown

    from src.agent.audit_log import read_all_entries
    from src.agent.bridge import get_invoice_by_id
    from src.agent.db import get_connection
    from src.agent.inference import get_customer_history, get_shap_contributions

    audit_entries = [e for e in read_all_entries() if e["invoice_id"] == invoice_id]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT attempt_number, subject, body, tone, channel, sent_at, payment_link
                   FROM outreach_drafts WHERE invoice_id = %s ORDER BY sent_at ASC""",
                (invoice_id,),
            )
            draft_rows = cur.fetchall()
            cur.execute(
                """SELECT promised_amount, promised_date, made_on, confidence, kept
                   FROM promise_events WHERE invoice_id = %s ORDER BY made_on ASC""",
                (invoice_id,),
            )
            promise_rows = cur.fetchall()

    drafts = [
        {"attempt_number": r[0], "subject": r[1], "body": r[2], "tone": r[3],
         "channel": r[4], "sent_at": r[5].isoformat(), "payment_link": r[6]}
        for r in draft_rows
    ]
    promises = [
        {"promised_amount": r[0], "promised_date": r[1].isoformat(), "made_on": r[2].isoformat(),
         "confidence": r[3], "kept": r[4]}
        for r in promise_rows
    ]

    reasons = []
    try:
        invoice = get_invoice_by_id(invoice_id)
        history_df = get_customer_history(invoice.customer_id, as_of=state["due_date"])
        contributions = get_shap_contributions(invoice, history_df)
        reasons = [f"{feat}: {val:+.3f}" for feat, val in contributions]
    except Exception:
        pass  # non-critical for the detail view — don't fail the whole request over it

    return {
        "state": {k: v for k, v in state.items() if not k.startswith("_")},
        "awaiting_reply": state["_awaiting_reply"],
        "has_run": state["_has_run"],
        "shap_reasons": reasons,
        "audit_trail": audit_entries,
        "outreach_drafts": drafts,
        "promise_history": promises,
    }


@app.post("/api/invoices/{invoice_id}/run", response_model=RunResponse)
def run_invoice(invoice_id: str):
    rec = _get_invoice_record(invoice_id)
    inv = Invoice(**rec)
    config = {"configurable": {"thread_id": invoice_id}}

    snapshot = _app_graph.get_state(config)
    if snapshot.values:
        raise HTTPException(
            status_code=400,
            detail="This invoice has already been run — see the known-simplification note "
                   "in main.py's module docstring. Use /reply if it's awaiting a response.",
        )

    state = invoice_to_state(inv)
    result = _app_graph.invoke(state, config=config)
    awaiting_reply = "__interrupt__" in result
    return RunResponse(invoice_id=invoice_id, status=result["status"], awaiting_reply=awaiting_reply)


@app.post("/api/invoices/{invoice_id}/reply", response_model=ReplyResponse)
def reply_to_invoice(invoice_id: str, body: ReplyRequest):
    from langgraph.types import Command

    config = {"configurable": {"thread_id": invoice_id}}
    snapshot = _app_graph.get_state(config)
    if not snapshot.values or not any(getattr(t, "interrupts", None) for t in snapshot.tasks):
        raise HTTPException(status_code=400, detail="This invoice is not currently awaiting a reply.")

    result = _app_graph.invoke(Command(resume=body.reply_text), config=config)
    return ReplyResponse(
        invoice_id=invoice_id,
        status=result["status"],
        stop_reason=result.get("stop_reason"),
        last_extracted_intent=result.get("last_extracted_intent"),
        extraction_confidence=result.get("extraction_confidence"),
        promise_keep_score=result.get("promise_keep_score"),
    )