"""
Day 5, part 2 — Promise-keep prediction model.

DATA PROVENANCE (read this before trusting the numbers below):
No real promise-to-pay data exists anywhere at this point in the build.
The Kaggle dataset has no promise concept at all. Razorpay promise data
only starts existing once the agent (Day 7-8) begins extracting promises
from real buyer replies. So this model is trained entirely on SIMULATED
promise outcomes, generated from the synthetic India customers' risk
profiles (src/adapters/synthetic_adapter.py) — same reasoning as ADR-0001's
"no public real dataset exists" argument, extended one level further.

This is a legitimate second-order signal to build (a customer's promise-
keeping tendency is a distinct, useful thing to model separately from raw
lateness), but it should be described in the pitch as a simulated-training
scaffold, not presented as learned from real promise data. See ADR-0003.

Simulation logic:
  - A promise is only simulated for invoices that were actually LATE — a
    promise-to-pay scenario only exists once an invoice is overdue and
    being chased.
  - made_on = due_date + a few days (agent contacts customer once overdue)
  - promised_date = made_on + a promise horizon (customer commits to a
    future date)
  - kept = 1 if the invoice's actual clear_date <= promised_date, else 0
    (this falls naturally out of each customer's already-simulated risk
    profile — a reliable customer's clear_date tends to land before
    whatever they promised, an unreliable one's doesn't)
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

from src.adapters.synthetic_adapter import generate_customers
from src.data.schema import MIN_HISTORY_INVOICES

MODELS_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "models"

TRAINING_POOL_SIZE = 300  # larger than the 40-customer demo pool — this pool
                            # exists purely to generate enough simulated
                            # promises to train on, never shown in the demo


def simulate_promises(seed: int = 123) -> pd.DataFrame:
    customers, history = generate_customers(n=TRAINING_POOL_SIZE, seed=seed)
    cust_by_id = {c.customer_id: c for c in customers}

    random.seed(seed)
    rows = []
    for inv in history:
        if not inv.is_late:
            continue  # only late invoices get chased -> promised

        cust = cust_by_id[inv.customer_id]
        made_on = inv.due_date + pd.Timedelta(days=random.randint(1, 10))
        horizon = random.randint(3, 20)
        promised_date = made_on + pd.Timedelta(days=horizon)
        kept = int(inv.cleared_date <= promised_date)

        rows.append({
            "customer_id": inv.customer_id,
            "invoice_id": inv.invoice_id,
            "amount_log": np.log1p(inv.amount),
            "terms_days": inv.payment_terms_days,
            "days_overdue_at_promise": (made_on - inv.due_date).days,
            "promise_horizon_days": horizon,
            "customer_late_rate": cust.late_rate if cust.late_rate is not None else np.nan,
            "customer_n_invoices": cust.n_invoices_total,
            "is_cold_start": int(cust.is_cold_start()),
            "kept": kept,
        })

    df = pd.DataFrame(rows)
    # cold-start fallback for customer_late_rate: use pool-wide mean, same
    # pattern as the main feature pipeline (Day 3)
    pool_mean_late_rate = df["customer_late_rate"].mean()
    df["customer_late_rate"] = df["customer_late_rate"].fillna(pool_mean_late_rate)
    return df


FEATURE_COLS = [
    "amount_log", "terms_days", "days_overdue_at_promise",
    "promise_horizon_days", "customer_late_rate", "customer_n_invoices", "is_cold_start",
]
LABEL_COL = "kept"


def run():
    df = simulate_promises()
    print(f"Simulated {len(df)} promise events from {TRAINING_POOL_SIZE} synthetic customers")
    print(f"Kept rate: {df[LABEL_COL].mean():.4f}")

    X = df[FEATURE_COLS]
    y = df[LABEL_COL]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = xgb.XGBClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.1,
        eval_metric="aucpr", random_state=42, n_jobs=-1,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict_proba(X_test)[:, 1]

    aucpr = average_precision_score(y_test, y_pred)
    aucroc = roc_auc_score(y_test, y_pred)

    # naive heuristic: always predict the base rate (no per-invoice signal)
    naive_pred = np.full_like(y_pred, y_train.mean())
    naive_aucpr = average_precision_score(y_test, naive_pred)

    print()
    print(f"Test set size: {len(y_test)}")
    print(f"Model AUC-PR:  {aucpr:.4f}")
    print(f"Model AUC-ROC: {aucroc:.4f}")
    print(f"Naive (base-rate) AUC-PR: {naive_aucpr:.4f}")
    print(f"Lift over naive: {(aucpr - naive_aucpr) / naive_aucpr * 100:+.1f}%")

    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print()
    print("Feature importance:")
    print(importances)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(MODELS_DIR / "promise_keep_model.json")
    print()
    print(f"Model saved -> {MODELS_DIR / 'promise_keep_model.json'}")
    print()
    print("REMINDER: trained on SIMULATED promise data — see module docstring / ADR-0003 "
          "before citing these numbers as if from real promise history.")


if __name__ == "__main__":
    run()