"""
Day 7 — LangGraph state schema.

This is the state object that flows through the graph for a single
invoice. It's a TypedDict (not the Pydantic Invoice from src/data/schema.py)
because LangGraph's state merging expects dict-like state — the Pydantic
schema is still the source of truth for the underlying invoice/customer
data, this just carries the agent's working state derived from it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional, TypedDict

from src.utils.config import load_policy

RiskTier = Literal["LOW", "MEDIUM", "HIGH"]
InvoiceStatus = Literal[
    "active", "promised", "paid", "disputed", "exception", "exhausted", "resolved"
]


class InvoiceState(TypedDict):
    invoice_id: str
    customer_id: str

    amount: float
    payment_terms_days: int
    due_date: date

    propensity_score: float
    risk_tier: Optional[RiskTier]
    overdue_ratio: Optional[float]

    promise_keep_score: Optional[float]   # None if no active promise

    attempt_count: int
    status: InvoiceStatus
    stop_reason: Optional[str]             # set when a stopping rule fires

    intervention_tone: Optional[str]
    intervention_channels: Optional[list[str]]

    # Day 8: set by parse_response, read by the HITL conditional edge.
    extraction_confidence: Optional[float]   # None until a reply has been parsed
    hostile_tone: Optional[bool]
    last_extracted_intent: Optional[str]     # e.g. "promise_to_pay" | "dispute" | "payment_confirmation"

    prev_audit_hash: str                    # for the hash-chained log (Day 7 audit_log.py)


def days_overdue(due_date: date, as_of: date) -> int:
    return max((as_of - due_date).days, 0)


def compute_overdue_ratio(due_date: date, terms_days: int, as_of: date) -> float:
    overdue = days_overdue(due_date, as_of)
    return overdue / max(terms_days, 1)


def compute_risk_tier(propensity_score: float) -> RiskTier:
    policy = load_policy()["risk_tiers"]
    if propensity_score < policy["low_max"]:
        return "LOW"
    if propensity_score < policy["medium_max"]:
        return "MEDIUM"
    return "HIGH"


def make_initial_state(
    invoice_id: str,
    customer_id: str,
    amount: float,
    payment_terms_days: int,
    due_date: date,
    propensity_score: float,
    as_of: Optional[date] = None,
) -> InvoiceState:
    as_of = as_of or date.today()
    return InvoiceState(
        invoice_id=invoice_id,
        customer_id=customer_id,
        amount=amount,
        payment_terms_days=payment_terms_days,
        due_date=due_date,
        propensity_score=propensity_score,
        risk_tier=compute_risk_tier(propensity_score),
        overdue_ratio=compute_overdue_ratio(due_date, payment_terms_days, as_of),
        promise_keep_score=None,
        attempt_count=0,
        status="active",
        stop_reason=None,
        intervention_tone=None,
        intervention_channels=None,
        extraction_confidence=None,
        hostile_tone=None,
        last_extracted_intent=None,
        prev_audit_hash="GENESIS",
    )