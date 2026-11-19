# 0002. Orchestrate the agents in code, with Foundry agents as workers

- Status: accepted
- Date: 2026-11-19

## Context

The workflow is a fixed business process: ingest, extract, draft, QA check, human review. Two steps need an LLM agent (drafting and QA). Every step must be auditable, testable, and stop for a human before anything is final.

As of November 2026, Microsoft Foundry Agent Service is generally available, multi-agent workflows are in public preview, and connected agents (classic) are deprecated with retirement on March 31, 2027.

## Decision

Define the Drafting and QA agents as Foundry prompt agents (versioned, traced, evaluated in Foundry). A small Python orchestrator in `src/caa/agents/orchestrator.py` calls them in order, dispatches their function tool calls to the rules package, and writes an audit event after each step.

## Alternatives considered

- **Foundry multi-agent workflows.** Declarative and visual, and a good fit for branching flows. Not chosen because it is in preview and our flow is linear; also harder to unit test and to hook into our audit log. Revisit when it reaches GA or the flow gains branches.
- **Connected agents.** Deprecated; not an option for new work.
- **Microsoft Agent Framework or LangGraph.** Strong for complex graphs and long-running state. More abstraction than a three-step linear flow needs.

## Consequences

- The process order, retries and stop points are ordinary code with tests.
- Foundry still provides agent versioning, tracing and evaluations.
- We own about a hundred lines of orchestration code.
- Moving to a Foundry workflow later changes the orchestrator, not the agents or the rules.
