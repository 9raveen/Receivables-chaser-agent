# Compliance Framing Note

Documentation-level note on what "compliant escalation" means in this
project's design — not a legal review. Written to show the design was
deliberate, not accidental.

## What "compliant" means here, concretely

- **Contact windows**: no outreach outside configured hours (default
  9am–9pm local) or on configured no-contact days (default Sundays).
  Enforced as a stopping-rule edge (agent-policy-spec.md §3), not a prompt
  instruction.
- **No harassment patterns**: `max_attempts` (default 5) is a hard ceiling
  on contact per invoice, enforced the same way. A silent buyer stops
  being contacted, not endlessly re-tried.
- **Dispute = immediate stop**: any invoice flagged disputed routes to
  `exception_queue` immediately, with zero further automated contact until
  a human clears it. This is the single most important rule in the spec —
  continuing to chase a disputed invoice is the clearest possible
  compliance failure this design could have.
- **No autonomous money movement**: the agent reads, reasons, and drafts.
  It does not move funds, alter invoice records, or take any action
  outside the bounded node set defined in the graph (agent-policy-spec.md).
- **Escalation, not silent failure**: every stopping condition and every
  HITL trigger routes to a defined destination with a logged reason — no
  invoice can be silently dropped or left in an undefined state.

## What this note is not

Not a substitute for actual legal/compliance review in a real deployment.
No claim is made about RBI collection-practice regulations or equivalent
being fully satisfied — this is a hackathon-scope design decision showing
the *shape* of a compliant system (stopping rules as enforced code,
disputes halting contact, bounded action set, full audit trail), not a
certified compliance product.
