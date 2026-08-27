"""
Day 1 — Data Foundation
Loads the raw invoice dataset, cleans it, and constructs the delinquency label.

Key decisions (see ADR-0001):
- Train label only on isOpen == 0 rows (closed invoices). isOpen == 1 rows are
  right-censored — we don't yet know if they'll be paid late — and must be
  excluded from label-based training, not treated as "on time."
- Customer identity is cust_number, never name_customer (name_customer is
  fuzzed/anonymized and not stable per customer).
- 1,161 exact duplicate rows in the raw export are dropped.
"""

from pathlib import Path
import pandas as pd

RAW_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "invoices_raw.csv"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# columns stored as YYYYMMDD ints/floats in the raw export
YYYYMMDD_COLS = ["due_in_date", "baseline_create_date"]
# document_create_date / document_create_date.1 are already int YYYYMMDD, no NaN
YYYYMMDD_INT_COLS = ["document_create_date", "document_create_date.1"]


def _parse_yyyymmdd(series: pd.Series) -> pd.Series:
    """Convert a YYYYMMDD float/int column (with possible NaN) to datetime."""
    return pd.to_datetime(series.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. drop exact duplicate rows
    n_before = len(df)
    df = df.drop_duplicates()
    n_dupes = n_before - len(df)

    # 2. parse dates
    df["due_in_date"] = _parse_yyyymmdd(df["due_in_date"])
    df["baseline_create_date"] = _parse_yyyymmdd(df["baseline_create_date"])
    df["document_create_date"] = _parse_yyyymmdd(df["document_create_date"])
    df["document_create_date.1"] = _parse_yyyymmdd(df["document_create_date.1"])
    df["posting_date"] = pd.to_datetime(df["posting_date"], errors="coerce")
    df["clear_date"] = pd.to_datetime(df["clear_date"], errors="coerce")

    # 3. drop the always-null / constant columns found in inspection
    df = df.drop(columns=["area_business", "posting_id"], errors="ignore")

    # 4. dtype sanity
    df["isOpen"] = df["isOpen"].astype(int)
    df["business_code"] = df["business_code"].astype(str)
    df["cust_number"] = df["cust_number"].astype(str)
    df["cust_payment_terms"] = df["cust_payment_terms"].astype(str)

    print(f"[clean] dropped {n_dupes} duplicate rows ({n_before} -> {len(df)})")
    return df


def add_label(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds:
      - days_late: clear_date - due_in_date, in days (NaN for open invoices)
      - is_late: binary label, NaN for open invoices (do not fillna -> would
        silently mislabel censored rows)
    """
    df = df.copy()
    df["days_late"] = (df["clear_date"] - df["due_in_date"]).dt.days
    df["is_late"] = (df["days_late"] > 0).astype("Int64")
    # explicitly null out label for open (censored) invoices
    df.loc[df["isOpen"] == 1, ["days_late", "is_late"]] = pd.NA
    return df


def load_clean_labeled(path: Path = RAW_PATH) -> pd.DataFrame:
    df = load_raw(path)
    df = clean(df)
    df = add_label(df)
    return df


def train_eligible(df: pd.DataFrame) -> pd.DataFrame:
    """Rows usable for training the delinquency model: closed invoices only."""
    return df[df["isOpen"] == 0].copy()


if __name__ == "__main__":
    df = load_clean_labeled()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "invoices_clean.parquet"
    df.to_parquet(out_path, index=False)

    trainable = train_eligible(df)

    print()
    print(f"Total rows (post-clean): {len(df)}")
    print(f"Open (censored, excluded from label training): {(df['isOpen'] == 1).sum()}")
    print(f"Closed (label-eligible): {len(trainable)}")
    print(f"Positive rate (is_late=1) among closed: {trainable['is_late'].mean():.4f}")
    print(f"Unique customers: {df['cust_number'].nunique()}")
    print(f"Saved cleaned dataset -> {out_path}")