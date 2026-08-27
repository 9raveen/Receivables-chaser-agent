"""
Day 2 — Synthetic (Faker) India adapter.

Produces two things, both conforming to the same schema as the Kaggle
adapter:
  1. A pool of synthetic India customers, each with a "risk profile" that
     drives a history of CLOSED invoices — so Customer.late_rate/
     avg_days_late are genuinely derived from that customer's simulated
     behavior, not assigned as a random label. Cold-start rule (schema.py)
     applies here too: a customer needs >= MIN_HISTORY_INVOICES before its
     rate is non-None.
  2. The 50+ record LIVE demo batch: currently-open, overdue invoices
     assigned to those customers. This is the batch the agent actually
     runs against in the demo.

payment_terms_code / payment_terms_days are explicit here ("NET30"/30,
"NET60"/60) rather than derived, since we control the generation — unlike
the Kaggle adapter, which had to infer terms from opaque codes.

Risk profile -> behavior mapping (documented, not hidden in magic numbers):
  - Each customer gets a `risk` in [0, 1] drawn from a Beta distribution
    (skewed toward reliable payers, long tail of risky ones — mirrors the
    real Kaggle late-rate distribution shape, not a uniform coin flip).
  - `risk` controls: probability an invoice is late, and if late, the
    magnitude of days_late (higher risk -> both more frequently late and
    later when late).
  - NET60 customers get a small additional lateness bump, reflecting that
    longer terms are often extended to slower-paying relationships in
    practice — a deliberate, named modeling choice, not an artifact.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from faker import Faker

from src.data.schema import Customer, DataSource, Invoice, MIN_HISTORY_INVOICES

fake = Faker("en_IN")

INDIA_SECTORS = [
    "Textiles", "Pharmaceuticals", "IT Services", "Auto Components",
    "FMCG Distribution", "Construction Materials", "Electronics",
    "Agro Processing", "Logistics", "Chemicals",
]

TERMS_OPTIONS = [("NET30", 30), ("NET60", 60)]
TERMS_WEIGHTS = [0.7, 0.3]  # NET30 more common, matches typical India MSME practice

CURRENCY = "INR"


def _make_gstin() -> str:
    """Synthetic GSTIN in the real 15-char format (not a valid checksum,
    format-realistic only): 2-digit state code + 10-char PAN + entity code +
    Z + checksum char."""
    state_code = f"{random.randint(1, 37):02d}"
    pan = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5)) + \
          "".join(random.choices("0123456789", k=4)) + \
          random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    entity_code = str(random.randint(1, 9))
    checksum = random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{state_code}{pan}{entity_code}Z{checksum}"


def _sample_risk() -> float:
    # Beta(2, 5): mean ~0.29, skewed toward reliable payers, long tail of risk
    return random.betavariate(2, 5)


def _sample_days_late(risk: float, terms_days: int) -> int:
    """Given a customer's risk and this invoice's terms, sample days_late.
    Returns 0 or negative (early) for on-time payers, positive for late."""
    net60_bump = 3 if terms_days == 60 else 0
    is_late = random.random() < (risk + 0.05)  # small base lateness floor
    if not is_late:
        return random.randint(-5, 0)  # paid early/on-time
    # late magnitude scales with risk; heavier tail for high-risk customers
    base = random.expovariate(1 / (5 + risk * 25))
    return int(round(base + net60_bump)) + 1  # ensure > 0


def generate_customers(n: int = 40, seed: int = 42) -> tuple[list[Customer], list[Invoice]]:
    """Returns (customers, historical_closed_invoices)."""
    random.seed(seed)
    Faker.seed(seed)

    customers: list[Customer] = []
    history_invoices: list[Invoice] = []

    for i in range(n):
        cust_id = f"IN-CUST-{i+1:04d}"
        risk = _sample_risk()
        segment = random.choice(INDIA_SECTORS)
        # history depth: deliberately span the cold-start boundary so the
        # feature layer's fallback path gets exercised, same as real data
        n_history = random.choice([0, 1, 2, 3, 4, 6, 10, 15, 20])

        closed = []
        for j in range(n_history):
            terms_code, terms_days = random.choices(TERMS_OPTIONS, TERMS_WEIGHTS)[0]
            inv_date = date.today() - timedelta(days=random.randint(60, 720))
            due = inv_date + timedelta(days=terms_days)
            days_late = _sample_days_late(risk, terms_days)
            cleared = due + timedelta(days=days_late)
            if cleared < inv_date:
                cleared = inv_date + timedelta(days=1)

            inv = Invoice(
                invoice_id=f"{cust_id}-H{j+1:03d}",
                customer_id=cust_id,
                business_unit=segment,
                currency=CURRENCY,
                amount=round(random.uniform(15000, 850000), 2),  # INR, realistic B2B range
                payment_terms_code=terms_code,
                payment_terms_days=terms_days,
                invoice_date=inv_date,
                due_date=due,
                posting_date=inv_date,
                cleared_date=cleared,
                is_open=False,
                days_late=max(days_late, 0),
                is_late=days_late > 0,
                disputed=False,
                source=DataSource.SYNTHETIC,
            )
            closed.append(inv)

        history_invoices.extend(closed)

        n_total = n_history
        n_late = sum(1 for inv in closed if inv.is_late)
        cold_start = n_total < MIN_HISTORY_INVOICES
        late_rate = None if cold_start or n_total == 0 else n_late / n_total
        avg_days_late = (
            None if cold_start or n_total == 0
            else (sum(inv.days_late for inv in closed if inv.is_late) / n_late if n_late else 0.0)
        )

        customers.append(
            Customer(
                customer_id=cust_id,
                display_name=fake.company(),
                segment=segment,
                country="IN",
                gstin=_make_gstin(),
                n_invoices_total=n_total,
                n_invoices_late=n_late,
                late_rate=late_rate,
                avg_days_late=avg_days_late,
                promise_keep_rate=None,
            )
        )

    return customers, history_invoices


def generate_demo_batch(customers: list[Customer], n_invoices: int = 55, seed: int = 7) -> list[Invoice]:
    """
    The live demo batch: currently OPEN, overdue invoices assigned across
    the customer pool. This is what the propensity model scores and the
    agent acts on end-to-end in the demo.
    """
    random.seed(seed)
    risk_by_customer = {c.customer_id: (c.late_rate if c.late_rate is not None else 0.3) for c in customers}

    batch = []
    for i in range(n_invoices):
        cust = random.choice(customers)
        terms_code, terms_days = random.choices(TERMS_OPTIONS, TERMS_WEIGHTS)[0]
        # overdue by a random amount, spread across the lifecycle the agent
        # needs to handle: just-due, moderately overdue, seriously overdue
        overdue_days = random.choice(
            [random.randint(1, 10), random.randint(11, 30), random.randint(31, 75)]
        )
        due = date.today() - timedelta(days=overdue_days)
        inv_date = due - timedelta(days=terms_days)

        batch.append(
            Invoice(
                invoice_id=f"DEMO-{i+1:04d}",
                customer_id=cust.customer_id,
                business_unit=cust.segment,
                currency=CURRENCY,
                amount=round(random.uniform(15000, 850000), 2),
                payment_terms_code=terms_code,
                payment_terms_days=terms_days,
                invoice_date=inv_date,
                due_date=due,
                posting_date=inv_date,
                cleared_date=None,
                is_open=True,
                days_late=None,   # censored — still open, per schema guard
                is_late=None,
                disputed=False,
                source=DataSource.SYNTHETIC,
            )
        )
    return batch


if __name__ == "__main__":
    import json
    from pathlib import Path

    customers, history = generate_customers(n=40)
    demo_batch = generate_demo_batch(customers, n_invoices=55)

    n_cold_start = sum(1 for c in customers if c.is_cold_start())
    print(f"Generated {len(customers)} synthetic India customers")
    print(f"  cold-start (<{MIN_HISTORY_INVOICES} invoices): {n_cold_start}")
    print(f"Generated {len(history)} historical closed invoices")
    print(f"Generated {len(demo_batch)} live demo batch invoices (all open)")
    print()

    late_rates = [c.late_rate for c in customers if c.late_rate is not None]
    print(f"Non-cold-start customers: {len(late_rates)}")
    print(f"  mean late_rate: {sum(late_rates)/len(late_rates):.3f}")
    print(f"  (real Kaggle data late rate was 0.419, for comparison)")
    print()

    print("Sample customer:", customers[0].model_dump())
    print()
    print("Sample demo batch invoice:", demo_batch[0].model_dump())

    overdue_buckets = [(date.today() - inv.due_date).days for inv in demo_batch]
    print()
    print(f"Demo batch overdue-days range: {min(overdue_buckets)}–{max(overdue_buckets)}")

    # persist for Day 3+
    out_dir = Path(__file__).resolve().parents[2] / "data" / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _dump(objs, path):
        with open(path, "w") as f:
            json.dump([o.model_dump(mode="json") for o in objs], f, indent=2, default=str)

    _dump(customers, out_dir / "customers.json")
    _dump(history, out_dir / "history_invoices.json")
    _dump(demo_batch, out_dir / "demo_batch.json")
    print()
    print(f"Saved -> {out_dir}/customers.json, history_invoices.json, demo_batch.json")