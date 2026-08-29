"""
Day 7 — check_stopping_conditions node.
Day 8 — payment_detected/disputed/pending_promise are now DERIVED from the
real PaymentEvent/PromiseEvent logs and the current invoice record (via
src/agent/event_log.py), closing the gap flagged in handoff §7: these were
previously manual function arguments the caller had to supply, rather than
being read from the append-only logs Day 2's schema design intended.

The compliance-critical gate (agent-policy-spec.md §3). Must run BEFORE
select_intervention on every cycle — that ordering is what makes these
rules actually binding rather than advisory. The LLM (Day 8) never gets a
chance to decide whether to honor a stopping rule; this node decides it in
plain code before the LLM is even invoked.
"""

from __future__ import annotations

from datetime import datetime

from src.agent.audit_log import write_entry
from src.agent.event_log import get_dispute_status, get_payment_status, get_pending_promise
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
    now: datetime | None = None,
) -> InvoiceState:
    now = now or datetime.now()
    policy = load_policy()

    invoice_id = state["invoice_id"]
    payment_detected = get_payment_status(invoice_id)
    disputed = get_dispute_status(invoice_id)
    pending_promise = get_pending_promise(invoice_id) is not None

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