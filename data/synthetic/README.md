# Synthetic data

All case files here are fictional. Names, places, organizations and events are invented, and every document is labeled as fictional. Any resemblance to real people or organizations is coincidental.

## Layout

- `source/case-00N/*.md`: the human-readable source of each document. `<<<PAGE>>>` starts a new page.
- `source/case-00N/case.json`: assessment type, start date, expected facts (ground truth with document and page), planted issues, and any 42 CFR Part 2 style documents.
- `cases/case-00N/*.pdf`: the PDFs that get uploaded. Generated, do not edit by hand.
- `generator/build_pdfs.py`: regenerates the PDFs.

```bash
uv run --group data python data/synthetic/generator/build_pdfs.py
```

## The cases

| Case | Type | What it exercises |
| --- | --- | --- |
| case-001 | Initial assessment | Clean case: every required element is in the file |
| case-002 | Initial assessment | A contradiction between sources (who the youth lives with) and a missing element (no substance use history) |
| case-003 | Initial assessment | A missing element (no prior services documented) |
| case-004 | Reassessment | A substance use disorder treatment record released with consent, for Part 2 style handling |

The expected facts feed the evaluation datasets: extraction recall, citation accuracy, and whether the QA agent catches each planted issue.
