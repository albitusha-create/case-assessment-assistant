"""Publish the agents to Foundry, or run a synthetic case through the workflow.

uv run python -m caa.agents publish
uv run python -m caa.agents draft case-002     # extract and draft
uv run python -m caa.agents review case-002    # extract, draft and QA
"""

import argparse
from datetime import date

from caa.agents.definitions import publish_agents
from caa.agents.pipeline import run_case, services_from_settings
from caa.config import get_settings
from caa.models import Draft
from caa.qa.report import QAReport
from caa.synthetic import load_case


def print_draft(draft: Draft) -> None:
    for section in draft.sections:
        print(f"\n## {section.title}")
        for claim in section.claims:
            cites = ", ".join(f"{c.doc_id} p{c.page}" for c in claim.citations) or "no citation"
            print(f"- {claim.text}  [{cites}] ({', '.join(claim.elements)})")


def print_report(report: QAReport) -> None:
    print(f"\n# QA report (checklist {report.checklist_version})")
    for result in report.results:
        status = "PASS" if result.passed else f"FAIL ({result.severity})"
        print(f"{status:<18} {result.item_id} [{result.checked_by}]")
        for finding in result.findings:
            print(f"    - {finding}")
    for gap in report.acknowledged_gaps:
        print(f"Known gap: {gap.element} ({gap.section_id})")
    verdict = "can be approved" if report.can_approve else "is BLOCKED"
    blocking, warnings = len(report.blocking_failures), len(report.warnings)
    print(f"\nDraft {verdict}: {blocking} blocking, {warnings} warnings")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m caa.agents")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("publish", help="create a new version of each agent in Foundry")
    for name in ("draft", "review"):
        command = commands.add_parser(name, help=f"{name} one synthetic case")
        command.add_argument("case_id")
    args = parser.parse_args()

    settings = get_settings()
    services = services_from_settings(settings)

    if args.command == "publish":
        for label in publish_agents(services.project, settings.chat_model_deployment):
            print(f"Published {label}")
        return

    run = run_case(
        services, load_case(args.case_id), date.today(), with_qa=args.command == "review"
    )
    print(f"Extracted {len(run.facts.facts)} facts")
    print_draft(run.drafted.draft)
    if run.drafted.dropped_citations:
        print(f"\nDropped citations to unknown chunks: {run.drafted.dropped_citations}")
    if run.report is not None:
        print_report(run.report)


if __name__ == "__main__":
    main()
