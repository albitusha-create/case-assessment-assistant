"""Load and validate the criteria YAML files into typed models."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

DEFAULT_CRITERIA_DIR = Path(__file__).resolve().parents[3] / "criteria"


class DueRule(BaseModel):
    days: int = Field(gt=0)
    day_type: Literal["calendar", "business"]
    starts_from: str


class SectionSpec(BaseModel):
    id: str
    title: str
    required_elements: list[str]


class AssessmentType(BaseModel):
    label: str
    due: DueRule
    sections: list[SectionSpec]


class ChecklistItem(BaseModel):
    id: str
    description: str
    checked_by: Literal["rule", "agent"]
    tool: str | None = None
    severity: Literal["blocking", "warning"]


class Thresholds(BaseModel):
    min_citation_coverage: float = Field(ge=0.0, le=1.0)


class QAChecklist(BaseModel):
    version: str
    thresholds: Thresholds
    items: list[ChecklistItem]
    prohibited_phrases: list[str]


class Criteria(BaseModel):
    version: str
    assessment_types: dict[str, AssessmentType]
    element_definitions: dict[str, str] = Field(default_factory=dict)
    holidays: list[date] = Field(default_factory=list)
    checklist: QAChecklist


def load_criteria(criteria_dir: Path = DEFAULT_CRITERIA_DIR) -> Criteria:
    """Read both YAML files and validate them. Fails loudly on a bad file."""
    types_raw = yaml.safe_load((criteria_dir / "assessment_types.yaml").read_text())
    checklist_raw = yaml.safe_load((criteria_dir / "qa_checklist.yaml").read_text())
    return Criteria.model_validate({**types_raw, "checklist": checklist_raw})


def get_required_sections(criteria: Criteria, assessment_type: str) -> list[SectionSpec]:
    """Ordered required sections for an assessment type."""
    try:
        return criteria.assessment_types[assessment_type].sections
    except KeyError:
        known = ", ".join(sorted(criteria.assessment_types))
        raise ValueError(f"Unknown assessment type '{assessment_type}'. Known: {known}") from None
