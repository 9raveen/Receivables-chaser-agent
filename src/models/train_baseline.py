"""
Day 4 — Baseline propensity model.

No hyperparameter tuning yet — this is an end-to-end pipeline sanity check.
Metric: AUC-PR (average precision), not AUC-ROC, because AUC-ROC is
optimistic under class imbalance and this dataset — while not severely
imbalanced (~42% positive) — should still be judged on the metric that
matches how the agent will actually use these scores (ranking/thresholding
invoices for intervention, where precision at the top of the ranking
matters most).

Sanity check: the model must beat a naive heuristic baseline
(payment_terms_days alone) — if it can't, something upstream is broken.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score

FEATURES_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
MODELS_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "models"

CATEGORICAL_COLS = ["business_code", "invoice_currency", "terms_code_grouped"]
NUMERIC_COLS = [
    "amount_log", "payment_terms_days", "terms_code_freq",
    "customer_late_rate_feat", "customer_avg_days_late_feat",
    "cust_n_prior_invoices", "is_cold_start", "amount_vs_customer_avg",
]
LABEL_COL = "is_late"


def load_splits():
    train = pd.read_parquet(FEATURES_DIR / "train_features.parquet")
    test = pd.read_parquet(FEATURES_DIR / "test_features.parquet")
    return train, test


def encode_categoricals(train: pd.DataFrame, test: pd.DataFrame):
    """One-hot encode categoricals, fit on train columns, align test to match
    (unseen test categories get all-zero dummies rather than crashing)."""
    train_dummies = pd.get_dummies(train[CATEGORICAL_COLS], prefix=CATEGORICAL_COLS)
    test_dummies = pd.get_dummies(test[CATEGORICAL_COLS], prefix=CATEGORICAL_COLS)
    test_dummies = test_dummies.reindex(columns=train_dummies.columns, fill_value=0)

    X_train = pd.concat([train[NUMERIC_COLS].reset_index(drop=True), train_dummies.reset_index(drop=True)], axis=1)
    X_test = pd.concat([test[NUMERIC_COLS].reset_index(drop=True), test_dummies.reset_index(drop=True)], axis=1)
    return X_train, X_test


def naive_heuristic_baseline(test: pd.DataFrame) -> np.ndarray:
    """
    Naive baseline: longer payment terms -> slightly higher chance of being
    late, normalized to [0,1] by min-max scaling payment_terms_days. This is
    the sanity floor — a model that can't beat "just look at the terms
    length" isn't learning anything useful from the richer feature set.
    """
    days = test["payment_terms_days"].values.astype(float)
    return (days - days.min()) / (days.max() - days.min() + 1e-9)


def train_baseline(X_train, y_train) -> xgb.XGBClassifier:
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        eval_metric="aucpr",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model


def run():
    train, test = load_splits()
    X_train, X_test = encode_categoricals(train, test)
    y_train, y_test = train[LABEL_COL].values, test[LABEL_COL].values

    model = train_baseline(X_train, y_train)
    y_pred = model.predict_proba(X_test)[:, 1]

    model_aucpr = average_precision_score(y_test, y_pred)
    model_aucroc = roc_auc_score(y_test, y_pred)

    heuristic_pred = naive_heuristic_baseline(test)
    heuristic_aucpr = average_precision_score(y_test, heuristic_pred)
    heuristic_aucroc = roc_auc_score(y_test, heuristic_pred)

    print(f"Test set size: {len(y_test)}, positive rate: {y_test.mean():.4f}")
    print()
    print(f"{'Metric':<12}{'Model':>12}{'Naive heuristic':>18}")
    print(f"{'AUC-PR':<12}{model_aucpr:>12.4f}{heuristic_aucpr:>18.4f}")
    print(f"{'AUC-ROC':<12}{model_aucroc:>12.4f}{heuristic_aucroc:>18.4f}")
    print()

    lift = (model_aucpr - heuristic_aucpr) / heuristic_aucpr * 100
    print(f"Model AUC-PR lift over naive heuristic: {lift:+.1f}%")

    if model_aucpr <= heuristic_aucpr:
        print()
        print("!!! MODEL DOES NOT BEAT THE NAIVE HEURISTIC — do not proceed to Day 5 "
              "until this is investigated (check feature leakage removal, encoding, "
              "or whether informative features are actually reaching the model).")
    else:
        print()
        print("Sanity check passed: model beats naive heuristic.")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(MODELS_DIR / "propensity_baseline.json")
    print()
    print(f"Model saved -> {MODELS_DIR / 'propensity_baseline.json'}")

    # quick feature importance glance (not SHAP yet — that's Day 5)
    importances = pd.Series(model.feature_importances_, index=X_train.columns).sort_values(ascending=False)
    print()
    print("Top 10 features by XGBoost gain importance:")
    print(importances.head(10))


if __name__ == "__main__":
    run()