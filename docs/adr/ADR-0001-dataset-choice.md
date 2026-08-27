# ADR-0001: Propensity model training dataset

## Status
Accepted

## Context
No public, real, anonymized B2B AR/factoring dataset with a usable delinquency
label exists (a genuine gap — real receivables data is commercially sensitive
and not published). Three Kaggle candidates were evaluated:

1. `hhenry/finance-factoring-ibm-late-payment-histories` — 2,466 rows, 100
   customers. Confirmed to be an IBM Watson Analytics fabricated demo dataset
   (`WA_Fn-UseC_` filename prefix), not real data. Uniform NET30 terms only
   (zero variance), toy-scale invoice amounts ($5–$128).
2. `rajattomar132/payment-date-dataset` — likely a repost/duplicate of (1),
   insufficient distinguishing information found.
3. `pradumn203/payment-date-prediction-for-invoices-dataset` — SAP-style AR
   export, 50,000 rows, 1,425 customers, 74 distinct `cust_payment_terms`
   codes, invoice amounts $0.72–$668,593 (realistic B2B scale), 2
   currencies, 6 business units.

## Decision
Use dataset (3). It is structurally realistic (genuine payment-terms and
invoice-amount variation, multi-entity structure) even though it is likely
adapted/anonymized for a modeling exercise rather than raw production data.

## Known limitations (deliberately not hidden)
- **Right-censoring**: 9,681 rows (~20%) have `isOpen=1` — unpaid as of
  extraction, outcome unknown. These are excluded from label-based training
  entirely rather than treated as "on time." Trainable set: 39,158 rows
  (after dedup), 41.9% positive (late) rate.
- **Duplicate rows**: 1,161 exact duplicates in the raw export, dropped.
- **Customer identity**: `name_customer` is fuzzed/anonymized and not stable
  per customer (960/1425 customers have >1 distinct name string for the same
  `cust_number`). All customer-level features key on `cust_number`.
- **Cold start**: customer invoice history is heavily skewed — median 3
  invoices/customer, 45.7% of customers have fewer than 3. Customer-history
  features need a segment-level fallback for thin-history customers.
- **Payment-terms cardinality**: 74 codes, only 9 cover 90% of rows. Top ~10
  encoded individually, remainder bucketed as `OTHER_RARE`.
- **Not India-specific**: no INR, GST, or NET30/60-labeled terms in the raw
  data. This is exactly why the synthetic India layer (Day 2) exists — it is
  not decorative, it fills a real, named gap in available real-world data.
- **Temporal scope**: dates span 2018-12 to 2020-07. Behavioral/relational
  patterns (large invoices settle slower, prior-late customers repeat) are
  treated as stable over time; absolute/macroeconomic features avoided in
  favor of relative ones for this reason.

## Consequences
- Relative/behavioral features preferred over absolute thresholds throughout
  the feature set (Day 3).
- Cold-start fallback logic required for customer-history features.
- The pitch frames this honestly: "no real public dataset exists" is part of
  the market-gap argument, not a weakness to obscure.
