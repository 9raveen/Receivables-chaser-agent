"""
Day 8 — Event log lookups.
Day 9 — MIGRATED from append-only JSONL files to Postgres (Neon). Public
function signatures are UNCHANGED from Day 8 — every caller (stopping.py,
hitl.py, draft_outreach.py, parse_response.py) needed zero changes, since
this module was always the seam between "how state is derived" and "where
it's stored." Only the storage mechanism moved.

Reason for the migration (see chat): a deployed backend on typical free
hosting doesn't guarantee persistent disk across restarts — JSONL files
would silently lose history between judge visits. Postgres (Neon free
tier) fixes that.

IMPORTANT ASYMMETRY, unchanged from Day 8: `disputed` is a plain boolean
field on schema.Invoice itself, not an event type — schema.py has no
DisputeEvent, so get_dispute_status() still reads the CURRENT invoice
record from data/synthetic/demo_batch.json, not a database table. That
file is static reference data (never written to), so it doesn't need to
move to Postgres — the ephemeral-storage risk this migration solves only
applies to things the agent WRITES at runtime.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.agent.db import get_connection
from src.data.schema import ContactAttempt, PaymentEvent, PaymentEventType, PromiseEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"
DEMO_BATCH_PATH = SYNTHETIC_DIR / "demo_batch.json"


# --- writers ---------------------------------------------------------------

def append_payment_event(event: PaymentEvent) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO payment_events
                   (invoice_id, event_type, amount, event_date, source)
                   VALUES (%s, %s, %s, %s, %s)""",
                (event.invoice_id, event.event_type.value, event.amount,
                 event.event_date, event.source.value),
            )
        conn.commit()


def append_promise_event(event: PromiseEvent) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO promise_events
                   (invoice_id, promised_amount, promised_date, made_on,
                    extracted_by, confidence, kept)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (event.invoice_id, event.promised_amount, event.promised_date,
                 event.made_on, event.extracted_by, event.confidence, event.kept),
            )
        conn.commit()


def append_contact_attempt(event: ContactAttempt) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO contact_attempts
                   (invoice_id, attempt_number, channel, tone, sent_at,
                    within_contact_window, response_received)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (event.invoice_id, event.attempt_number, event.channel.value,
                 event.tone.value, event.sent_at, event.within_contact_window,
                 event.response_received),
            )
        conn.commit()


def append_outreach_draft(
    invoice_id: str,
    attempt_number: int,
    subject: str,
    body: str,
    tone: str,
    channel: str,
    sent_at,
    payment_link: Optional[str] = None,
) -> None:
    """
    NOT part of schema.py — ContactAttempt (Day 2) tracks that an attempt
    happened but has no field for the actual message text. Day 8 addition,
    now Postgres-backed.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO outreach_drafts
                   (invoice_id, attempt_number, subject, body, tone, channel,
                    sent_at, payment_link)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (invoice_id, attempt_number, subject, body, tone, channel,
                 sent_at, payment_link),
            )
        conn.commit()


# --- public lookups ----------------------------------------------------------

def get_payment_status(invoice_id: str) -> bool:
    """
    True if this invoice has a FULL_PAYMENT event with no later REVERSAL
    undoing it. PARTIAL_PAYMENT alone does not count.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT event_type FROM payment_events
                   WHERE invoice_id = %s ORDER BY event_date ASC""",
                (invoice_id,),
            )
            rows = cur.fetchall()

    paid = False
    for (event_type,) in rows:
        if event_type == PaymentEventType.FULL_PAYMENT.value:
            paid = True
        elif event_type == PaymentEventType.REVERSAL.value:
            paid = False
    return paid


def get_dispute_status(invoice_id: str) -> bool:
    """Reads the CURRENT invoice record's `disputed` field — see module
    docstring on why this stays file-based, not Postgres."""
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
    field names) for this invoice where kept is still NULL. Returns None
    if there's no unresolved promise.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT invoice_id, promised_amount, promised_date, made_on,
                          extracted_by, confidence, kept
                   FROM promise_events
                   WHERE invoice_id = %s AND kept IS NULL
                   ORDER BY made_on DESC LIMIT 1""",
                (invoice_id,),
            )
            row = cur.fetchone()

    if row is None:
        return None
    return {
        "invoice_id": row[0],
        "promised_amount": row[1],
        "promised_date": row[2].isoformat() if isinstance(row[2], date) else row[2],
        "made_on": row[3].isoformat() if isinstance(row[3], datetime) else row[3],
        "extracted_by": row[4],
        "confidence": row[5],
        "kept": row[6],
    }


def get_broken_promise_streak(invoice_id: str) -> int:
    """
    Counts consecutive BROKEN (kept=False) promises, most recent first,
    stopping at the first promise that was kept (True) or is still
    unresolved (NULL) — or when events run out.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT kept FROM promise_events
                   WHERE invoice_id = %s ORDER BY made_on DESC""",
                (invoice_id,),
            )
            rows = cur.fetchall()

    streak = 0
    for (kept,) in rows:
        if kept is False:
            streak += 1
        else:
            break
    return streak