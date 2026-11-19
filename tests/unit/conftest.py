import pytest

from caa.models import Citation, Claim, Draft, DraftSection
from caa.rules import Criteria, load_criteria


@pytest.fixture(scope="session")
def criteria() -> Criteria:
    return load_criteria()


def cite(chunk_id: str = "c1", page: int = 1) -> Citation:
    return Citation(chunk_id=chunk_id, doc_id="doc-1", page=page)


@pytest.fixture
def complete_draft() -> Draft:
    """A small initial assessment that satisfies every required element."""

    def section(section_id: str, elements: list[str]) -> DraftSection:
        claims = [
            Claim(
                text=f"Statement about {element}.",
                citations=[cite(f"{element}-chunk")],
                elements=[element],
            )
            for element in elements
        ]
        return DraftSection(id=section_id, title=section_id, claims=claims)

    return Draft(
        case_id="case-001",
        assessment_type="initial_assessment",
        sections=[
            section(
                "presenting_concerns",
                ["referral_source", "reason_for_referral", "client_stated_needs"],
            ),
            section(
                "history_background",
                [
                    "prior_services",
                    "family_social_history",
                    "health_history",
                    "substance_use_history",
                ],
            ),
            section(
                "current_functioning",
                ["living_situation", "education_or_employment", "natural_supports", "strengths"],
            ),
            section(
                "summary_considerations",
                ["summary", "information_gaps", "considerations_for_staff"],
            ),
        ],
    )
