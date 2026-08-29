"""
Day 8 — Event log lookups.

Closes the gap noted in handoff §7: check_stopping_conditions previously
took payment_detected/disputed/pending_promise as manual function
arguments, rather than deriving them from the PaymentEvent/PromiseEvent
append-only logs Day 2's schema design intended. Nothing in Days 1-7 ever
wrote one of these logs anywhere — this module is both the writer and the
reader.

Storage: same append-only JSONL pattern as src/agent/audit_log.py
(logs/audit_log.jsonl) — logs/payment_events.jsonl, logs/promise_events.jsonl.
One JSON object per line, gitignored, loaded fully into memory on read
(same known non-production-scale caveat already documented for the audit
log in handoff §7 — fine at hackathon scale).

IMPORTANT ASYMMETRY, not an oversight: `disputed` is a plain boolean field
on schema.Invoice itself, not an event type — schema.py has no
DisputeEvent. So get_dispute_status() can't read from an append-only log
the way payment/promise do; it reads the CURRENT invoice record instead,
sourced from data/synthetic/demo_batch.json for now (same swappable-source
pattern as inference.py's get_customer_history — a Razorpay-backed lookup
later replaces this function's body only).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.data.schema import PaymentEvent, PaymentEventType, PromiseEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / "logs"
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"

PAYMENT_EVENTS_PATH = LOGS_DIR / "payment_events.jsonl"
PROMISE_EVENTS_PATH = LOGS_DIR / "promise_events.jsonl"
DEMO_BATCH_PATH = SYNTHETIC_DIR / "demo_batch.json"


# --- writers ---------------------------------------------------------------

def append_payment_event(event: PaymentEvent) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PAYMENT_EVENTS_PATH, "a") as f:
        f.write(json.dumps(event.model_dump(mode="json")) + "\n")


def append_promise_event(event: PromiseEvent) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROMISE_EVENTS_PATH, "a") as f:
        f.write(json.dumps(event.model_dump(mode="json")) + "\n")


# --- readers (internal) -----------------------------------------------------

def _read_payment_events(invoice_id: str) -> list[dict]:
    if not PAYMENT_EVENTS_PATH.exists():
        return []
    with open(PAYMENT_EVENTS_PATH) as f:
        events = [json.loads(line) for line in f if line.strip()]
    events = [e for e in events if e["invoice_id"] == invoice_id]
    events.sort(key=lambda e: e["event_date"])
    return events


def _read_promise_events(invoice_id: str) -> list[dict]:
    if not PROMISE_EVENTS_PATH.exists():
        return []
    with open(PROMISE_EVENTS_PATH) as f:
        events = [json.loads(line) for line in f if line.strip()]
    events = [e for e in events if e["invoice_id"] == invoice_id]
    events.sort(key=lambda e: e["made_on"])
    return events


# --- public lookups ----------------------------------------------------------

def get_payment_status(invoice_id: str) -> bool:
    """
    True if this invoice has a FULL_PAYMENT event with no later REVERSAL
    undoing it. PARTIAL_PAYMENT alone does not count as payment_detected —
    the stopping rule ("payment detected -> resolved") should only fire on
    a fully resolved invoice, matching the Day 6 spec's intent.
    """
    events = _read_payment_events(invoice_id)
    paid = False
    for e in events:
        if e["event_type"] == PaymentEventType.FULL_PAYMENT.value:
            paid = True
        elif e["event_type"] == PaymentEventType.REVERSAL.value:
            paid = False
    return paid


def get_dispute_status(invoice_id: str) -> bool:
    """
    Reads the CURRENT invoice record's `disputed` field — see module
    docstring on why this isn't log-based like payment/promise. Sourced
    from data/synthetic/demo_batch.json for now.
    """
    if not DEMO_BATCH_PATH.exists():
        return False
    with open(DEMO_BATCH_PATH) as f:
        batch = json.load(f)
    for rec in batch:
        if rec["invoice_id"] == invoice_id:
            return bool(rec.get("disputed", False))
    return False


def get_pending_promise(invoice_id: str) -> Optional[dict]:
    """
    Returns the most recent PromiseEvent (as a dict, matching schema.py's
    field names) for this invoice where kept is still None — i.e. a
    promise has been made and its promised_date hasn't yet been evaluated.
    Returns None if there's no unresolved promise.
    """
    events = _read_promise_events(invoice_id)
    for e in reversed(events):  # most recent first
        if e.get("kept") is None:
            return e
    return None