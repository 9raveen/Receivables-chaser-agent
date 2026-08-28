"""
Day 7 — graph wiring.

Builds the actual LangGraph StateGraph. The key structural fact this file
proves: select_intervention is UNREACHABLE unless check_stopping_conditions
returns "active" status. That's not a convention followed by the node
functions — it's enforced by the graph's conditional edge routing, which
is exactly the point of using LangGraph over a plain prompt-driven loop
(ADR-0004).

Day 7 stops here — draft_outreach, parse_response, and the HITL
interrupt() node are Day 8, once real Claude calls are wired in.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agent.nodes.intervention import select_intervention
from src.agent.nodes.scoring import score_and_route
from src.agent.nodes.stopping import check_stopping_conditions
from src.agent.state import InvoiceState


def route_after_stopping_check(state: InvoiceState) -> str:
    """Conditional edge function — this IS the enforcement mechanism.
    check_stopping_conditions has already run and set state['status'];
    this function is what actually prevents select_intervention from
    being reached when a stopping condition fired."""
    if state["status"] == "active":
        return "proceed"
    return "halt"  # resolved / exception / exhausted / hold(active but blocked this cycle)


def build_graph():
    graph = StateGraph(InvoiceState)

    graph.add_node("score_and_route", score_and_route)
    graph.add_node("check_stopping_conditions", check_stopping_conditions)
    graph.add_node("select_intervention", select_intervention)

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
    graph.add_edge("select_intervention", END)

    return graph.compile()


if __name__ == "__main__":
    import json
    from datetime import date, timedelta
    from pathlib import Path

    from src.agent.state import make_initial_state

    demo_batch_path = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_batch.json"
    with open(demo_batch_path) as f:
        demo_batch = json.load(f)

    app = build_graph()

    # 5 hand-picked invoices spanning the risk/overdue spectrum, per the
    # Day 7 milestone ("agent runs on 5 hand-picked test invoices")
    sample = demo_batch[:5]

    # fabricate a propensity score per invoice for this smoke test (real
    # scoring pipeline wiring happens once the trained model + feature
    # pipeline are connected to live invoices — separate integration step)
    fabricated_scores = [0.15, 0.45, 0.55, 0.72, 0.90]

    for inv, score in zip(sample, fabricated_scores):
        state = make_initial_state(
            invoice_id=inv["invoice_id"],
            customer_id=inv["customer_id"],
            amount=inv["amount"],
            payment_terms_days=inv["payment_terms_days"],
            due_date=date.fromisoformat(inv["due_date"]),
            propensity_score=score,
        )
        result = app.invoke(state)
        print(f"{result['invoice_id']}: tier={result['risk_tier']}, "
              f"overdue_ratio={result['overdue_ratio']:.2f}, "
              f"status={result['status']}, "
              f"intervention={result.get('intervention_tone')} "
              f"via {result.get('intervention_channels')}")

    # also exercise a stopping-rule path explicitly: max_attempts already hit
    print()
    print("Stopping-rule test (attempt_count already at max):")
    state = make_initial_state(
        invoice_id="DEMO-STOP-TEST",
        customer_id="IN-CUST-0001",
        amount=50000.0,
        payment_terms_days=30,
        due_date=date.today() - timedelta(days=40),
        propensity_score=0.8,
    )
    state["attempt_count"] = 5  # already at max_attempts
    result = app.invoke(state)
    print(f"{result['invoice_id']}: status={result['status']}, "
          f"stop_reason={result['stop_reason']}, "
          f"intervention={result.get('intervention_tone')}  <- must be None, node unreachable")