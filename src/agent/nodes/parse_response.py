"""
Day 8 — parse_response node.

Pauses the graph via interrupt() to wait for a real buyer reply — the
genuine async gap this project was built toward (Option A: real
checkpointing over a synchronous demo simulation). Verified against actual
interrupt()/Command/SqliteSaver behavior via a standalone 2-node test graph
BEFORE being wired in here (confirmed: pauses on first invoke, persists to
disk, resumes correctly across a SEPARATE process run with
Command(resume=reply_text)).

interrupt() MUST be the first statement in this function, before any other
side-effecting code (event log writes, LLM calls). LangGraph replays a
node's execution from the top on resume — a cached interrupt() call
returns its resume value immediately without re-pausing, but any code
BEFORE interrupt() would re-execute (and re-fire, e.g. double-writing an
event) on every resume if it existed there. Keeping interrupt() first
means only the post-interrupt work (the actual extraction) ever runs,
exactly once per real reply.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.agent.audit_log import write_entry
from src.agent.bridge import get_invoice_by_id
from src.agent.event_log import append_payment_event, append_promise_event
from src.agent.inference import get_customer_history, score_invoice
from src.agent.llm_utils import call_with_structured_output
from src.agent.state import InvoiceState
from src.data.schema import DataSource, PaymentEvent, PaymentEventType, PromiseEvent


class ExtractedResponse(BaseModel):
    intent: Literal[
        "promise_to_pay", "payment_confirmation", "dispute", "request_more_time", "unclear", "other"
    ]
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    hostile_tone: bool
    promised_amount: Optional[float] = None
    promised_date: Optional[str] = None  # ISO date string, if intent == promise_to_pay
    dispute_reason: Optional[str] = None
    summary: str = Field(description="One short sentence summarizing the reply, for the audit log")


def _build_extraction_prompt(state: InvoiceState, reply_text: str) -> str:
    return f"""You are analyzing a buyer's reply to a B2B accounts-receivable
follow-up message, for invoice {state['invoice_id']} (amount INR {state['amount']:,.2f},
originally due {state['due_date'].isoformat()}).

Today's date is {date.today().isoformat()}.

Buyer's reply:
\"\"\"
{reply_text}
\"\"\"

Classify the reply and extract the following fields:
- intent: one of "promise_to_pay", "payment_confirmation", "dispute", "request_more_time", "unclear", "other"
- extraction_confidence: your own honest confidence (0.0-1.0) in this classification and any extracted
  fields. Use a LOW value if the reply is ambiguous, sarcastic, vague, or hard to parse — do not default
  to a high number just because you produced an answer.
- hostile_tone: true if the reply is hostile, aggressive, or abusive in tone, else false
- promised_amount: a specific payment amount mentioned, else null
- promised_date: a specific future payment date mentioned. RESOLVE any relative date (e.g. "next Friday",
  "in 10 days", "by end of month") to an absolute ISO date (YYYY-MM-DD) using today's date above as the
  reference point — do not leave this null just because the date was stated relatively rather than
  absolutely. Only use null if no future date was mentioned at all.
- dispute_reason: if intent is "dispute", a short plain-language reason for the dispute, else null
- summary: one short, neutral sentence summarizing what the buyer said, for an internal audit log
"""


def parse_response(state: InvoiceState) -> InvoiceState:
    reply_text = interrupt({
        "invoice_id": state["invoice_id"],
        "customer_id": state["customer_id"],
        "attempt_number": state["attempt_count"],
        "request": "awaiting_buyer_reply",
    })

    if not reply_text or not reply_text.strip():
        # No reply received (e.g. a scheduled timeout resuming with an
        # empty string after N days of silence — the "silent" persona
        # case). Skip LLM extraction entirely — there's nothing to
        # extract — log it plainly, and let the normal loop-back to
        # check_stopping_conditions handle it: another outreach attempt
        # if attempts remain, or exhausted once max_attempts is hit. This
        # is what actually gives a genuinely silent buyer a real path to
        # "exhausted" instead of leaving the graph paused forever.
        new_hash = write_entry(
            invoice_id=state["invoice_id"],
            node="parse_response",
            decision="no_response",
            reason="no reply received — will retry per stopping rules",
            prev_hash=state["prev_audit_hash"],
        )
        return {
            **state,
            "last_extracted_intent": "no_response",
            "extraction_confidence": None,
            "hostile_tone": None,
            "prev_audit_hash": new_hash,
        }

    prompt = _build_extraction_prompt(state, reply_text)
    extracted = call_with_structured_output(prompt, ExtractedResponse)

    now = datetime.now()
    new_promise_keep_score = state["promise_keep_score"]

    if extracted.intent == "promise_to_pay" and extracted.promised_date:
        promised_date = date.fromisoformat(extracted.promised_date)
        promise_event = PromiseEvent(
            invoice_id=state["invoice_id"],
            promised_amount=extracted.promised_amount or state["amount"],
            promised_date=promised_date,
            made_on=now,
            extracted_by="agent",
            confidence=extracted.extraction_confidence,
            kept=None,
        )
        append_promise_event(promise_event)

        invoice = get_invoice_by_id(state["invoice_id"])
        history_df = get_customer_history(state["customer_id"], as_of=date.today())
        _, new_promise_keep_score = score_invoice(
            invoice, history_df,
            promise_event={"made_on": now, "promised_date": promised_date},
        )

    elif extracted.intent == "payment_confirmation":
        amount = extracted.promised_amount if extracted.promised_amount is not None else state["amount"]
        is_full = abs(amount - state["amount"]) < 0.01
        payment_event = PaymentEvent(
            invoice_id=state["invoice_id"],
            event_type=PaymentEventType.FULL_PAYMENT if is_full else PaymentEventType.PARTIAL_PAYMENT,
            amount=amount,
            event_date=now.date(),
            source=DataSource.SYNTHETIC,
        )
        append_payment_event(payment_event)

    new_hash = write_entry(
        invoice_id=state["invoice_id"],
        node="parse_response",
        decision=extracted.intent,
        reason=extracted.summary,
        prev_hash=state["prev_audit_hash"],
    )

    return {
        **state,
        "extraction_confidence": extracted.extraction_confidence,
        "hostile_tone": extracted.hostile_tone,
        "last_extracted_intent": extracted.intent,
        "promise_keep_score": new_promise_keep_score,
        "prev_audit_hash": new_hash,
    }