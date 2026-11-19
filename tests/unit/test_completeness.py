from caa.models import Draft
from caa.rules import Criteria, check_required_elements, get_required_sections


def test_complete_draft_passes(criteria: Criteria, complete_draft: Draft) -> None:
    required = get_required_sections(criteria, "initial_assessment")
    result = check_required_elements(complete_draft, required)
    assert result.is_complete
    assert result.unexpected_sections == []


def test_missing_section_is_reported(criteria: Criteria, complete_draft: Draft) -> None:
    complete_draft.sections = [s for s in complete_draft.sections if s.id != "history_background"]
    required = get_required_sections(criteria, "initial_assessment")
    result = check_required_elements(complete_draft, required)
    assert result.missing_sections == ["history_background"]
    assert not result.is_complete


def test_missing_element_is_reported(criteria: Criteria, complete_draft: Draft) -> None:
    functioning = next(s for s in complete_draft.sections if s.id == "current_functioning")
    functioning.claims = [c for c in functioning.claims if "strengths" not in c.elements]
    required = get_required_sections(criteria, "initial_assessment")
    result = check_required_elements(complete_draft, required)
    assert [(m.section_id, m.element) for m in result.missing_elements] == [
        ("current_functioning", "strengths")
    ]


def test_extra_section_is_flagged_not_failed(criteria: Criteria, complete_draft: Draft) -> None:
    complete_draft.sections.append(complete_draft.sections[0].model_copy(update={"id": "extra"}))
    required = get_required_sections(criteria, "initial_assessment")
    result = check_required_elements(complete_draft, required)
    assert result.is_complete
    assert result.unexpected_sections == ["extra"]
