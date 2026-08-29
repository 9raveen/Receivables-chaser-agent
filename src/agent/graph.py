"""
Day 7 — graph wiring.
Day 8 — draft_outreach wired in after select_intervention. Graph shape is
now: score_and_route -> check_stopping_conditions -> [conditional] ->
    "proceed" -> select_intervention -> draft_outreach -> END
    "halt"    -> END

select_intervention is still UNREACHABLE unless check_stopping_conditions
returns "active" status (Day 7's proven structural fact, unchanged) — and
by extension draft_outreach is unreachable too, since it only follows
select_intervention. Running this smoke test now makes REAL Gemini calls
for every invoice that reaches draft_outreach (well within free-tier
limits for 5 invoices, but worth knowing before running this repeatedly).

parse_response, the HITL interrupt() node, and the cyclic rewiring for
multi-turn (draft_outreach -> wait for reply -> parse_response -> loop
back) are still Day 8 remaining work, not done here.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agent.nodes.draft_outreach import draft_outreach
from src.agent.nodes.intervention import select_intervention
from src.agent.nodes.scoring import score_and_route
from src.agent.nodes.stopping import check_stopping_conditions
from src.agent.state import InvoiceState


def route_after_stopping_check(state: InvoiceState) -> str:
    """Conditional edge function — this IS the enforcement mechanism.
    check_stopping_conditions has already run and set state['status'];
    this function is what actually prevents select_intervention (and now
    draft_outreach, downstream of it) from being reached when a stopping
    condition fired."""
    if state["status"] == "active":
        return "proceed"
    return "halt"  # resolved / exception / exhausted / hold(active but blocked this cycle)


def build_graph():
    graph = StateGraph(InvoiceState)

    graph.add_node("score_and_route", score_and_route)
    graph.add_node("check_stopping_conditions", check_stopping_conditions)
    graph.add_node("select_intervention", select_intervention)
    graph.add_node("draft_outreach", draft_outreach)

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
    graph.add_edge("draft_outreach", END)

    return graph.compile()


if __name__ == "__main__":
    import json
    from datetime import date, timedelta
    from pathlib import Path

    from src.agent.bridge import invoice_to_state

    demo_batch_path = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_batch.json"
    with open(demo_batch_path) as f:
        demo_batch = json.load(f)

    app = build_graph()

    # 5 hand-picked invoices spanning the risk/overdue spectrum, per the
    # Day 7 milestone ("agent runs on 5 hand-picked test invoices").
    # Day 8: propensity_score now comes from the REAL model (via
    # invoice_to_state -> inference.py), not fabricated — see bridge.py.
    from src.data.schema import Invoice

    sample = demo_batch[:5]

    for rec in sample:
        inv = Invoice(**rec)
        state = invoice_to_state(inv)
        result = app.invoke(state)
        print(f"{result['invoice_id']}: tier={result['risk_tier']}, "
              f"overdue_ratio={result['overdue_ratio']:.2f}, "
              f"status={result['status']}, "
              f"intervention={result.get('intervention_tone')} "
              f"via {result.get('intervention_channels')}")

    # also exercise a stopping-rule path explicitly: max_attempts already hit
    print()
    print("Stopping-rule test (attempt_count already at max):")
    stop_test_invoice = Invoice(
        invoice_id="DEMO-STOP-TEST",
        customer_id="IN-CUST-0001",
        business_unit="Logistics",
        currency="INR",
        amount=50000.0,
        payment_terms_code="NET30",
        payment_terms_days=30,
        invoice_date=date.today() - timedelta(days=70),
        due_date=date.today() - timedelta(days=40),
        posting_date=date.today() - timedelta(days=70),
        cleared_date=None,
        is_open=True,
        days_late=None,
        is_late=None,
        disputed=False,
        source="synthetic",
    )
    state = invoice_to_state(stop_test_invoice)
    state["attempt_count"] = 5  # already at max_attempts
    result = app.invoke(state)
    print(f"{result['invoice_id']}: status={result['status']}, "
          f"stop_reason={result['stop_reason']}, "
          f"intervention={result.get('intervention_tone')}  <- must be None, node unreachable")