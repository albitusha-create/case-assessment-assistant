"""Extraction recall eval: how many planted facts does extraction find?

    uv run python evals/extraction_recall.py               # all cases, gate at 0.8
    uv run python evals/extraction_recall.py --min-recall 0.9

Runs extraction live (one model call per case), prints what was missed, writes
a JSON report to evals/results/, and exits non-zero when recall is below the
threshold or any fact fills a planted gap, so CI can use it as a gate.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from azure.identity import DefaultAzureCredential

from caa.config import get_settings
from caa.extraction.extractor import extract_facts
from caa.extraction.scoring import RecallReport, score_recall
from caa.ingestion.pipeline import clients_from_settings
from caa.retrieval.search import list_case_chunks
from caa.rules import load_criteria
from caa.synthetic import list_case_ids, load_case

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def main(min_recall: float) -> int:
    settings = get_settings()
    clients = clients_from_settings(settings, DefaultAzureCredential())
    criteria = load_criteria()
    reports: list[RecallReport] = []
    rejected_total = 0

    for case_id in list_case_ids():
        case = load_case(case_id)
        chunks = list_case_chunks(clients.search, case_id)
        result = extract_facts(
            clients.openai,
            settings.chat_model_deployment,
            criteria,
            case_id,
            case.assessment_type,
            chunks,
        )
        report = score_recall(case_id, case.expected_facts, result.facts, case.absent_elements)
        reports.append(report)
        rejected_total += len(result.rejected)
        found, rejected = len(report.found), len(result.rejected)
        print(f"{case_id}: {found}/{report.expected} found, {rejected} rejected")
        for miss in report.missed:
            print(
                f"  missed {miss.id} {miss.element} [{miss.doc_id} p{miss.page}]: {miss.statement}"
            )
        for fill in report.false_fills:
            print(f"  FILLED A PLANTED GAP {fill}")

    expected = sum(r.expected for r in reports)
    found = sum(len(r.found) for r in reports)
    overall = found / expected
    print(f"\nOverall recall: {found}/{expected} = {overall:.2f} (gate {min_recall:.2f})")
    false_fills = sum(len(r.false_fills) for r in reports)
    print(f"Facts filling a planted gap: {false_fills} (gate 0)")
    print(f"Facts rejected by the citation and element checks: {rejected_total}")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"extraction-recall-{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "model": settings.chat_model_deployment,
                "overall_recall": overall,
                "false_fills": false_fills,
                "rejected": rejected_total,
                "cases": [r.model_dump() | {"recall": r.recall} for r in reports],
            },
            indent=2,
        )
    )
    print(f"Report: {out}")
    return 0 if overall >= min_recall and false_fills == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-recall", type=float, default=0.8)
    raise SystemExit(main(parser.parse_args().min_recall))
