"""
Day 7 — select_intervention node.

Implements the decision table from agent-policy-spec.md §2 exactly. Only
reached if check_stopping_conditions returned status="active" (proceed) —
the graph's conditional edges enforce this ordering, not this node itself.
"""

from __future__ import annotations

from src.agent.audit_log import write_entry
from src.agent.state import InvoiceState
from src.utils.config import load_policy


def select_intervention(state: InvoiceState) -> InvoiceState:
    policy = load_policy()
    tier = state["risk_tier"]
    ratio = state["overdue_ratio"]
    keep_score = state["promise_keep_score"]

    thresholds = policy["overdue_ratio_thresholds"]

    if tier == "LOW":
        tone, channels = "friendly_reminder", ["email"]
    elif tier == "MEDIUM":
        if ratio > thresholds["medium_firm"]:
            tone, channels = "firm_reminder", ["email"]
        else:
            tone, channels = "friendly_reminder", ["email"]
    else:  # HIGH
        if ratio > thresholds["high_formal"]:
            tone, channels = "formal_notice", ["email", "sms"]
        else:
            tone, channels = "firm_reminder", ["email"]

    # promise-keep adjustment (modest second-order signal — see ADR-0003,
    # this only shortens follow-up cadence, never overrides the primary
    # tier/ratio decision above)
    adjustment_note = ""
    if keep_score is not None and keep_score < policy["promise_keep"]["low_keep_score"]:
        adjustment_note = " (shortened follow-up grace period — low promise-keep score)"

    new_hash = write_entry(
        invoice_id=state["invoice_id"],
        node="select_intervention",
        decision=f"{tone} via {'+'.join(channels)}",
        reason=f"tier={tier}, overdue_ratio={ratio:.3f}{adjustment_note}",
        prev_hash=state["prev_audit_hash"],
    )

    return {
        **state,
        "intervention_tone": tone,
        "intervention_channels": channels,
        "attempt_count": state["attempt_count"] + 1,
        "prev_audit_hash": new_hash,
    }