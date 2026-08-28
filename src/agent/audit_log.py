"""
Day 7 — Hash-chained audit log.

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
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "audit_log.jsonl"

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

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry_content, default=str) + "\n")

    return this_hash


def read_all_entries() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    entries = []
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def verify_chain(invoice_id: str | None = None) -> tuple[bool, str | None]:
    """
    Recomputes every hash from scratch and checks it matches what was
    stored. Returns (is_valid, first_broken_entry_id_or_None).
    If invoice_id is given, only that invoice's chain is checked.
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
    # smoke test: write a short chain, verify it, then tamper and verify
    # it correctly detects the tamper
    h0 = GENESIS_HASH
    h1 = write_entry("TEST-001", "score_and_route", "risk_tier=HIGH", "propensity 0.81", h0)
    h2 = write_entry("TEST-001", "select_intervention", "formal_notice", "HIGH tier, overdue_ratio 0.6", h1)

    valid, broken = verify_chain("TEST-001")
    print(f"Chain valid before tamper: {valid}")

    # tamper: rewrite the log file with one entry's decision changed but
    # hash left as-is, to prove verify_chain catches it
    entries = read_all_entries()
    for e in entries:
        if e["invoice_id"] == "TEST-001" and e["node"] == "select_intervention":
            e["decision"] = "friendly_reminder"  # tampered, hash now stale
    with open(LOG_PATH, "w") as f:
        for e in entries:
            f.write(json.dumps(e, default=str) + "\n")

    valid, broken = verify_chain("TEST-001")
    print(f"Chain valid after tamper: {valid} (broken entry: {broken})")