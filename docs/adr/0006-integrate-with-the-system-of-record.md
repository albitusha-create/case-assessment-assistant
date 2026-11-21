# 0006. Integrate with the agency's system of record, do not replace it

- Status: accepted
- Date: 2026-11-21

## Context

Workers already complete a core assessment form in an agency case management system. They gather facts from several documents and type each section by hand. That system is the system of record: it is where the assessment is signed, submitted and audited by the agency. A new tool that asks workers to submit somewhere else adds a second record and a second habit, and it will not be adopted.

The repo includes a mock of such a system (`src/caa/portal`), with a generic form and synthetic data, so the integration can be shown end to end.

## Decision

The assistant is a client of the agency system, through that system's API:

- It reads the case record before drafting.
- After a supervisor approves, it maps the draft onto the agency form and saves it there as a **draft**, with the source document and page under each pre-filled section.
- The worker reviews, edits and submits in the agency system. The API offers no submit operation, and the assistant never asks for one.
- The agency system notifies us through a signed webhook when the worker submits, so our audit log records the outcome and how many pre-filled sections the worker changed.

The mapping from our draft to the form is a table in code, not a model call. Clinical sections (mental health, substance use, trauma) and the person's own self-rating are never pre-filled: the assistant shows cited facts beside them as a reference, and the agency system refuses a pre-fill there as well. Sections the records do not cover become a list of topics to raise in the interview.

The same operations are exposed as MCP tools for agents. The only write tool takes a case id, not text, and runs the same approval check.

## Alternatives considered

- **Our app as the place of record.** Simpler to build, but it duplicates the agency record and changes how workers work.
- **Fill the agency form through screen automation.** Works without an API, but it is brittle, hard to audit and easy to break with a UI change. An API is the right contract when one exists.
- **Let the model write the form directly.** Faster to demo, but it skips the supervisor gate and the deterministic mapping a reviewer can check line by line.

## Consequences

- Workers keep their system and their final say. The measure of value is the share of pre-filled sections they keep, which the submit webhook reports.
- A portal outage never blocks drafting or approval. A failed or refused send is logged and can be retried, and retries are idempotent.
- The portal client is the seam for a real vendor: point `PORTAL_BASE_URL` at it and replace the bearer key with the vendor's OAuth client credentials, ideally through API Management.
- The mock portal keeps its state in memory and resets on restart. That is fine for a demo, not for anything else.
