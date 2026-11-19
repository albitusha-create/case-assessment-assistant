"""The synthetic ground truth must stay consistent with its sources and the criteria."""

import json
from pathlib import Path

import pytest

from caa.rules import Criteria, get_required_sections

SOURCE_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "source"
CASE_FILES = sorted(SOURCE_DIR.glob("case-*/case.json"))


def _page_count(doc_path: Path) -> int:
    return doc_path.read_text().count("<<<PAGE>>>") + 1


def test_there_are_synthetic_cases() -> None:
    assert len(CASE_FILES) >= 3


@pytest.mark.parametrize("case_file", CASE_FILES, ids=lambda p: p.parent.name)
def test_expected_facts_point_at_real_pages_and_elements(
    case_file: Path, criteria: Criteria
) -> None:
    case = json.loads(case_file.read_text())
    sections = get_required_sections(criteria, case["assessment_type"])
    known_elements = {e for s in sections for e in s.required_elements}

    for fact in case["expected_facts"]:
        doc = case_file.parent / f"{fact['doc_id']}.md"
        assert doc.exists(), f"{fact['id']} cites missing document {fact['doc_id']}"
        assert 1 <= fact["page"] <= _page_count(doc), f"{fact['id']} cites a page out of range"
        assert fact["element"] in known_elements, f"{fact['id']} has unknown element"


@pytest.mark.parametrize("case_file", CASE_FILES, ids=lambda p: p.parent.name)
def test_sources_are_labeled_fictional(case_file: Path) -> None:
    for doc in case_file.parent.glob("*.md"):
        assert "(fictional)" in doc.read_text(), f"{doc.name} is not labeled fictional"
