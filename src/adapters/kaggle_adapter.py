"""
Day 2 — Kaggle adapter.

Maps data/processed/invoices_clean.parquet (Day 1 output) into the
normalized schema (src/data/schema.py). This is the first of three planned
adapters (kaggle, synthetic/faker, razorpay) — all three must produce the
same Invoice/Customer objects so downstream code (features, model, agent)
never touches a raw source column.

Key derivations (documented because they're not free of judgment calls):
  - `payment_terms_days`: the raw `cust_payment_terms` codes (74 distinct,
    e.g. "NAH4", "CA10") are opaque internal SAP codes with no public decode
    table. Instead of guessing semantics from the code string, terms length
    is derived EMPIRICALLY as the median (due_date - invoice_date) across
    all invoices sharing that code. This is measured, not assumed.
  - `invoice_date` = document_create_date (best available proxy in the raw
    export for "when the invoice was created").
  - `country` is derived from `invoice_currency` (USD -> US, CAD -> CA) as
    a documented heuristic — there is no real country column in the source.
  - Customer `late_rate` / `avg_days_late` are computed ONLY from closed
    (is_open=False) invoices, and set to None (cold start) when a customer
    has fewer than MIN_HISTORY_INVOICES total invoices (see schema.py /
    ADR-0001).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.schema import (
    Customer,
    DataSource,
    Invoice,
    MIN_HISTORY_INVOICES,
)

PROCESSED_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "invoices_clean.parquet"

CURRENCY_TO_COUNTRY = {"USD": "US", "CAD": "CA"}


def _derive_payment_terms_days(df: pd.DataFrame) -> pd.Series:
    """Median (due_in_date - document_create_date) per cust_payment_terms code."""
    implied_days = (df["due_in_date"] - df["document_create_date"]).dt.days
    per_code_median = implied_days.groupby(df["cust_payment_terms"]).transform("median")
    # guard against any pathological negative/NaN medians (bad rows) -> fall
    # back to the global median rather than propagate garbage
    global_median = implied_days.median()
    per_code_median = per_code_median.where(per_code_median > 0, global_median)
    return per_code_median.round().astype(int)


def build_invoices(df: pd.DataFrame) -> list[Invoice]:
    df = df.copy()
    df["payment_terms_days"] = _derive_payment_terms_days(df)

    invoices = []
    for row in df.itertuples(index=False):
        invoices.append(
            Invoice(
                invoice_id=str(int(row.doc_id)),
                customer_id=str(row.cust_number),
                business_unit=str(row.business_code),
                currency=str(row.invoice_currency),
                amount=float(row.total_open_amount),
                payment_terms_code=str(row.cust_payment_terms),
                payment_terms_days=int(row.payment_terms_days),
                invoice_date=row.document_create_date.date(),
                due_date=row.due_in_date.date(),
                posting_date=row.posting_date.date(),
                cleared_date=(row.clear_date.date() if pd.notna(row.clear_date) else None),
                is_open=bool(row.isOpen),
                days_late=(int(row.days_late) if pd.notna(row.days_late) else None),
                is_late=(bool(row.is_late) if pd.notna(row.is_late) else None),
                disputed=False,  # no dispute column in source; defaults False
                source=DataSource.KAGGLE,
            )
        )
    return invoices


def build_customers(df: pd.DataFrame) -> list[Customer]:
    customers = []
    for cust_id, group in df.groupby("cust_number"):
        closed = group[group["isOpen"] == 0]
        n_total = len(group)
        n_closed = len(closed)
        n_late = int((closed["is_late"] == 1).sum()) if n_closed else 0

        cold_start = n_total < MIN_HISTORY_INVOICES
        late_rate = None if cold_start or n_closed == 0 else n_late / n_closed
        avg_days_late = (
            None
            if cold_start or n_closed == 0
            else float(closed.loc[closed["is_late"] == 1, "days_late"].mean())
            if n_late > 0
            else 0.0
        )

        # display_name: most frequent name string seen for this customer
        # (names are fuzzed/unstable per ADR-0001 — display only, never a key)
        display_name = group["name_customer"].mode().iloc[0]
        segment = group["business_code"].mode().iloc[0]
        currency_mode = group["invoice_currency"].mode().iloc[0]
        country = CURRENCY_TO_COUNTRY.get(currency_mode, "UNKNOWN")

        customers.append(
            Customer(
                customer_id=str(cust_id),
                display_name=str(display_name),
                segment=str(segment),
                country=country,
                n_invoices_total=n_total,
                n_invoices_late=n_late,
                late_rate=late_rate,
                avg_days_late=avg_days_late,
                promise_keep_rate=None,  # no promises exist yet at this stage
            )
        )
    return customers


def load_kaggle_source(path: Path = PROCESSED_PATH) -> tuple[list[Invoice], list[Customer]]:
    df = pd.read_parquet(path)
    invoices = build_invoices(df)
    customers = build_customers(df)
    return invoices, customers


if __name__ == "__main__":
    invoices, customers = load_kaggle_source()

    n_cold_start = sum(1 for c in customers if c.is_cold_start())

    print(f"Built {len(invoices)} Invoice objects, {len(customers)} Customer objects")
    print(f"Cold-start customers (n_invoices_total < {MIN_HISTORY_INVOICES}): "
          f"{n_cold_start} ({n_cold_start/len(customers):.1%})")

    sample_inv = invoices[0]
    sample_cust = next(c for c in customers if c.customer_id == sample_inv.customer_id)
    print()
    print("Sample invoice:", sample_inv.model_dump())
    print()
    print("Its customer:", sample_cust.model_dump())

    terms_days_seen = sorted({inv.payment_terms_days for inv in invoices})
    print()
    print(f"Distinct derived payment_terms_days values: {len(terms_days_seen)}")
    print(f"Range: {min(terms_days_seen)}–{max(terms_days_seen)}")