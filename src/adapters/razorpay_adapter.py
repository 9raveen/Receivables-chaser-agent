"""
Day 9 — Razorpay test-mode adapter (Payment Links).

Scope decision (see chat): Payment Links only, Invoices API deferred.
Reasoning: Invoices API needs a real customer object (email/contact) more
centrally than Payment Links does, and neither schema.py's Customer nor
synthetic_adapter.py's generation produces email/phone for any customer —
that data simply doesn't exist anywhere in this project. Payment Links'
"customer" parameter isn't mandatory (confirmed against the real
razorpay-python SDK docs), so this adapter creates links with
notify={"sms": False, "email": False} — WE control actual outreach
delivery via draft_outreach.py, Razorpay only supplies a real, working,
clickable payment URL to embed in it. This also avoids the unknown risk
of Razorpay's test mode actually emailing/texting a placeholder address
if notify were left True.

CACHING: test mode caps Payment Links at 30 per business (confirmed in
Razorpay's docs). With 55 demo invoices and a Day 10 persona harness that
may run multiple attempts per invoice, naive "create a link every call"
design would exceed that fast. This adapter creates a real link ONCE per
invoice_id (cached to disk) and reuses it on every subsequent call —
callers never need to think about the cap themselves.

FAILS SOFT: get_or_create_payment_link() catches exceptions (missing
credentials, hitting the 30-link cap, network errors) and returns None
rather than raising — draft_outreach.py falls back to its pre-Day-9
UTR/remittance-details phrasing when this happens, so a Razorpay outage
or cap-hit doesn't take down outreach drafting entirely.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from src.data.schema import Invoice

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = PROJECT_ROOT / "data" / "processed" / "razorpay_payment_links.json"

_client = None


def _get_client():
    global _client
    if _client is None:
        import razorpay

        key_id = os.environ["RAZORPAY_KEY_ID"]
        key_secret = os.environ["RAZORPAY_KEY_SECRET"]
        _client = razorpay.Client(auth=(key_id, key_secret))
    return _client


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    with open(CACHE_PATH) as f:
        return json.load(f)


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_or_create_payment_link(invoice: Invoice) -> Optional[str]:
    """
    Returns a real Razorpay test-mode payment link short_url for this
    invoice, creating one (and caching it) on first call, reusing the
    cached one on every subsequent call for the same invoice_id.

    Returns None on any failure (missing credentials, cap hit, network
    error) — callers must handle that gracefully, not assume a link
    always comes back.
    """
    try:
        cache = _load_cache()
        if invoice.invoice_id in cache:
            return cache[invoice.invoice_id]["short_url"]

        client = _get_client()
        response = client.payment_link.create({
            "amount": int(round(invoice.amount * 100)),  # paise, not rupees
            "currency": invoice.currency,
            "description": f"Payment for invoice {invoice.invoice_id}",
            "reference_id": invoice.invoice_id,  # max 40 chars — DEMO-XXXX fits easily
            "notify": {"sms": False, "email": False},
            "notes": {
                "customer_id": invoice.customer_id,
                "source": "chaser_agent",
            },
        })

        cache[invoice.invoice_id] = {
            "payment_link_id": response["id"],
            "short_url": response["short_url"],
            "created_at": datetime.now().isoformat(),
        }
        _save_cache(cache)
        return response["short_url"]

    except Exception as e:
        print(f"[razorpay_adapter] payment link creation failed for {invoice.invoice_id}: {e}")
        return None


def fetch_payment_link_status(payment_link_id: str) -> Optional[dict]:
    """
    Fetches the current status of a payment link (e.g. "created", "paid",
    "expired", "cancelled") — not yet wired into event_log.py's payment
    detection (that would mean check_stopping_conditions polling Razorpay
    on every cycle, a real design decision not made here). Exposed for
    manual/future use. Returns None on failure rather than raising.
    """
    try:
        client = _get_client()
        return client.payment_link.fetch(payment_link_id)
    except Exception as e:
        print(f"[razorpay_adapter] fetch failed for {payment_link_id}: {e}")
        return None