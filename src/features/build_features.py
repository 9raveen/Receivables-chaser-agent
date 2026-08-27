"""
Day 3 — EDA + Feature Engineering.

Operates on the Kaggle data (data/processed/invoices_clean.parquet) since
that's what trains the propensity model. The synthetic layer feeds the
agent later, not model training.

Leakage safeguards (the reason this file exists rather than just reusing
Customer.late_rate from the Day 2 adapter):

  1. TEMPORAL SPLIT, not random. Train on earlier invoices, test on later
     ones, split by invoice_date so no future information reaches training.

  2. CUSTOMER-HISTORY FEATURES ARE EXPANDING, NOT GLOBAL. The Day 2 adapter's
     Customer.late_rate is computed over a customer's ENTIRE history — using
     it as a per-invoice feature would leak future outcomes into earlier
     invoices. Here, each invoice only sees that customer's invoices strictly
     BEFORE it (sorted by invoice_date, shift(1) before aggregating).

  3. COLD START (schema.py's MIN_HISTORY_INVOICES rule) is re-applied at the
     expanding-window level: if a customer has fewer than MIN_HISTORY_INVOICES
     prior invoices as-of the current one, fall back to a segment-level
     (business_code) expanding average instead of a noisy small-sample rate.

  4. cust_payment_terms FREQUENCY ENCODING is fit on the TRAIN split only,
     then applied to test — the standard leakage-safe way to encode a
     categorical whose distribution the model shouldn't learn from test data.

  5. payment_terms_days (median due-invoice gap per code) is the one
     exception fit on the full dataset — it doesn't use the label or any
     future outcome, only invoice/due date pairs, so it's a business-term
     definition, not a leakage-prone statistic. Rare codes get more stable
     estimates this way.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.schema import MIN_HISTORY_INVOICES

PROCESSED_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "invoices_clean.parquet"
FEATURES_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

TOP_N_TERMS_CODES = 10

# Explicit date-based split (NOT a fraction-based cutoff). Data exploration
# revealed a hard censoring cliff: isOpen rate is ~0% for every due_in_date
# month through Jan 2020, then jumps to 67% in March 2020 and ~100% by May
# 2020 — this is a sharp boundary (likely the dataset's extraction date),
# not a gradual effect. A fraction-based split ignored this and produced a
# test set that was 76% censored with a biased-low positive rate (0.377 vs
# 0.420 train). These explicit dates were chosen by checking test-set size,
# closed-rate, and positive-rate balance across several candidates — see
# ADR-0002.
TRAIN_END = "2019-10-01"     # exclusive: train = due_in_date < this
TEST_START = "2019-10-01"    # inclusive
TEST_END = "2020-02-29"      # inclusive: stays safely before the cliff


def temporal_split(df: pd.DataFrame, date_col: str = "due_in_date") -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df[date_col] < TRAIN_END].copy()
    test = df[(df[date_col] >= TEST_START) & (df[date_col] <= TEST_END)].copy()
    return train, test


# ---------------------------------------------------------------------------
# Step 2: payment_terms_days (full-dataset, label-free — see docstring point 5)
# ---------------------------------------------------------------------------

def add_payment_terms_days(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    implied_days = (df["due_in_date"] - df["document_create_date"]).dt.days
    per_code_median = implied_days.groupby(df["cust_payment_terms"]).transform("median")
    global_median = implied_days.median()
    per_code_median = per_code_median.where(per_code_median > 0, global_median)
    df["payment_terms_days"] = per_code_median.round().astype(int)
    return df


# ---------------------------------------------------------------------------
# Step 3: expanding (leakage-safe) customer + segment history features
# ---------------------------------------------------------------------------

def add_expanding_history_features(df: pd.DataFrame, date_col: str = "document_create_date") -> pd.DataFrame:
    """
    Must be called on the FULL (train+test) frame, sorted by date, so that
    test-set expanding features correctly see train-set history as "past" —
    this is not leakage, since real-world deployment also has full past
    history available at inference time. What's forbidden is a test-set
    invoice's own future being visible to itself or to earlier invoices.
    """
    df = df.sort_values(date_col).reset_index(drop=True).copy()

    # only closed invoices carry a known is_late outcome that can inform
    # future expanding stats; open invoices are excluded from the running
    # aggregation (nothing to learn from an unresolved outcome), but they
    # still receive a feature value based on history before them.
    df["_late_for_expansion"] = df["is_late"].where(df["isOpen"] == 0)
    df["_days_late_for_expansion"] = df["days_late"].where((df["isOpen"] == 0) & (df["is_late"] == 1))

    # --- customer-level expanding stats, shifted so current row excluded ---
    grp_cust = df.groupby("cust_number")
    df["cust_n_prior_invoices"] = grp_cust.cumcount()
    df["cust_expanding_late_rate"] = (
        grp_cust["_late_for_expansion"].apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=0, drop=True)
    )
    df["cust_expanding_avg_days_late"] = (
        grp_cust["_days_late_for_expansion"].apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=0, drop=True)
    )
    df["cust_expanding_avg_amount"] = (
        grp_cust["total_open_amount"].apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=0, drop=True)
    )

    # --- segment (business_code) expanding stats — cold-start fallback ---
    grp_seg = df.groupby("business_code")
    df["segment_expanding_late_rate"] = (
        grp_seg["_late_for_expansion"].apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=0, drop=True)
    )
    df["segment_expanding_avg_days_late"] = (
        grp_seg["_days_late_for_expansion"].apply(lambda s: s.shift(1).expanding().mean())
        .reset_index(level=0, drop=True)
    )

    # --- apply cold-start fallback: use segment stat when prior history thin ---
    is_cold = df["cust_n_prior_invoices"] < MIN_HISTORY_INVOICES
    df["customer_late_rate_feat"] = np.where(
        is_cold, df["segment_expanding_late_rate"], df["cust_expanding_late_rate"]
    )
    df["customer_avg_days_late_feat"] = np.where(
        is_cold, df["segment_expanding_avg_days_late"], df["cust_expanding_avg_days_late"]
    )
    df["is_cold_start"] = is_cold.astype(int)

    # global fallback for the very first invoices in a brand-new segment too
    global_late_rate = df["_late_for_expansion"].mean()
    df["customer_late_rate_feat"] = df["customer_late_rate_feat"].fillna(global_late_rate)
    df["customer_avg_days_late_feat"] = df["customer_avg_days_late_feat"].fillna(0.0)
    df["cust_expanding_avg_amount"] = df["cust_expanding_avg_amount"].fillna(
        df["total_open_amount"].expanding().mean()
    )

    df["amount_vs_customer_avg"] = df["total_open_amount"] / df["cust_expanding_avg_amount"].replace(0, np.nan)
    df["amount_vs_customer_avg"] = df["amount_vs_customer_avg"].fillna(1.0)

    df = df.drop(columns=["_late_for_expansion", "_days_late_for_expansion"])
    return df


# ---------------------------------------------------------------------------
# Step 4: terms-code frequency encoding, fit on TRAIN only
# ---------------------------------------------------------------------------

def fit_terms_code_encoding(train: pd.DataFrame) -> dict:
    top_codes = train["cust_payment_terms"].value_counts().nlargest(TOP_N_TERMS_CODES).index.tolist()
    freq_map = train["cust_payment_terms"].value_counts(normalize=True).to_dict()
    return {"top_codes": set(top_codes), "freq_map": freq_map}


def apply_terms_code_encoding(df: pd.DataFrame, encoding: dict) -> pd.DataFrame:
    df = df.copy()
    df["terms_code_grouped"] = df["cust_payment_terms"].where(
        df["cust_payment_terms"].isin(encoding["top_codes"]), "OTHER_RARE"
    )
    # unseen-in-train codes get frequency 0, not KeyError
    df["terms_code_freq"] = df["cust_payment_terms"].map(encoding["freq_map"]).fillna(0.0)
    return df


# ---------------------------------------------------------------------------
# Step 5: final feature assembly
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "amount_log",
    "payment_terms_days",
    "terms_code_freq",
    "customer_late_rate_feat",
    "customer_avg_days_late_feat",
    "cust_n_prior_invoices",
    "is_cold_start",
    "amount_vs_customer_avg",
    "business_code",
    "invoice_currency",
    "terms_code_grouped",
]
LABEL_COLUMN = "is_late"


def build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    df = add_payment_terms_days(df)
    df = add_expanding_history_features(df)
    df["amount_log"] = np.log1p(df["total_open_amount"])
    return df


def run() -> None:
    raw = pd.read_parquet(PROCESSED_PATH)

    featured = build_feature_table(raw)

    # split AFTER expanding features are computed (expanding features need
    # full chronological history to be correct at the test-set boundary —
    # see docstring on add_expanding_history_features)
    train, test = temporal_split(featured)

    n_test_before = len(test)
    n_test_still_open = (test["isOpen"] == 1).sum()
    print(f"Test set: {n_test_before} rows in window [{TEST_START}, {TEST_END}], "
          f"{n_test_still_open} still open ({n_test_still_open/n_test_before:.1%}) — "
          f"expected near-zero given the explicit pre-cliff window")

    encoding = fit_terms_code_encoding(train)
    train = apply_terms_code_encoding(train, encoding)
    test = apply_terms_code_encoding(test, encoding)

    # drop censored (open) rows — no label to train/evaluate against
    train_labeled = train[train["isOpen"] == 0].copy()
    test_labeled = test[test["isOpen"] == 0].copy()

    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    train_labeled[FEATURE_COLUMNS + [LABEL_COLUMN]].to_parquet(FEATURES_DIR / "train_features.parquet", index=False)
    test_labeled[FEATURE_COLUMNS + [LABEL_COLUMN]].to_parquet(FEATURES_DIR / "test_features.parquet", index=False)

    print(f"Train window: due_in_date < {TRAIN_END}")
    print(f"Test window:  due_in_date in [{TEST_START}, {TEST_END}]")
    print(f"Train: {len(train)} total rows, {len(train_labeled)} labeled (closed)")
    print(f"Test:  {len(test)} total rows, {len(test_labeled)} labeled (closed)")
    print(f"Train positive rate: {train_labeled[LABEL_COLUMN].mean():.4f}")
    print(f"Test positive rate:  {test_labeled[LABEL_COLUMN].mean():.4f}")
    print()
    print(f"Cold-start rows in train: {train_labeled['is_cold_start'].mean():.1%}")
    print(f"Cold-start rows in test:  {test_labeled['is_cold_start'].mean():.1%}")
    print()
    print("Feature columns:", FEATURE_COLUMNS)
    print()
    print("Sample engineered row:")
    print(train_labeled[FEATURE_COLUMNS + [LABEL_COLUMN]].iloc[0])


if __name__ == "__main__":
    run()