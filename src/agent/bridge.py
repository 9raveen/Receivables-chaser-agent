"""
Day 8 — schema.Invoice -> InvoiceState bridge.

Closes the gap noted in the handoff §7/§8: previously InvoiceState was
only ever hand-constructed via make_initial_state() with individually
passed arguments in a test script. This is the real conversion function —
takes a schema.Invoice (the Pydantic source-of-truth object an adapter
produces) and returns a fully-scored InvoiceState ready to enter the graph.

Thin by design: all the real work (feature construction, encoding,
scoring) already lives in inference.py. This module's only job is wiring
Invoice -> real propensity_score -> make_initial_state().
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from src.agent.inference import get_customer_history, score_invoice
from src.agent.state import InvoiceState, make_initial_state
from src.data.schema import Invoice

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_BATCH_PATH = PROJECT_ROOT / "data" / "synthetic" / "demo_batch.json"


def get_invoice_by_id(invoice_id: str) -> Invoice:
    """
    Re-fetches a full schema.Invoice by ID from the current invoice source
    (data/synthetic/demo_batch.json for now — same swappable-source pattern
    as inference.py's get_customer_history / event_log.py's
    get_dispute_status, a Razorpay-backed lookup later replaces this
    function's body only).

    Needed because InvoiceState (the TypedDict that flows through the
    graph) only carries a subset of Invoice's fields — nodes that need the
    full object (e.g. draft_outreach.py, for SHAP explanation which needs
    business_unit/currency/payment_terms_code) have to look it up again by
    invoice_id rather than trust state to carry everything.

    Raises ValueError if the invoice_id isn't found — deliberately loud
    rather than returning None, since a node calling this expects the
    invoice to exist (it already has an invoice_id from state).
    """
    with open(DEMO_BATCH_PATH) as f:
        batch = json.load(f)
    for rec in batch:
        if rec["invoice_id"] == invoice_id:
            return Invoice(**rec)
    raise ValueError(f"Invoice {invoice_id} not found in {DEMO_BATCH_PATH}")


def invoice_to_state(invoice: Invoice, as_of: Optional[date] = None) -> InvoiceState:
    """
    Converts a schema.Invoice into an InvoiceState with a REAL propensity
    score (not fabricated, unlike the Day 7 smoke test).

    as_of defaults to today — NOT the invoice's own due_date. Customer
    history and overdue_ratio should both be computed "as of now", matching
    make_initial_state()'s own default. (Earlier ad hoc testing used
    as_of=invoice.due_date, which happened not to matter for invoices whose
    history was already long-closed before their due date, but is wrong in
    general — fixed here.)

    promise_keep_score is intentionally left untouched: make_initial_state()
    always sets it to None, correctly, since a freshly-scored invoice has
    no promise on it yet. It only gets populated later, once Day 8's
    parse_response node extracts one from a buyer reply.
    """
    as_of = as_of or date.today()

    history_df = get_customer_history(invoice.customer_id, as_of=as_of)
    propensity_score, _ = score_invoice(invoice, history_df)

    return make_initial_state(
        invoice_id=invoice.invoice_id,
        customer_id=invoice.customer_id,
        amount=invoice.amount,
        payment_terms_days=invoice.payment_terms_days,
        due_date=invoice.due_date,
        propensity_score=propensity_score,
        as_of=as_of,
    )