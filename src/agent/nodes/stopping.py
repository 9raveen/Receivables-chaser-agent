"""
Day 7 — check_stopping_conditions node.

The compliance-critical gate (agent-policy-spec.md §3). Must run BEFORE
select_intervention on every cycle — that ordering is what makes these
rules actually binding rather than advisory. The LLM (Day 8) never gets a
chance to decide whether to honor a stopping rule; this node decides it in
plain code before the LLM is even invoked.

External signals (payment_detected, disputed, pending_promise) are passed
in rather than baked into state, because in the real system they come from
the PaymentEvent / PromiseEvent append-only logs (src/data/schema.py),
not from a single mutable flag on the invoice — exactly the design
decision made in Day 2's schema (state is derived by reading event
history, never trusted from an overwritten field).
"""

from __future__ import annotations

from datetime import datetime

from src.agent.audit_log import write_entry
from src.agent.state import InvoiceState
from src.utils.config import load_policy

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _within_contact_window(now: datetime, policy: dict) -> bool:
    rules = policy["stopping_rules"]
    if WEEKDAY_NAMES[now.weekday()] in rules["no_contact_days"]:
        return False
    if not (rules["contact_window_start_hour"] <= now.hour < rules["contact_window_end_hour"]):
        return False
    return True


def check_stopping_conditions(
    state: InvoiceState,
    payment_detected: bool = False,
    disputed: bool = False,
    pending_promise: bool = False,
    now: datetime | None = None,
) -> InvoiceState:
    now = now or datetime.now()
    policy = load_policy()

    decision: str
    reason: str
    new_status = state["status"]
    stop_reason = None

    if payment_detected:
        decision, reason = "resolved", "payment event detected"
        new_status = "resolved"
    elif disputed:
        decision, reason = "exception_queue", "invoice disputed — immediate stop"
        new_status = "exception"
        stop_reason = "disputed"
    elif state["attempt_count"] >= policy["stopping_rules"]["max_attempts"]:
        decision, reason = "exhausted", f"max_attempts ({policy['stopping_rules']['max_attempts']}) reached"
        new_status = "exhausted"
        stop_reason = "max_attempts"
    elif pending_promise:
        decision, reason = "hold", "promise pending, not yet due — no re-contact"
        stop_reason = "pending_promise"
    elif not _within_contact_window(now, policy):
        decision, reason = "hold", f"outside contact window ({now.isoformat()})"
        stop_reason = "outside_contact_window"
    else:
        decision, reason = "proceed", "no stopping condition triggered"

    new_hash = write_entry(
        invoice_id=state["invoice_id"],
        node="check_stopping_conditions",
        decision=decision,
        reason=reason,
        prev_hash=state["prev_audit_hash"],
    )

    return {
        **state,
        "status": new_status,
        "stop_reason": stop_reason,
        "prev_audit_hash": new_hash,
    }