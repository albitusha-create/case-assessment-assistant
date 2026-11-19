# Evaluations

| Eval | What it measures | Run |
| --- | --- | --- |
| `extraction_recall.py` | Share of planted facts (`data/synthetic/source/*/case.json`) that extraction finds with the right element, document and page. Also counts facts our checks rejected. | `uv run python evals/extraction_recall.py` |

Each run calls the chat model once per case and writes a JSON report to `evals/results/` (git-ignored). Groundedness and draft quality evals land here later and run in CI as a quality gate.
