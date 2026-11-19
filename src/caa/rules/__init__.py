"""Deterministic business rules. Pure functions, no I/O except reading criteria files.

The agents call these as function tools. Anything a reviewer could ask "why"
about lives here, with a unit test, not in a prompt.
"""

from caa.rules.citations import (
    CoverageResult,
    InvalidCitation,
    check_citation_coverage,
    validate_citations,
)
from caa.rules.completeness import CompletenessResult, check_required_elements
from caa.rules.criteria import (
    AssessmentType,
    Criteria,
    SectionSpec,
    get_required_sections,
    load_criteria,
)
from caa.rules.due_dates import DueDateResult, calculate_due_date
from caa.rules.language import ProhibitedMatch, check_prohibited_language

__all__ = [
    "AssessmentType",
    "CompletenessResult",
    "CoverageResult",
    "Criteria",
    "DueDateResult",
    "InvalidCitation",
    "ProhibitedMatch",
    "SectionSpec",
    "calculate_due_date",
    "check_citation_coverage",
    "check_prohibited_language",
    "check_required_elements",
    "get_required_sections",
    "load_criteria",
    "validate_citations",
]
