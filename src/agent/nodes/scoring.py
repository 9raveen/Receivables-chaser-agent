"""
Day 7 — score_and_route node.

Entry point of the graph for each cycle. Takes the propensity score
(already computed by the Day 4-5 model, passed in as part of state) and
derives risk_tier + overdue_ratio. Writes one audit log entry.

Deliberately does NOT call the ML model itself — that happens once,
upstream, when the invoice enters the system. This node just routes based
on what's already known, keeping the graph's job "decide and act," not
"also be a feature pipeline."
"""

from __future__ import annotations

from datetime import date

from src.agent.audit_log import write_entry
from src.agent.state import InvoiceState, compute_overdue_ratio, compute_risk_tier


def score_and_route(state: InvoiceState, as_of: date | None = None) -> InvoiceState:
    as_of = as_of or date.today()

    risk_tier = compute_risk_tier(state["propensity_score"])
    overdue_ratio = compute_overdue_ratio(state["due_date"], state["payment_terms_days"], as_of)

    new_hash = write_entry(
        invoice_id=state["invoice_id"],
        node="score_and_route",
        decision=f"risk_tier={risk_tier}",
        reason=f"propensity_score={state['propensity_score']:.3f}, overdue_ratio={overdue_ratio:.3f}",
        prev_hash=state["prev_audit_hash"],
    )

    return {
        **state,
        "risk_tier": risk_tier,
        "overdue_ratio": overdue_ratio,
        "prev_audit_hash": new_hash,
    }