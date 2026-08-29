"""
Day 8 — Inference-time feature pipeline + model scoring.

Bridges the Day 3 batch feature pipeline (built for a full historical
DataFrame at training time) to a single live invoice scored on demand
inside the LangGraph agent.

Built against the CURRENT v1 propensity model, trained on Kaggle data only.
Reuses your actual fitted logic where possible rather than reimplementing
it:
  - `fit_terms_code_encoding` is imported and recomputed once from
    invoices_clean.parquet + temporal_split (pure function of train split,
    not persisted to disk anywhere in build_features.py, so recomputing
    once here — cached module-level — reuses the real logic without
    requiring changes to that file).
  - The trained one-hot column set is reconstructed the same way:
    re-running pd.get_dummies on train_features.parquet's categorical
    columns, matching encode_categoricals()'s exact NUMERIC_COLS +
    dummy-column order. No new files need to be persisted in
    train_baseline.py or build_features.py for this to work.

Known, accepted limitation (v1 model only — tracked for the option-1
retrain, not fixed here): business_code and invoice_currency are unseen
categories for every synthetic India invoice (Kaggle's business_code
values and USD/CAD currency never overlap with India sector names / INR),
so those two dummy groups collapse to all-zero for every DEMO-* invoice.
terms_code_grouped lands in the real, trained "OTHER_RARE" bucket (NET30/
NET60 were never top-10 SAP codes either), non-informative but not zeroed.

promise_keep.py's source has now been confirmed: same xgb.XGBClassifier +
save_model + predict_proba pattern, FEATURE_COLS order matches exactly.
No remaining unverified assumptions in this module.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from src.data.schema import Invoice, MIN_HISTORY_INVOICES

# --- paths ---------------------------------------------------------------
# src/agent/inference.py -> parents[2] is project root, same depth as
# build_features.py's src/features/build_features.py -> parents[2].
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"
INVOICES_CLEAN_PATH = PROCESSED_DIR / "invoices_clean.parquet"

PROPENSITY_MODEL_PATH = MODELS_DIR / "propensity_baseline.json"
PROMISE_KEEP_MODEL_PATH = MODELS_DIR / "promise_keep_model.json"

# Matches train_baseline.py exactly.
CATEGORICAL_COLS = ["business_code", "invoice_currency", "terms_code_grouped"]
NUMERIC_COLS = [
    "amount_log", "payment_terms_days", "terms_code_freq",
    "customer_late_rate_feat", "customer_avg_days_late_feat",
    "cust_n_prior_invoices", "is_cold_start", "amount_vs_customer_avg",
]

# Day 1 EDA: overall Kaggle positive (late) rate. Used ONLY as the
# propensity-model's cold-start fallback for customer_late_rate_feat
# (n_prior == 0) — the real add_expanding_history_features() falls back to
# a business_code-level segment average first, then this same global rate
# as a last resort. True segment-level fallback isn't meaningful here since
# synthetic sectors don't overlap Kaggle's business_code values (the same
# categorical-mismatch issue tracked for the retrain) — falling straight to
# the documented global rate is the closest faithful approximation
# available pre-retrain.
#
# NOT used for the promise-keep model's cold-start fallback — that model
# was trained on a different distribution entirely (the 300-customer
# synthetic pool, Beta(2,5)-generated), so it needs its own pool-mean
# fallback — see _load_promise_keep_pool_mean_late_rate below.
GLOBAL_LATE_RATE_FALLBACK = 0.419


# --- model / encoding loading (cached module-level, loaded once) ---------

_propensity_model: xgb.XGBClassifier | None = None
_promise_keep_model: xgb.XGBClassifier | None = None
_train_dummy_columns: list[str] | None = None
_terms_code_encoding: dict | None = None
_pk_pool_mean_late_rate: float | None = None


def _load_propensity_model() -> xgb.XGBClassifier:
    global _propensity_model
    if _propensity_model is None:
        _propensity_model = xgb.XGBClassifier()
        _propensity_model.load_model(str(PROPENSITY_MODEL_PATH))
    return _propensity_model


def _load_promise_keep_model() -> xgb.XGBClassifier:
    global _promise_keep_model
    if _promise_keep_model is None:
        _promise_keep_model = xgb.XGBClassifier()
        _promise_keep_model.load_model(str(PROMISE_KEEP_MODEL_PATH))
    return _promise_keep_model


def _load_train_dummy_columns() -> list[str]:
    """
    Reconstructs the exact trained one-hot column order by re-running
    pd.get_dummies on train_features.parquet's categorical columns — the
    same operation encode_categoricals() did at training time. No new
    file needs to exist for this; train_features.parquet already does.
    """
    global _train_dummy_columns
    if _train_dummy_columns is None:
        train = pd.read_parquet(PROCESSED_DIR / "train_features.parquet")
        train_dummies = pd.get_dummies(train[CATEGORICAL_COLS], prefix=CATEGORICAL_COLS)
        _train_dummy_columns = list(NUMERIC_COLS) + list(train_dummies.columns)
    return _train_dummy_columns


def _load_terms_code_encoding() -> dict:
    """
    Recomputes fit_terms_code_encoding(train) exactly as build_features.py
    does — imported directly, not reimplemented — against the same train
    split (temporal_split on invoices_clean.parquet). Cached after first
    call. This mirrors real training-time fitting rather than guessing
    the output shape.
    """
    global _terms_code_encoding
    if _terms_code_encoding is None:
        from src.features.build_features import fit_terms_code_encoding, temporal_split

        raw = pd.read_parquet(INVOICES_CLEAN_PATH)
        train, _ = temporal_split(raw)
        _terms_code_encoding = fit_terms_code_encoding(train)
    return _terms_code_encoding


def _load_promise_keep_pool_mean_late_rate() -> float:
    """
    Reconstructs promise_keep.py's `pool_mean_late_rate` fallback exactly:
    the mean late_rate across the same 300-customer synthetic pool
    (seed=123, matching simulate_promises()'s default), excluding
    cold-start customers whose late_rate is None — same computation
    simulate_promises() does in-memory, recomputed here since that value
    isn't persisted anywhere either.
    """
    global _pk_pool_mean_late_rate
    if _pk_pool_mean_late_rate is None:
        from src.adapters.synthetic_adapter import generate_customers
        from src.models.promise_keep import TRAINING_POOL_SIZE

        customers, _ = generate_customers(n=TRAINING_POOL_SIZE, seed=123)
        rates = [c.late_rate for c in customers if c.late_rate is not None]
        _pk_pool_mean_late_rate = sum(rates) / len(rates)
    return _pk_pool_mean_late_rate


# --- customer history ------------------------------------------------------

def get_customer_history(customer_id: str, as_of: date | datetime) -> pd.DataFrame:
    """
    Prior CLOSED invoices for one customer, as of a given date — the
    single-invoice equivalent of the rows an expanding-window calculation
    would already have seen.

    Sources from data/synthetic/history_invoices.json (Day 2 output).
    Swapping in a Razorpay-backed source later (Day 9) means replacing
    this function's body only.

    Returns an empty DataFrame (not None) if the customer has no prior
    history — callers must handle the cold-start case explicitly via
    is_cold_start, not by checking for None.
    """
    history_path = SYNTHETIC_DIR / "history_invoices.json"
    with open(history_path) as f:
        all_history = json.load(f)

    if isinstance(as_of, datetime):
        as_of = as_of.date()

    rows = [
        h for h in all_history
        if h["customer_id"] == customer_id
        and h.get("cleared_date") is not None
        and datetime.fromisoformat(h["cleared_date"]).date() <= as_of
    ]

    if not rows:
        return pd.DataFrame(columns=[
            "invoice_id", "customer_id", "amount", "due_date",
            "cleared_date", "is_late", "days_late",
        ])

    df = pd.DataFrame(rows)
    df["due_date"] = pd.to_datetime(df["due_date"])
    df["cleared_date"] = pd.to_datetime(df["cleared_date"])
    return df


# --- feature construction --------------------------------------------------

def build_single_invoice_features(invoice: Invoice, history_df: pd.DataFrame) -> pd.DataFrame:
    """
    One-row DataFrame matching NUMERIC_COLS + CATEGORICAL_COLS, mirroring
    add_expanding_history_features()'s per-row logic for a single new
    invoice: history_df already IS "everything strictly before this
    invoice" (get_customer_history filters on cleared_date <= as_of), so
    the expanding mean/rate over history_df is exactly the quantity
    shift(1).expanding().mean() would produce for the next row in a full
    sorted batch — no need to call that batch function directly.
    """
    n_prior = len(history_df)
    is_cold_start = n_prior < MIN_HISTORY_INVOICES

    if n_prior == 0:
        customer_late_rate_feat = GLOBAL_LATE_RATE_FALLBACK
        customer_avg_days_late_feat = 0.0
    else:
        n_late = int(history_df["is_late"].sum())
        customer_late_rate_feat = n_late / n_prior
        late_rows = history_df[history_df["is_late"]]
        customer_avg_days_late_feat = (
            float(late_rows["days_late"].mean()) if len(late_rows) else 0.0
        )

    amount = float(invoice.amount)
    amount_log = float(np.log1p(amount))

    if n_prior > 0:
        avg_amount = float(history_df["amount"].mean())
        amount_vs_customer_avg = amount / avg_amount if avg_amount > 0 else 1.0
    else:
        amount_vs_customer_avg = 1.0

    encoding = _load_terms_code_encoding()
    code = invoice.payment_terms_code
    terms_code_grouped = code if code in encoding["top_codes"] else "OTHER_RARE"
    terms_code_freq = encoding["freq_map"].get(code, 0.0)

    row = {
        "amount_log": amount_log,
        "payment_terms_days": invoice.payment_terms_days,
        "terms_code_freq": terms_code_freq,
        "customer_late_rate_feat": customer_late_rate_feat,
        "customer_avg_days_late_feat": customer_avg_days_late_feat,
        "cust_n_prior_invoices": n_prior,
        "is_cold_start": int(is_cold_start),
        "amount_vs_customer_avg": amount_vs_customer_avg,
        # schema.Invoice.business_unit -> raw Kaggle column name
        # "business_code", confirmed via add_expanding_history_features's
        # groupby("business_code").
        "business_code": invoice.business_unit,
        "invoice_currency": invoice.currency,
        "terms_code_grouped": terms_code_grouped,
    }

    return pd.DataFrame([row])


def _encode_for_inference(feature_row: pd.DataFrame) -> pd.DataFrame:
    """
    Mirrors encode_categoricals() exactly: one-hot the categorical columns
    with the same prefix scheme, concat with numeric columns in the same
    order, reindex to the real trained dummy-column set (unseen category
    -> all-zero dummy, same as the test-set reindex at training time).
    """
    train_columns = _load_train_dummy_columns()

    cat_dummies = pd.get_dummies(feature_row[CATEGORICAL_COLS], prefix=CATEGORICAL_COLS)
    encoded = pd.concat(
        [feature_row[NUMERIC_COLS].reset_index(drop=True), cat_dummies.reset_index(drop=True)],
        axis=1,
    )
    encoded = encoded.reindex(columns=train_columns, fill_value=0)
    return encoded


# --- scoring ---------------------------------------------------------------

def score_invoice(
    invoice: Invoice,
    history_df: pd.DataFrame,
    promise_event: dict | None = None,
) -> tuple[float, float | None]:
    """
    Returns (propensity_score, promise_keep_score).

    promise_keep_score is None unless promise_event is provided — the
    model has nothing to score before a promise has actually been
    extracted for this invoice (Day 8's parse_response node).
    """
    feature_row = build_single_invoice_features(invoice, history_df)
    encoded = _encode_for_inference(feature_row)

    model = _load_propensity_model()
    propensity_score = float(model.predict_proba(encoded)[:, 1][0])

    promise_keep_score = None
    if promise_event is not None:
        promise_keep_score = _score_promise_keep(invoice, history_df, promise_event)

    return propensity_score, promise_keep_score


def _score_promise_keep(
    invoice: Invoice, history_df: pd.DataFrame, promise_event: dict
) -> float:
    """
    Feature order matches promise_keep.py's FEATURE_COLS exactly. Cold-start
    fallback for customer_late_rate uses the same 300-customer pool mean
    promise_keep.py itself falls back to (see
    _load_promise_keep_pool_mean_late_rate), not the Kaggle-wide rate used
    for the propensity model — the two models were trained on different
    distributions and need different fallbacks.
    """
    n_prior = len(history_df)
    is_cold_start = n_prior < MIN_HISTORY_INVOICES
    customer_late_rate = (
        _load_promise_keep_pool_mean_late_rate() if n_prior == 0
        else float(history_df["is_late"].sum()) / n_prior
    )

    made_on = promise_event["made_on"]
    made_on = datetime.fromisoformat(made_on) if isinstance(made_on, str) else made_on
    promised_date = promise_event["promised_date"]
    promised_date = (
        datetime.fromisoformat(promised_date) if isinstance(promised_date, str) else promised_date
    )
    if isinstance(promised_date, date) and not isinstance(promised_date, datetime):
        promised_date = datetime.combine(promised_date, datetime.min.time())

    due_date = invoice.due_date
    due_date_dt = due_date if isinstance(due_date, datetime) else datetime.combine(due_date, datetime.min.time())

    days_overdue_at_promise = (made_on - due_date_dt).days
    promise_horizon_days = (promised_date - made_on).days

    row = pd.DataFrame([{
        "amount_log": float(np.log1p(float(invoice.amount))),
        "terms_days": invoice.payment_terms_days,
        "days_overdue_at_promise": days_overdue_at_promise,
        "promise_horizon_days": promise_horizon_days,
        "customer_late_rate": customer_late_rate,
        "customer_n_invoices": n_prior,
        "is_cold_start": int(is_cold_start),
    }])

    model = _load_promise_keep_model()
    return float(model.predict_proba(row)[:, 1][0])