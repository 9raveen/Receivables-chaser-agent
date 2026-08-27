"""
Day 5, part 1 — Calibration + SHAP.

Calibration matters here specifically because the agent (Day 6-8) will
THRESHOLD decisions on these scores (e.g. "score > 0.6 -> escalate tier"),
not just rank invoices by them. A model can have great AUC-PR (good at
RANKING who's riskier) while being badly calibrated (a "0.8" doesn't
actually mean an 80% chance) — ranking quality and calibration are
different properties and both matter for different reasons here.

SHAP explains individual predictions in plain terms — this feeds directly
into Day 7-8's draft_outreach node, which cites a specific reason (e.g.
"this customer has a pattern of late payments") rather than a bare score.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display in this environment
import matplotlib.pyplot as plt
import pandas as pd
import shap
import xgboost as xgb
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss

from src.models.train_baseline import (
    CATEGORICAL_COLS,
    FEATURES_DIR,
    LABEL_COL,
    NUMERIC_COLS,
    encode_categoricals,
    load_splits,
    MODELS_DIR,
)

FIGURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "figures"


def load_trained_model() -> xgb.XGBClassifier:
    model = xgb.XGBClassifier()
    model.load_model(MODELS_DIR / "propensity_baseline.json")
    return model


def plot_calibration(y_test, y_pred_raw, y_pred_calibrated, out_path: Path):
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfectly calibrated")

    frac_pos_raw, mean_pred_raw = calibration_curve(y_test, y_pred_raw, n_bins=10, strategy="quantile")
    ax.plot(mean_pred_raw, frac_pos_raw, marker="o", label="Raw XGBoost")

    frac_pos_cal, mean_pred_cal = calibration_curve(y_test, y_pred_calibrated, n_bins=10, strategy="quantile")
    ax.plot(mean_pred_cal, frac_pos_cal, marker="s", label="Isotonic-calibrated")

    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives (actual)")
    ax.set_title("Calibration / Reliability Curve")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_shap_summary(model, X_test, out_path_bar: Path, out_path_beeswarm: Path):
    explainer = shap.TreeExplainer(model)
    shap_values = explainer(X_test)

    fig = plt.figure()
    shap.summary_plot(shap_values, X_test, plot_type="bar", show=False)
    fig = plt.gcf()
    fig.tight_layout()
    fig.savefig(out_path_bar, dpi=120)
    plt.close(fig)

    fig = plt.figure()
    shap.summary_plot(shap_values, X_test, show=False)
    fig = plt.gcf()
    fig.tight_layout()
    fig.savefig(out_path_beeswarm, dpi=120)
    plt.close(fig)

    return shap_values


def explain_single_invoice(model, X_test, test_df, shap_values, row_idx: int = 0):
    """Turns SHAP values for one row into a plain-language reason string —
    this is the format the agent's draft_outreach node will consume later."""
    row_shap = shap_values[row_idx]
    contributions = pd.Series(row_shap.values, index=X_test.columns).sort_values(key=abs, ascending=False)
    top3 = contributions.head(3)

    print(f"\nExplanation for test row {row_idx} (actual is_late={test_df.iloc[row_idx][LABEL_COL]}):")
    for feat, val in top3.items():
        direction = "increases" if val > 0 else "decreases"
        print(f"  - {feat} {direction} risk (SHAP contribution: {val:+.3f})")


def run():
    train, test = load_splits()
    X_train, X_test = encode_categoricals(train, test)
    y_train, y_test = train[LABEL_COL].values, test[LABEL_COL].values

    model = load_trained_model()
    y_pred_raw = model.predict_proba(X_test)[:, 1]

    # --- calibration ---
    brier_raw = brier_score_loss(y_test, y_pred_raw)

    calibrator = IsotonicRegression(out_of_bounds="clip")
    half = len(X_test) // 2
    calibrator.fit(y_pred_raw[:half], y_test[:half])
    # Note: calibrating and evaluating both on test would be circular; in a
    # non-hackathon setting this would use a held-out calibration split.
    # Flagging this explicitly rather than silently doing it wrong.
    y_pred_calibrated = calibrator.transform(y_pred_raw[half:])
    y_test_cal_eval = y_test[half:]
    brier_calibrated = brier_score_loss(y_test_cal_eval, y_pred_calibrated)
    aucpr_calibrated = average_precision_score(y_test_cal_eval, y_pred_calibrated)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_calibration(
        y_test[half:], y_pred_raw[half:], y_pred_calibrated,
        FIGURES_DIR / "calibration_curve.png",
    )

    print(f"Brier score — raw model:        {brier_raw:.4f}")
    print(f"Brier score — isotonic (holdout half): {brier_calibrated:.4f}")
    print(f"AUC-PR on that holdout half: {aucpr_calibrated:.4f}")
    print(f"Calibration curve saved -> {FIGURES_DIR / 'calibration_curve.png'}")

    # --- SHAP ---
    shap_values = plot_shap_summary(
        model, X_test,
        FIGURES_DIR / "shap_bar.png",
        FIGURES_DIR / "shap_beeswarm.png",
    )
    print(f"SHAP plots saved -> {FIGURES_DIR}/shap_bar.png, shap_beeswarm.png")

    explain_single_invoice(model, X_test, test, shap_values, row_idx=0)
    explain_single_invoice(model, X_test, test, shap_values, row_idx=1)


if __name__ == "__main__":
    run()