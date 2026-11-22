# 0007. Assist the worker inside the agency portal, one section at a time

- Status: accepted
- Date: 2026-11-22

## Context

ADR 0006 puts the worker's final edit and submit in the agency system. Until now the assistant helped only before that: it pre-filled a draft after a supervisor approved it. While the worker types in the portal (after an interview, or in a section the records did not cover) they get no help, and the QA checklist is applied only to the AI draft, not to what is finally submitted.

## Decision

The portal's form page hosts a small script from the assistant, the way an agency system hosts a sidebar app from a vendor. It adds **Check with assistant** under each section the assistant may review. The worker's current text goes to our API (`POST /api/assist/cases/{case}/sections/{section}/check`) and the results show under the field:

- **Rule checks in code:** wording that reads as an eligibility, risk, diagnosis or level of care determination (the same phrase list as the draft QA).
- **QA checklist judgment, scoped to the section:** statements agree with the case documents, conflicts are named, safety concerns are carried, person-first language, and (in Strengths) specific strengths. Severity comes from the checklist; an item the model does not report is shown as not checked.
- **Facts the worker can insert:** up to five facts from the case documents that belong in the section and are not in the text yet, each with its document and page. **Insert** appends the sentence to the field.

Everything is advice. The worker decides, and nothing blocks the portal's save or submit. The assistant never writes to the form itself.

The line the portal draws for pre-fill holds here too: clinical sections and the person's own self-rating get no button, and the API refuses them. Each check and each inserted fact is written to the assistant's audit log, with the section and source, never the worker's text.

The check is one structured model call with the section's elements, the checklist items and every chunk of the case, not a run of the Foundry QA agent. As in extraction, the model cites chunk ids only, and code looks up the document and page and drops any chunk outside the case.

## Alternatives considered

- **Run the Foundry QA agent per section.** It is built to review a whole cited draft and loops over tool calls to read chunks, which takes too long for a worker waiting on a button. A section is small enough to send whole.
- **Check on every keystroke or on leaving the field.** More model calls and cost, and results that change under the worker's cursor. A button keeps the worker in control and the cost visible.
- **Rewrite the worker's text.** Faster to demo, but it takes the narrative away from the person who did the interview. Suggestions are separate sentences with sources, inserted only on request.

## Consequences

- The checklist now reaches what the worker submits, not only the AI draft.
- The audit log shows how workers use the assistant in the portal: which sections they checked, what stayed open and which suggested facts they inserted.
- A real vendor integration would need the agency system to allow the panel (an extension point or a browser extension), and calls would go through API Management with per-user rate limits.
- The model call is not traced as a Foundry agent run. If tracing per section matters, move it to a third prompt agent with no tools.
