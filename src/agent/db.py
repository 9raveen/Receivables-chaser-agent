"""
Day 9 — Postgres (Neon) connection helper.

Separate from graph.py's PostgresSaver — LangGraph manages its own
checkpoint tables/connection internally via that class. This module is
for OUR OWN tables: audit log, payment/promise/contact events, outreach
drafts (event_log.py, audit_log.py).

Uses psycopg (v3) — the same driver LangGraph's own PostgresSaver depends
on, so the project has one Postgres driver, not two.

New connection per call, no pooling: Neon is serverless/scale-to-zero and
this project's call volume is low (a handful of demo invoices, occasional
writes) — a connection pool would be premature complexity here. Revisit
if the persona eval harness (Day 10) turns out to hammer this hard enough
for per-call connection overhead to matter.
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg.connect(os.environ["DATABASE_URL"])


def init_schema() -> None:
    """
    Creates the tables event_log.py and audit_log.py need, if they don't
    already exist. Safe to call repeatedly (IF NOT EXISTS).
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS payment_events (
        id SERIAL PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        amount DOUBLE PRECISION NOT NULL,
        event_date DATE NOT NULL,
        source TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_payment_events_invoice_id ON payment_events(invoice_id);

    CREATE TABLE IF NOT EXISTS promise_events (
        id SERIAL PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        promised_amount DOUBLE PRECISION NOT NULL,
        promised_date DATE NOT NULL,
        made_on TIMESTAMPTZ NOT NULL,
        extracted_by TEXT NOT NULL,
        confidence DOUBLE PRECISION NOT NULL,
        kept BOOLEAN,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_promise_events_invoice_id ON promise_events(invoice_id);

    CREATE TABLE IF NOT EXISTS contact_attempts (
        id SERIAL PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        channel TEXT NOT NULL,
        tone TEXT NOT NULL,
        sent_at TIMESTAMPTZ NOT NULL,
        within_contact_window BOOLEAN NOT NULL,
        response_received BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_contact_attempts_invoice_id ON contact_attempts(invoice_id);

    CREATE TABLE IF NOT EXISTS outreach_drafts (
        id SERIAL PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        tone TEXT NOT NULL,
        channel TEXT NOT NULL,
        sent_at TIMESTAMPTZ NOT NULL,
        payment_link TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_outreach_drafts_invoice_id ON outreach_drafts(invoice_id);

    CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY,
        entry_id TEXT NOT NULL UNIQUE,
        invoice_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        node TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        this_hash TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_log_invoice_id ON audit_log(invoice_id);
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()