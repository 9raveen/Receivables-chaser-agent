# ADR-0003: Promise-keep model trained on simulated data

## Status
Accepted

## Context
A promise-keep prediction model (predict whether a buyer will honor a
specific "I'll pay by X" promise) requires promise-outcome history to
train on. No such data exists anywhere available to this project:
- The Kaggle AR dataset has no promise concept at all.
- Real Razorpay promise data only starts existing once the LangGraph agent
  (Day 7-8) begins extracting promises from actual buyer replies — which
  hasn't happened yet at Day 5.

## Decision
Train on simulated promise outcomes, generated from the synthetic India
customer pool (src/adapters/synthetic_adapter.py), using a dedicated
larger pool (300 customers, separate from the 40-customer demo pool) to
get enough simulated late invoices to promise-simulate a usable training
set.

Simulation logic: a promise is only generated for invoices that were
actually late in that customer's simulated history (a promise-to-pay
scenario only exists once an invoice is overdue). `made_on` and
`promised_date` are randomly offset from `due_date`; `kept` is derived
from whether the invoice's already-simulated `clear_date` falls on or
before the promised date — so the label falls naturally out of each
customer's underlying risk profile rather than being separately assigned.

## Result (honestly characterized, not oversold)
- 721 simulated promise events, 64.5% kept rate
- Test AUC-PR: 0.710 vs. naive base-rate AUC-PR 0.646 (+9.9% lift)
- Test AUC-ROC: 0.573 — modest, barely above random
- Feature importance is sensibly spread across `promise_horizon_days`,
  `terms_days`, `customer_late_rate`, `days_overdue_at_promise` — no
  degenerate single-feature dominance, suggesting the simulation has
  learnable (if noisy) structure rather than being pure noise.

## Consequences
- **This model should be presented as a modest second-order signal, not a
  strong standalone classifier.** The lift over naive is real but small.
- The pitch must state clearly that promise-keep training data is
  simulated — the same honesty standard applied to ADR-0001's dataset
  choice. If the project were extended past the hackathon, this would be
  the first model to retrain on real (agent-collected) promise data.
- Because the underlying signal is inherently weaker than the propensity
  model's, the agent's policy (Day 6) should treat promise-keep score as
  an adjustment to behavior (e.g., shorter follow-up grace period for a
  low predicted keep-rate), not as a primary escalation trigger on its
  own.
