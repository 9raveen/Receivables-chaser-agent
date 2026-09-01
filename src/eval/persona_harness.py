"""
Day 10 — Persona eval harness.

5 personas per the Day 6 agent-policy-spec.md: cooperative, evasive,
disputer, serial-promiser, silent. Each runs against the REAL graph (real
Gemini calls, real Postgres, real interrupt/resume) — no mocking. Each
uses a fresh, never-manually-touched demo invoice, so there's no
collision with invoices already exercised during Day 8/9/10 testing.

Two real gaps this harness surfaces and works around, not hides:
  1. "Silent" only works because parse_response.py now special-cases an
     empty reply as "no_response" and loops back for another attempt
     (fixed today, see chat) — previously a silent buyer left the graph
     paused forever with no path to "exhausted".
  2. "Serial-promiser" needs PromiseEvent.kept=False history to trigger
     the broken-promise-streak HITL rule, but nothing in the system
     currently EVALUATES whether a promise was kept once promised_date
     passes (no scheduled job exists for this — real future work, not
     built here). This harness seeds two kept=False PromiseEvents
     directly before running that persona's test, which is honest test
     setup for a real trigger, not a fake pass.

PASS/FAIL philosophy: each persona checks the property that actually
matters for that scenario (e.g. "did NOT hallucinate a firm promise from
vague language"), not an exact-match on model output, since LLM phrasing
varies run to run.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from src.agent.bridge import invoice_to_state
from src.agent.event_log import append_promise_event
from src.agent.graph import build_graph
from src.data.schema import Invoice, PromiseEvent
from src.utils.config import load_policy

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_BATCH_PATH = PROJECT_ROOT / "data" / "synthetic" / "demo_batch.json"

# Reserved, confirmed-untouched invoices (per has_run:false snapshot) —
# one per persona, avoids any collision with manual testing.
PERSONA_INVOICES = {
    "cooperative": "DEMO-0004",
    "evasive": "DEMO-0005",
    "disputer": "DEMO-0006",
    "serial_promiser": "DEMO-0013",  # switched again — DEMO-0011 had a crashed (not cleanly
                                       # completed) run from the earlier quota-exhaustion attempt,
                                       # and re-invoking a CRASHED thread's checkpoint is unverified
                                       # behavior (only cleanly-completed thread re-invoke has been
                                       # confirmed). Using a genuinely untouched invoice sidesteps
                                       # the question entirely rather than guessing at it.
    "silent": "DEMO-0009",
}


def _load_invoice(invoice_id: str) -> Invoice:
    with open(DEMO_BATCH_PATH) as f:
        batch = json.load(f)
    for rec in batch:
        if rec["invoice_id"] == invoice_id:
            return Invoice(**rec)
    raise ValueError(f"{invoice_id} not found in demo_batch.json")


def _reset_invoice_test_state(invoice_id: str) -> None:
    """
    Deletes all event-log rows for this invoice_id before a test runs —
    makes the harness genuinely re-runnable. Without this, a SECOND run
    of the harness reuses the same reserved invoices, inherits whatever
    promise/payment/contact history the FIRST run left behind, and
    produces confusing partial results (exactly what happened to
    `cooperative` above — it halted instantly on a pending promise from
    the prior run, never even reaching parse_response this time).
    Does NOT touch the LangGraph checkpoint tables — doesn't need to:
    re-invoking a completed thread with fresh input starts a new run from
    the entry point regardless of checkpoint history, and none of
    check_stopping_conditions'/hitl.py's decisions read checkpoint state
    directly — they all read event_log, which this DOES reset.
    """
    from src.agent.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            for table in ["audit_log", "payment_events", "promise_events",
                          "contact_attempts", "outreach_drafts"]:
                cur.execute(f"DELETE FROM {table} WHERE invoice_id = %s", (invoice_id,))
        conn.commit()


def _run_and_pause(app, invoice_id: str) -> dict:
    inv = _load_invoice(invoice_id)
    state = invoice_to_state(inv)
    config = {"configurable": {"thread_id": invoice_id}}
    return app.invoke(state, config=config)


def _resume(app, invoice_id: str, reply_text: str) -> dict:
    config = {"configurable": {"thread_id": invoice_id}}
    return app.invoke(Command(resume=reply_text), config=config)


# --- persona test functions --------------------------------------------

def test_cooperative(app) -> dict:
    invoice_id = PERSONA_INVOICES["cooperative"]
    _reset_invoice_test_state(invoice_id)
    _run_and_pause(app, invoice_id)
    result = _resume(app, invoice_id,
        "We sincerely apologize for the delay. We will transfer the full amount by this Friday.")

    passed = (
        result.get("last_extracted_intent") == "promise_to_pay"
        and result.get("promise_keep_score") is not None
        and result["status"] == "active"
        and result.get("stop_reason") == "pending_promise"
    )
    return {
        "persona": "cooperative",
        "passed": passed,
        "criteria": "extracts promise_to_pay, computes promise_keep_score, halts on pending_promise (does not re-contact)",
        "actual": {k: result.get(k) for k in
                   ["status", "stop_reason", "last_extracted_intent", "promise_keep_score"]},
    }


def test_evasive(app) -> dict:
    invoice_id = PERSONA_INVOICES["evasive"]
    _reset_invoice_test_state(invoice_id)
    _run_and_pause(app, invoice_id)
    result = _resume(app, invoice_id,
        "We're looking into some internal issues on our end and will revert to you soon, "
        "can't confirm anything right now.")

    # The property that matters: the agent must NOT hallucinate a firm
    # commitment from vague language. It's fine whether it lands on
    # "unclear"/"request_more_time", or escalates via low confidence —
    # what it must NOT do is log a false promise_to_pay.
    passed = result.get("last_extracted_intent") != "promise_to_pay"
    return {
        "persona": "evasive",
        "passed": passed,
        "criteria": "does NOT hallucinate a firm promise_to_pay from vague/non-committal language",
        "actual": {k: result.get(k) for k in
                   ["status", "stop_reason", "last_extracted_intent", "extraction_confidence"]},
    }


def test_disputer(app) -> dict:
    invoice_id = PERSONA_INVOICES["disputer"]
    _reset_invoice_test_state(invoice_id)
    _run_and_pause(app, invoice_id)
    result = _resume(app, invoice_id,
        "This invoice is incorrect, we never received these goods, and honestly this feels "
        "like harassment at this point.")

    passed = (
        result.get("last_extracted_intent") == "dispute"
        and result["status"] == "exception"
        and (result.get("stop_reason") or "").startswith("hitl_")
    )
    return {
        "persona": "disputer",
        "passed": passed,
        "criteria": "extracts dispute, escalates via HITL (status=exception), does not proceed automatically",
        "actual": {k: result.get(k) for k in
                   ["status", "stop_reason", "last_extracted_intent", "hostile_tone"]},
    }


def test_serial_promiser(app) -> dict:
    invoice_id = PERSONA_INVOICES["serial_promiser"]
    _reset_invoice_test_state(invoice_id)

    # Seed 2 already-broken promises directly — see module docstring on
    # why this is honest test setup, not a fake pass.
    for i in range(2):
        made_on = datetime.now() - timedelta(days=30 - i * 10)
        append_promise_event(PromiseEvent(
            invoice_id=invoice_id,
            promised_amount=100000.0,
            promised_date=(made_on + timedelta(days=5)).date(),
            made_on=made_on,
            extracted_by="agent",
            confidence=0.9,
            kept=False,
        ))

    _run_and_pause(app, invoice_id)
    result = _resume(app, invoice_id, "Yes yes, we will pay by Monday for sure this time.")

    passed = (
        result["status"] == "exception"
        and (result.get("stop_reason") or "").startswith("hitl_broken_promise_streak")
    )
    return {
        "persona": "serial_promiser",
        "passed": passed,
        "criteria": "escalates via broken_promise_streak HITL trigger, regardless of this turn's own promise",
        "actual": {k: result.get(k) for k in ["status", "stop_reason", "last_extracted_intent"]},
    }


def test_silent(app) -> dict:
    invoice_id = PERSONA_INVOICES["silent"]
    _reset_invoice_test_state(invoice_id)
    policy = load_policy()
    max_attempts = policy["stopping_rules"]["max_attempts"]

    _run_and_pause(app, invoice_id)

    result = None
    safety_cap = max_attempts + 3  # a few extra iterations of headroom in case of an off-by-one
    for _ in range(safety_cap):
        result = _resume(app, invoice_id, "")  # empty = no reply received
        if "__interrupt__" not in result:
            break  # reached a terminal state (exhausted), stop looping

    passed = (
        result is not None
        and result["status"] == "exhausted"
        and result.get("stop_reason") == "max_attempts"
    )
    return {
        "persona": "silent",
        "passed": passed,
        "criteria": f"retries up to max_attempts ({max_attempts}) with no reply, then reaches exhausted",
        "actual": {k: (result or {}).get(k) for k in ["status", "stop_reason", "attempt_count"]},
    }


def run_all():
    with PostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as checkpointer:
        checkpointer.setup()
        app = build_graph(checkpointer)

        tests = [test_cooperative, test_evasive, test_disputer, test_serial_promiser, test_silent]
        results = []
        for test_fn in tests:
            print(f"Running: {test_fn.__name__} ...")
            try:
                results.append(test_fn(app))
            except Exception as e:
                results.append({
                    "persona": test_fn.__name__.replace("test_", ""),
                    "passed": False,
                    "criteria": "(crashed before completing)",
                    "actual": {"error": str(e)},
                })

    print()
    print("=" * 70)
    print("PERSONA EVAL RESULTS")
    print("=" * 70)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n[{status}] {r['persona']}")
        print(f"  criteria: {r['criteria']}")
        print(f"  actual:   {r['actual']}")

    n_passed = sum(1 for r in results if r["passed"])
    print()
    print(f"{n_passed}/{len(results)} passed")
    return results


if __name__ == "__main__":
    run_all()