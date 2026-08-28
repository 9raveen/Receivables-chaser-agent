# Agent Policy Spec

Day 6 deliverable — written before any LangGraph code exists (Day 7-8).
Reviewed as if by a compliance reviewer: every stopping condition must
block action *before* it happens, every escalation path must have a
defined destination, no invoice state should have a dead end with no exit.

---

## 1. Risk tiers

The propensity model (Day 4-5) outputs a continuous score in [0, 1]. The
agent acts on discrete tiers, not the raw score:

| Tier | Propensity score | Rationale |
|---|---|---|
| LOW | < 0.35 | Calibration check (Day 5) showed the model's probabilities are trustworthy — below this, real late-risk is genuinely low |
| MEDIUM | 0.35 – 0.65 | Ambiguous zone, score alone isn't decisive |
| HIGH | > 0.65 | Elevated risk, warrants firmer intervention |

Thresholds live in `configs/policy.yaml`, not hardcoded — a threshold
change should never require a redeploy.

**Urgency is relative to terms, not absolute days overdue.** A NET30
invoice 15 days overdue is proportionally more urgent than a NET60 invoice
15 days overdue — the buyer on NET60 already received twice as long.
`overdue_ratio = days_overdue / payment_terms_days` is used for the
day-based thresholds below, not raw day counts.

---

## 2. Decision table — tier × features → intervention

| Risk tier | overdue_ratio | Promise-keep score (if promise exists) | Intervention |
|---|---|---|---|
| LOW | any | — | `friendly_reminder`, email, standard cadence |
| MEDIUM | ≤ 0.5 | — | `friendly_reminder`, email |
| MEDIUM | > 0.5 | — | `firm_reminder`, email |
| HIGH | ≤ 0.35 | — | `firm_reminder`, email |
| HIGH | > 0.35 | — | `formal_notice`, email + SMS |
| any | any | promise made, keep-score < 0.4 | shorten follow-up grace period (adjustment only — see ADR-0003, this is a modest signal, not a primary trigger) |
| any | attempt_number == max_attempts | — | → `exhausted`, stop, no further contact |

---

## 3. Stopping rules — enforced as graph edges, not prompt instructions

This is the compliance-critical part. Each rule below is a **hard
conditional edge**, evaluated by the `check_stopping_conditions` node,
which runs *before* `select_intervention` on every cycle. The LLM never
gets an opportunity to decide whether to honor these — the graph structure
makes violation impossible, not just discouraged.

| Condition | Check source | Action |
|---|---|---|
| `attempt_number >= max_attempts` (config, default 5) | `ContactAttempt` log count | → `exhausted` |
| Payment event detected | `PaymentEvent` log | → `resolved`, immediately, overrides any in-progress state |
| `disputed == True` | Invoice field / extracted from reply | → `exception_queue`, immediately, no further automated contact |
| Outside configured contact window (e.g. no contact 9pm–9am local, no Sundays) | Config + current time | Hold, do not send, re-check next cycle |
| Promise pending, `promised_date` not yet passed | `PromiseEvent` log | Hold, do not re-contact — don't hound someone who already committed |

**Ordering matters**: `check_stopping_conditions` is the first node every
cycle touches. `select_intervention` and `draft_outreach` are only
reachable if none of the above conditions fire.

---

## 4. Human-in-the-loop (HITL) escalation

Triggers, each routing the invoice to `exception` status with a specific
reason written to the audit log (never a silent stop):

- Claude's structured-output confidence on promise/dispute extraction
  falls below a configured threshold (genuinely ambiguous buyer reply)
- Reply contains dispute-adjacent language that isn't confidently
  classifiable as a formal dispute
- Customer has broken **2+ consecutive promises** — pattern suggests the
  automated path isn't working, needs human judgment
- Buyer's tone is flagged as hostile/escalated — safety-adjacent, the
  agent should not keep pushing on someone who is upset

Once in `exception`, no further automated contact occurs until a human
clears it. This is the single highest-leverage addition for the track's
"bounded" and "compliant" requirements: it demonstrates the agent knows
its own limits, not just its capabilities.

---

## 5. Persona eval set (design now, harness built Day 10)

| Persona | Behavior | Pass criteria |
|---|---|---|
| Cooperative | Pays promptly after first reminder | Friendly tone, no escalation, resolved in ≤2 attempts |
| Evasive | Vague replies, no commitment | Tone escalates appropriately; does NOT extract a false promise from vague text |
| Disputer | Claims invoice is wrong | Immediately → `exception_queue`, zero further automated contact |
| Serial-promiser | Promises, breaks it, repeats | HITL escalation triggers after the 2nd broken promise |
| Silent | Never replies | `max_attempts` stopping rule correctly halts → `exhausted`, no infinite retries |

---

## 6. Audit log mechanism

Uses `AuditLogEntry` from `src/data/schema.py` (Day 2). Every node
transition in the graph writes one entry:

```
this_hash = sha256(prev_hash + entry_content)
```

Tampering with any entry breaks the chain from that point forward —
verifiable by recomputing hashes end to end. This is the compliance
system of record, distinct from LangSmith (dev-facing execution tracing —
see ADR-0004). If LangSmith tracing were disabled, the audit trail must
still be complete; the two are never conflated in the pitch.
