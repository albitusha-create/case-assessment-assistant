from pathlib import Path

import pytest
from pydantic import ValidationError

import caa.rules
from caa.rules import Criteria, get_required_sections, load_criteria


def test_criteria_files_load_and_validate(criteria: Criteria) -> None:
    assert "initial_assessment" in criteria.assessment_types
    assert criteria.checklist.prohibited_phrases


def test_required_sections_are_in_order(criteria: Criteria) -> None:
    sections = get_required_sections(criteria, "initial_assessment")
    assert [s.id for s in sections] == [
        "presenting_concerns",
        "history_background",
        "current_functioning",
        "summary_considerations",
    ]


def test_unknown_assessment_type_names_known_types(criteria: Criteria) -> None:
    with pytest.raises(ValueError, match="initial_assessment"):
        get_required_sections(criteria, "made_up_type")


def test_every_rule_item_names_a_tool(criteria: Criteria) -> None:
    for item in criteria.checklist.items:
        if item.checked_by == "rule":
            assert item.tool, f"{item.id} is checked by a rule but names no tool"


def test_bad_criteria_file_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "assessment_types.yaml").write_text("version: '1'\nassessment_types: {}\n")
    (tmp_path / "qa_checklist.yaml").write_text("version: '1'\n")  # missing fields
    with pytest.raises(ValidationError):
        load_criteria(tmp_path)


def test_rule_items_name_a_real_rule_function(criteria: Criteria) -> None:
    for item in criteria.checklist.items:
        if item.checked_by == "rule":
            assert item.tool in caa.rules.__all__, f"{item.id} names unknown tool {item.tool}"


def test_checklist_ids_are_unique(criteria: Criteria) -> None:
    ids = [item.id for item in criteria.checklist.items]
    assert len(ids) == len(set(ids))
