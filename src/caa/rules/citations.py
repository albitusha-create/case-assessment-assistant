"""Citation coverage and citation validity checks."""

from collections.abc import Set

from pydantic import BaseModel

from caa.models import Draft


class ClaimRef(BaseModel):
    section_id: str
    claim_index: int
    text: str


class CoverageResult(BaseModel):
    total_claims: int
    cited_claims: int
    coverage: float  # 0.0 to 1.0; 1.0 for an empty draft (nothing uncited)
    uncited: list[ClaimRef]


class InvalidCitation(BaseModel):
    section_id: str
    claim_index: int
    chunk_id: str


def check_citation_coverage(draft: Draft) -> CoverageResult:
    """Share of claims that carry at least one citation, and which ones do not."""
    uncited: list[ClaimRef] = []
    total = 0
    for section in draft.sections:
        for index, claim in enumerate(section.claims):
            total += 1
            if not claim.citations:
                uncited.append(ClaimRef(section_id=section.id, claim_index=index, text=claim.text))
    cited = total - len(uncited)
    coverage = 1.0 if total == 0 else cited / total
    return CoverageResult(
        total_claims=total, cited_claims=cited, coverage=coverage, uncited=uncited
    )


def validate_citations(draft: Draft, known_chunk_ids: Set[str]) -> list[InvalidCitation]:
    """Citations whose chunk is not in this case's index (made up, or from another case)."""
    invalid: list[InvalidCitation] = []
    for section in draft.sections:
        for index, claim in enumerate(section.claims):
            for citation in claim.citations:
                if citation.chunk_id not in known_chunk_ids:
                    invalid.append(
                        InvalidCitation(
                            section_id=section.id, claim_index=index, chunk_id=citation.chunk_id
                        )
                    )
    return invalid
