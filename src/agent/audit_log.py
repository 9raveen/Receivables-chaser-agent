"""
Day 7 — Hash-chained audit log.
Day 9 — MIGRATED from a JSONL file to Postgres (Neon). _compute_hash and
verify_chain are UNCHANGED from the original Day 7 source — the hashing
algorithm itself was never touched, only where entries are persisted and
read from. This matters: verify_chain must produce identical results for
entries written before and after this migration, or the compliance story
breaks.

CORRECTNESS NOTE: `timestamp` is stored as TEXT, not TIMESTAMPTZ. The
original code calls datetime.now(timezone.utc).isoformat() and hashes
that STRING — if this were stored as a native timestamp column, reading
it back would produce a Python datetime that re-serializes slightly
differently (formatting, precision) than the original string, and
verify_chain would report every entry as tampered even though nothing
changed. Storing the exact original string sidesteps that entirely.

Every node transition writes one entry. this_hash = sha256(prev_hash +
entry_content), so tampering with any entry breaks the chain from that
point forward — verifiable by recomputing hashes end to end.

This is the COMPLIANCE system of record (agent-policy-spec.md §6),
deliberately separate from LangSmith (dev-facing execution tracing). If
LangSmith tracing were disabled entirely, this log must still be complete
on its own.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from src.agent.db import get_connection

GENESIS_HASH = "GENESIS"


def _compute_hash(prev_hash: str, entry_content: dict) -> str:
    payload = prev_hash + json.dumps(entry_content, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_entry(
    invoice_id: str,
    node: str,
    decision: str,
    reason: str,
    prev_hash: str,
) -> str:
    """Appends one audit entry, returns its hash (becomes the next entry's
    prev_hash for this invoice)."""
    entry_content = {
        "entry_id": str(uuid.uuid4()),
        "invoice_id": invoice_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node,
        "decision": decision,
        "reason": reason,
        "prev_hash": prev_hash,
    }
    this_hash = _compute_hash(prev_hash, entry_content)
    entry_content["this_hash"] = this_hash

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audit_log
                   (entry_id, invoice_id, timestamp, node, decision, reason, prev_hash, this_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (entry_content["entry_id"], invoice_id, entry_content["timestamp"],
                 node, decision, reason, prev_hash, this_hash),
            )
        conn.commit()

    return this_hash


def read_all_entries() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT entry_id, invoice_id, timestamp, node, decision,
                          reason, prev_hash, this_hash
                   FROM audit_log ORDER BY id ASC"""
            )
            rows = cur.fetchall()

    entries = []
    for row in rows:
        entries.append({
            "entry_id": row[0],
            "invoice_id": row[1],
            "timestamp": row[2],
            "node": row[3],
            "decision": row[4],
            "reason": row[5],
            "prev_hash": row[6],
            "this_hash": row[7],
        })
    return entries


def verify_chain(invoice_id: str | None = None) -> tuple[bool, str | None]:
    """
    Recomputes every hash from scratch and checks it matches what was
    stored. Returns (is_valid, first_broken_entry_id_or_None).
    If invoice_id is given, only that invoice's chain is checked.
    UNCHANGED from the original Day 7 source.
    """
    entries = read_all_entries()
    if invoice_id is not None:
        entries = [e for e in entries if e["invoice_id"] == invoice_id]

    for entry in entries:
        stored_hash = entry["this_hash"]
        recompute_content = {k: v for k, v in entry.items() if k != "this_hash"}
        recomputed = _compute_hash(entry["prev_hash"], recompute_content)
        if recomputed != stored_hash:
            return False, entry["entry_id"]
    return True, None


if __name__ == "__main__":
    # smoke test: write a short chain, verify it, then tamper via a direct
    # SQL UPDATE (leaving this_hash untouched, same as the original file-
    # based test tampered the JSONL directly) and verify it's detected.
    h0 = GENESIS_HASH
    h1 = write_entry("TEST-001", "score_and_route", "risk_tier=HIGH", "propensity 0.81", h0)
    h2 = write_entry("TEST-001", "select_intervention", "formal_notice", "HIGH tier, overdue_ratio 0.6", h1)

    valid, broken = verify_chain("TEST-001")
    print(f"Chain valid before tamper: {valid}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE audit_log SET decision = %s
                   WHERE invoice_id = %s AND node = %s""",
                ("friendly_reminder", "TEST-001", "select_intervention"),
            )
        conn.commit()

    valid, broken = verify_chain("TEST-001")
    print(f"Chain valid after tamper: {valid} (broken entry: {broken})")
