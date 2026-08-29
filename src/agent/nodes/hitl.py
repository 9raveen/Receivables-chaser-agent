"""
Day 8 — HITL escalation check + handler.

check_hitl_triggers is a conditional-edge function, same pattern as
graph.py's route_after_stopping_check — pure routing logic, no side
effects, reads state that parse_response already set.

Four triggers, per the Day 6 agent-policy-spec.md list:
  1. disputed extraction (ambiguous dispute language)
  2. hostile tone
  3. extraction confidence below threshold
  4. 2+ consecutive broken promises

Trigger thresholds are read from policy.yaml under a "hitl" key with
.get()-based defaults (min_confidence=0.6, broken_promise_streak_threshold=2)
— NOT verified against your actual policy.yaml, since I don't have that
file's source. If policy.yaml doesn't have an "hitl" section yet, these
defaults apply silently; confirm they match your intended thresholds (or
add the section) rather than assuming this file's defaults are correct.
"""

from __future__ import annotations

from typing import Optional

from src.agent.audit_log import write_entry
from src.agent.event_log import get_broken_promise_streak
from src.agent.state import InvoiceState
from src.utils.config import load_policy

DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_BROKEN_PROMISE_STREAK_THRESHOLD = 2


def _identify_trigger(state: InvoiceState) -> Optional[str]:
    policy = load_policy().get("hitl", {})
    min_confidence = policy.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
    streak_threshold = policy.get("broken_promise_streak_threshold", DEFAULT_BROKEN_PROMISE_STREAK_THRESHOLD)

    if state.get("last_extracted_intent") == "dispute":
        return "disputed_extraction"
    if state.get("hostile_tone"):
        return "hostile_tone"
    conf = state.get("extraction_confidence")
    if conf is not None and conf < min_confidence:
        return f"low_extraction_confidence ({conf:.2f} < {min_confidence})"
    streak = get_broken_promise_streak(state["invoice_id"])
    if streak >= streak_threshold:
        return f"broken_promise_streak ({streak} >= {streak_threshold})"
    return None


def check_hitl_triggers(state: InvoiceState) -> str:
    """Conditional edge function — routes to 'escalate' or 'continue'."""
    return "escalate" if _identify_trigger(state) is not None else "continue"


def handle_hitl_escalation(state: InvoiceState) -> InvoiceState:
    trigger = _identify_trigger(state) or "unknown_trigger"
    new_hash = write_entry(
        invoice_id=state["invoice_id"],
        node="handle_hitl_escalation",
        decision="exception_queue",
        reason=f"HITL escalation: {trigger}",
        prev_hash=state["prev_audit_hash"],
    )
    return {
        **state,
        "status": "exception",
        "stop_reason": f"hitl_{trigger}",
        "prev_audit_hash": new_hash,
    }