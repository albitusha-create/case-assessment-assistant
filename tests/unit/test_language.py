from caa.models import Claim, Draft, DraftSection
from caa.rules import Criteria, check_prohibited_language


def _draft(text: str) -> Draft:
    return Draft(
        case_id="case-001",
        assessment_type="initial_assessment",
        sections=[
            DraftSection(id="summary_considerations", title="Summary", claims=[Claim(text=text)])
        ],
    )


def test_determination_language_is_flagged(criteria: Criteria) -> None:
    matches = check_prohibited_language(
        _draft("Based on the records, the client Is Eligible for services."),
        criteria.checklist.prohibited_phrases,
    )
    assert [m.phrase for m in matches] == ["is eligible"]


def test_neutral_language_passes(criteria: Criteria) -> None:
    text = "Staff may wish to review eligibility documentation, which is not yet in the file."
    assert check_prohibited_language(_draft(text), criteria.checklist.prohibited_phrases) == []


def test_whole_phrase_only() -> None:
    # "is eligible" must not match inside "this eligible" or similar partial words.
    assert check_prohibited_language(_draft("This eligibleness is odd."), ["is eligible"]) == []
