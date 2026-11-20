from caa.models import Claim, Draft, DraftSection
from caa.rules import check_citation_coverage, validate_citations
from tests.unit.conftest import cite


def _draft(*claims: Claim) -> Draft:
    return Draft(
        case_id="case-001",
        assessment_type="initial_assessment",
        sections=[DraftSection(id="presenting_concerns", title="Presenting", claims=list(claims))],
    )


def test_full_coverage(complete_draft: Draft) -> None:
    result = check_citation_coverage(complete_draft)
    assert result.coverage == 1.0
    assert result.uncited == []


def test_uncited_claims_are_listed() -> None:
    draft = _draft(
        Claim(text="Cited.", citations=[cite()]),
        Claim(text="Not cited."),
    )
    result = check_citation_coverage(draft)
    assert result.total_claims == 2
    assert result.coverage == 0.5
    assert [ref.text for ref in result.uncited] == ["Not cited."]
    assert result.uncited[0].claim_index == 1


def test_empty_draft_has_full_coverage() -> None:
    assert check_citation_coverage(_draft()).coverage == 1.0


def test_citation_to_unknown_chunk_is_invalid() -> None:
    draft = _draft(Claim(text="A.", citations=[cite("real"), cite("invented")]))
    invalid = validate_citations(draft, known_chunk_ids={"real"})
    assert [i.chunk_id for i in invalid] == ["invented"]


def test_all_citations_valid() -> None:
    draft = _draft(Claim(text="A.", citations=[cite("real")]))
    assert validate_citations(draft, known_chunk_ids={"real"}) == []


def test_gap_statements_are_not_counted_as_uncited() -> None:
    gap = Claim(
        text="No prior services are documented.", elements=["information_gaps", "prior_services"]
    )
    fact = Claim(text="Lives alone.", citations=[cite()], elements=["living_situation"])
    draft = Draft(
        case_id="case-003",
        assessment_type="initial_assessment",
        sections=[DraftSection(id="s", title="S", claims=[gap, fact])],
    )
    result = check_citation_coverage(draft)
    assert (result.total_claims, result.coverage) == (1, 1.0)
