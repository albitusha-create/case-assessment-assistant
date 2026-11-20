"""Run the checklist items marked `checked_by: rule`.

Each item names a function in caa.rules. Here we call it and turn its result
into pass or fail plus readable findings. No LLM is involved.
"""

from collections.abc import Set
from datetime import date

from caa.models import Draft
from caa.qa.report import CheckResult
from caa.rules import (
    Criteria,
    calculate_due_date,
    check_citation_coverage,
    check_prohibited_language,
    check_required_elements,
    get_required_sections,
    validate_citations,
)
from caa.rules.completeness import CompletenessResult
from caa.rules.criteria import ChecklistItem


def _sections_present(result: CompletenessResult) -> list[str]:
    return [f"Missing section: {s}" for s in result.missing_sections]


def _elements_present(result: CompletenessResult) -> list[str]:
    return [f"Missing element: {m.element} ({m.section_id})" for m in result.missing_elements]


def run_rule_checks(
    criteria: Criteria,
    draft: Draft,
    known_chunk_ids: Set[str],
    start_date: date,
    today: date,
) -> tuple[list[CheckResult], CompletenessResult]:
    """Results for every rule item, in checklist order, plus the completeness detail."""
    assessment = criteria.assessment_types[draft.assessment_type]
    completeness = check_required_elements(
        draft, get_required_sections(criteria, draft.assessment_type)
    )
    coverage = check_citation_coverage(draft)
    min_coverage = criteria.checklist.thresholds.min_citation_coverage
    due = calculate_due_date(start_date, assessment.due, today, criteria.holidays)

    findings_by_item: dict[str, list[str]] = {
        "required_sections_present": _sections_present(completeness),
        "required_elements_present": _elements_present(completeness),
        "completed_by_due_date": (
            [f"Overdue: due {due.due_date}, {-due.days_remaining} days ago"]
            if due.is_overdue
            else []
        ),
        "citation_coverage": (
            [f"Uncited claim ({u.section_id}): {u.text}" for u in coverage.uncited]
            if coverage.coverage < min_coverage
            else []
        ),
        "citations_resolve": [
            f"Unknown chunk {c.chunk_id} ({c.section_id})"
            for c in validate_citations(draft, known_chunk_ids)
        ],
        "no_determinations": [
            f'"{m.phrase}" in {m.section_id}: {m.text}'
            for m in check_prohibited_language(draft, criteria.checklist.prohibited_phrases)
        ],
    }

    results = [
        _result(item, findings_by_item[item.id])
        for item in criteria.checklist.items
        if item.checked_by == "rule"
    ]
    return results, completeness


def _result(item: ChecklistItem, findings: list[str]) -> CheckResult:
    return CheckResult(
        item_id=item.id,
        description=item.description,
        checked_by=item.checked_by,
        severity=item.severity,
        passed=not findings,
        findings=findings,
    )
