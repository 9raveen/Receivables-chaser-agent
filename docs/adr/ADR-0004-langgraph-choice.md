# ADR-0004: LangGraph over plain LangChain AgentExecutor

## Status
Accepted

## Context
The agent needs to: persist per-invoice state across days (promise
tracking spans a week or more), enforce hard stopping rules regardless of
what an LLM call returns, handle multi-turn branching conversations (reply
→ promise / dispute / silence), and support human-in-the-loop escalation.

Two candidates were considered: LangGraph (graph-based orchestration) and
plain LangChain `AgentExecutor` (single-loop, LLM decides the next tool
call each turn).

## Decision
LangGraph.

| Requirement | LangGraph | AgentExecutor |
|---|---|---|
| Per-invoice state persisted across days | Native checkpointing | Would require hand-rolled state persistence |
| Stopping rules enforced in code, not prompt | Conditional edges are real control flow | Weak — stopping logic ends up as instructions the model has to obey, which undercuts the compliance story |
| Multi-turn branching (reply → promise/dispute/silence) | Native — this is what graphs are for | Simulated with if/else glue code around the loop |
| HITL escalation | `interrupt()` is a first-class pattern | Bolt-on, not idiomatic |
| Audit trail granularity | Each node/edge traversal is a natural log point | Requires manual instrumentation for equivalent granularity |

The deciding factor: `AgentExecutor` is built for "single-session, LLM
picks the next tool call" workflows. This project's actual requirements —
persistent per-invoice state, hard-coded stopping conditions regardless of
LLM output, HITL — are the textbook case LangGraph was built for. Using
`AgentExecutor` here would mean fighting the framework to simulate graph
behavior, and it would put control flow in prompts instead of code, which
directly undercuts the "bounded, compliant" pitch this track requires.

## Consequences
- LangSmith tracing is native to LangGraph (env vars only, no
  instrumentation code) — used as a dev-facing execution trace, kept
  distinct from the hash-chained `AuditLogEntry` log, which is the
  compliance system of record (see agent-policy-spec.md §6). If LangSmith
  tracing is disabled, the audit trail must remain complete on its own.
