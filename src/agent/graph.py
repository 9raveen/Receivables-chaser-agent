"""
Day 7 — graph wiring.
Day 8 — draft_outreach, parse_response, and the HITL escalation path wired
in. The graph is now genuinely cyclic: parse_response's "continue" branch
loops back to check_stopping_conditions, matching an invoice's real
lifecycle across multiple contact attempts.

BUG FIX (discovered by building this loop, not present as a symptom
before): route_after_stopping_check previously only checked
state["status"] == "active" to decide "proceed" vs "halt". But
stopping.py's two "hold" branches (pending_promise,
outside_contact_window) leave status as "active" — they only set
stop_reason. With no loop, this was silently wrong but never observed.
With a real loop, it would have caused re-contacting a customer
immediately after they made a promise, contradicting the whole point of
that stopping rule. Fixed below by also requiring stop_reason is None.

Full shape:
  score_and_route -> check_stopping_conditions -> [conditional] ->
      "halt"    -> END
      "proceed" -> select_intervention -> draft_outreach -> parse_response
                                                                 |
                                                    (interrupt() fires here —
                                                     graph pauses, checkpointed
                                                     to disk, resumes via a
                                                     SEPARATE invocation with
                                                     Command(resume=reply_text) —
                                                     verified against actual
                                                     SqliteSaver behavior via
                                                     scratch_interrupt_test.py
                                                     before being wired in here)
                                                                 |
                                                [conditional: check_hitl_triggers]
                                                    "escalate" -> handle_hitl_escalation -> END
                                                    "continue" -> check_stopping_conditions (LOOP)

Requires a checkpointer to actually pause/resume — build_graph() takes one
as a parameter rather than constructing it internally, since SqliteSaver
needs to be used as a context manager (connection lifetime is the
caller's responsibility, not this module's).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agent.nodes.draft_outreach import draft_outreach
from src.agent.nodes.hitl import check_hitl_triggers, handle_hitl_escalation
from src.agent.nodes.intervention import select_intervention
from src.agent.nodes.parse_response import parse_response
from src.agent.nodes.scoring import score_and_route
from src.agent.nodes.stopping import check_stopping_conditions
from src.agent.state import InvoiceState


def route_after_stopping_check(state: InvoiceState) -> str:
    """Conditional edge function — this IS the enforcement mechanism.
    FIXED (Day 8): now also requires stop_reason is None, not just
    status == "active" — see module docstring. Without this, a "hold"
    decision (pending_promise / outside_contact_window) would incorrectly
    proceed to select_intervention, since those branches leave status
    unchanged at "active" and only set stop_reason."""
    if state["status"] == "active" and state["stop_reason"] is None:
        return "proceed"
    return "halt"


def build_graph(checkpointer):
    graph = StateGraph(InvoiceState)

    graph.add_node("score_and_route", score_and_route)
    graph.add_node("check_stopping_conditions", check_stopping_conditions)
    graph.add_node("select_intervention", select_intervention)
    graph.add_node("draft_outreach", draft_outreach)
    graph.add_node("parse_response", parse_response)
    graph.add_node("handle_hitl_escalation", handle_hitl_escalation)

    graph.set_entry_point("score_and_route")
    graph.add_edge("score_and_route", "check_stopping_conditions")

    graph.add_conditional_edges(
        "check_stopping_conditions",
        route_after_stopping_check,
        {
            "proceed": "select_intervention",
            "halt": END,
        },
    )
    graph.add_edge("select_intervention", "draft_outreach")
    graph.add_edge("draft_outreach", "parse_response")

    graph.add_conditional_edges(
        "parse_response",
        check_hitl_triggers,
        {
            "escalate": "handle_hitl_escalation",
            "continue": "check_stopping_conditions",  # the real cycle
        },
    )
    graph.add_edge("handle_hitl_escalation", END)

    return graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    import json
    from pathlib import Path

    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.types import Command

    from src.agent.bridge import invoice_to_state
    from src.data.schema import Invoice

    demo_batch_path = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_batch.json"
    with open(demo_batch_path) as f:
        demo_batch = json.load(f)

    import os

    from dotenv import load_dotenv
    load_dotenv()

    # DEMO-0003 — same test invoice used throughout, real history (n_prior: 15)
    inv = Invoice(**demo_batch[2])
    state = invoice_to_state(inv)
    config = {"configurable": {"thread_id": inv.invoice_id}}

    # NOTE: both invokes below run in the SAME process for convenience —
    # this test validates the real node logic (extraction, HITL routing,
    # promise scoring, the stopping-rule bug fix), not persistence across a
    # process restart. That mechanic was already verified separately via
    # scratch_interrupt_test.py's two-separate-`python`-invocations test
    # (against SqliteSaver — Postgres uses the identical interrupt/resume
    # API, per LangGraph's own docs, so that verification still applies).
    with PostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as checkpointer:
        checkpointer.setup()  # only needs to actually create tables once; safe to call every run
        app = build_graph(checkpointer)

        print("=== First invoke: score -> ... -> draft_outreach -> pause at parse_response ===")
        result = app.invoke(state, config=config)
        print(f"status={result['status']}, has __interrupt__: {'__interrupt__' in result}")

        print()
        print("=== Second invoke: buyer replies with a promise to pay ===")
        reply_text = "We will pay the full amount by next Friday, apologies for the delay."
        result2 = app.invoke(Command(resume=reply_text), config=config)
        print(f"status={result2['status']}, stop_reason={result2.get('stop_reason')}, "
              f"intent={result2.get('last_extracted_intent')}, "
              f"confidence={result2.get('extraction_confidence')}, "
              f"promise_keep_score={result2.get('promise_keep_score')}")
        print("(expect status=active, stop_reason=pending_promise — the bug-fix branch — "
              "since check_stopping_conditions should now correctly HALT after a promise, "
              "not loop back into another outreach)")