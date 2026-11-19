# 0004. Business rules are deterministic code the agents call as tools

- Status: accepted
- Date: 2026-11-19

## Context

Required sections, required elements, due dates and QA checks must give the same answer every time, be explainable to a reviewer, and change through code review, not prompt edits. LLMs are good at reading, drafting and spotting contradictions, and unreliable at counting, date math and policy.

## Decision

Put every rule in `src/caa/rules/` as a pure Python function with unit tests, driven by versioned YAML in `criteria/`. Register the rules as Foundry function tools. The agent asks for a rule result; our process runs the function and returns the result. The QA gap report labels each finding as either a rule result or an AI observation.

## Alternatives considered

- **Rules in prompts.** Fast to write, impossible to test, and drifts silently.
- **Rules behind an MCP server.** A clean way to share tools across agents and clients. A stretch item; the functions do not change, only how they are exposed.

## Consequences

- Checklist changes are YAML diffs with a version number recorded on each QA result.
- The LLM never decides eligibility, risk level or level of care; a rule flags such wording.
- Rule results are reproducible in evaluations and CI.
