"""
Day 2 — Normalized internal schema.

Every data source (Kaggle historical data, Faker-generated India synthetic
layer, Razorpay test-mode API) maps into these models via a thin adapter
(see src/adapters/). Nothing downstream — features, model, agent — should
ever touch a raw source column directly.

Design decisions encoded here (see ADR-0001, ADR-0002):
  - Identity is always `customer_id` / `invoice_id`. `display_name` exists
    only for outreach drafting, never used as a join/identity key
    (name_customer in the raw Kaggle data is unstable per customer).
  - `payment_terms_days` is a normalized numeric field the agent's urgency
    logic reads. `payment_terms_code` keeps the raw source code (opaque SAP
    code, or synthetic "NET30"/"NET60" string) for the ML model / audit.
  - Cold start: Customer.late_rate / avg_days_late are None when
    n_invoices_total < MIN_HISTORY_INVOICES. Feature code must fall back to
    segment-level aggregates rather than trust a noisy single-sample rate.
  - PaymentEvent and ContactAttempt are append-only logs, not mutable fields
    on Invoice — state (has this been paid? how many attempts?) is derived
    by reading history, never by trusting a single overwritten flag.
  - is_late / days_late are Optional and MUST be None for open (censored)
    invoices, never defaulted to 0/False. See ADR-0001 on right-censoring.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

MIN_HISTORY_INVOICES = 3  # threshold below which customer-level rates go None
                           # (matches the median found in Day 1 EDA)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DataSource(str, Enum):
    KAGGLE = "kaggle"
    SYNTHETIC = "synthetic"
    RAZORPAY = "razorpay"


class PaymentEventType(str, Enum):
    FULL_PAYMENT = "full_payment"
    PARTIAL_PAYMENT = "partial_payment"
    REVERSAL = "reversal"


class ContactChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    CALL = "call"


class ContactTone(str, Enum):
    FRIENDLY_REMINDER = "friendly_reminder"
    FIRM_REMINDER = "firm_reminder"
    FORMAL_NOTICE = "formal_notice"
    FINAL_NOTICE = "final_notice"


class InvoiceStatus(str, Enum):
    ACTIVE = "active"
    PROMISED = "promised"
    PAID = "paid"
    DISPUTED = "disputed"
    EXCEPTION = "exception"       # stopping rule tripped, needs human review
    EXHAUSTED = "exhausted"       # max attempts hit, no resolution


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------

class Customer(BaseModel):
    customer_id: str
    display_name: str
    segment: str                          # used for cold-start fallback
    country: str
    gstin: Optional[str] = None            # India GST identification number;
                                            # None for non-India (Kaggle) customers

    n_invoices_total: int = 0
    n_invoices_late: int = 0
    late_rate: Optional[float] = None            # None if cold start
    avg_days_late: Optional[float] = None          # None if cold start
    promise_keep_rate: Optional[float] = None      # None until promises exist

    @field_validator("late_rate", "avg_days_late", mode="after")
    @classmethod
    def _cold_start_guard(cls, v, info):
        # informational guard only — the actual enforcement happens where
        # these are computed (src/features), this just documents the contract
        return v

    def is_cold_start(self) -> bool:
        return self.n_invoices_total < MIN_HISTORY_INVOICES


class Invoice(BaseModel):
    invoice_id: str
    customer_id: str                       # FK -> Customer.customer_id
    business_unit: str
    currency: str                           # "USD" | "CAD" | "INR"
    amount: float

    payment_terms_code: str                 # raw code, kept for audit/ML categorical
    payment_terms_days: int                 # normalized numeric terms (agent reads this)

    invoice_date: date
    due_date: date
    posting_date: date
    cleared_date: Optional[date] = None

    is_open: bool
    days_late: Optional[int] = None         # None if is_open — never 0
    is_late: Optional[bool] = None          # None if is_open — see ADR-0001
    disputed: bool = False

    source: DataSource
    status: InvoiceStatus = InvoiceStatus.ACTIVE

    @field_validator("days_late", "is_late")
    @classmethod
    def _censoring_guard(cls, v, info):
        is_open = info.data.get("is_open")
        if is_open and v is not None:
            raise ValueError(
                "days_late/is_late must be None for open (censored) invoices — "
                "see ADR-0001 on right-censoring"
            )
        return v


class PaymentEvent(BaseModel):
    invoice_id: str
    event_type: PaymentEventType
    amount: float
    event_date: date
    source: DataSource


class PromiseEvent(BaseModel):
    invoice_id: str
    promised_amount: float
    promised_date: date
    made_on: datetime
    extracted_by: str = "agent"             # "agent" | "manual"
    confidence: float = Field(ge=0.0, le=1.0)
    kept: Optional[bool] = None             # None until promised_date passes


class ContactAttempt(BaseModel):
    invoice_id: str
    attempt_number: int
    channel: ContactChannel
    tone: ContactTone
    sent_at: datetime
    within_contact_window: bool
    response_received: bool = False


class AuditLogEntry(BaseModel):
    entry_id: str
    invoice_id: str
    timestamp: datetime
    node: str                               # which LangGraph node produced this
    decision: str
    reason: str
    prev_hash: str
    this_hash: str