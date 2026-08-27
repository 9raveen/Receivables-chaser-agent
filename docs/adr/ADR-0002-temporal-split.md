# ADR-0002: Temporal split and censoring-aware evaluation window

## Status
Accepted

## Context
Two related risks needed handling for a leakage-free, unbiased train/test
split on AR data:

1. **Standard temporal-split risk**: random k-fold would leak future payment
   behavior into training. Addressed by splitting on `due_in_date`.

2. **Informative censoring at the split boundary** (found during Day 3, not
   anticipated in advance): a first attempt using a fraction-based cutoff
   (78% train) produced a test set where positive rate dropped from 0.420
   (train) to 0.377 (test), with only 1,128 of 10,809 test rows labeled
   (89.6% still open). Investigating `isOpen` rate by `due_in_date` month
   revealed a sharp cliff, not a gradual effect:

   | due month | open rate |
   |---|---|
   | 2018-12 – 2020-01 | ~0% |
   | 2020-02 | 0.4% |
   | 2020-03 | 67.4% |
   | 2020-04 | 97.0% |
   | 2020-05 | 99.5% |
   | 2020-07 | 100% |

   This is almost certainly the dataset's extraction/snapshot date. A
   45-day percentile-based buffer (sized off the 95th-percentile days_late
   of 10 days) barely moved the numbers (0.377 → 0.376) because the real
   boundary is a cliff, not a smooth decay — the buffer needed to be sized
   off the observed cliff itself, not off the closed-invoice lateness
   distribution.

## Decision
Explicit date-based split, chosen by checking test-set size, closed-rate,
and positive-rate balance across candidate boundaries:

- **Train**: `due_in_date < 2019-10-01` — 24,811 labeled rows, positive
  rate 0.427
- **Test**: `due_in_date` in `[2019-10-01, 2020-02-29]` — 13,058 labeled
  rows (99.9% closed), positive rate 0.407

Test window intentionally stops well before the March 2020 cliff.

## Consequences
- Train/test positive rates are now close (0.427 vs 0.407) rather than
  artificially divergent — evaluation metrics reflect real model
  performance, not a censoring artifact.
- The full March–July 2020 tail of the dataset is unused for propensity
  model evaluation (it's ~97-100% censored and uninformative for this
  purpose). This is a real, acknowledged limitation of the dataset's
  extraction timing, not a modeling choice to hide.
- This finding also validates why `add_expanding_history_features`
  (build_features.py) computes customer/segment history as an EXPANDING
  window with `shift(1)`, rather than reusing the Day 2 adapter's
  full-history `Customer.late_rate` — a static, whole-history rate would
  leak information across this exact same boundary in the other direction
  (future informing past).
