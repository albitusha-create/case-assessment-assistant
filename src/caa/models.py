"""Shared data models. A draft is a list of sections, each a list of cited claims."""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Points a claim at one indexed chunk of a source document."""

    chunk_id: str
    doc_id: str
    page: int = Field(ge=1)


class Claim(BaseModel):
    """One sentence or short statement in a draft section."""

    text: str
    citations: list[Citation] = Field(default_factory=list)
    # Required elements this claim addresses, tagged by the drafting agent and
    # verified by rules (presence) and the QA agent (honesty of the tag).
    elements: list[str] = Field(default_factory=list)


class DraftSection(BaseModel):
    id: str
    title: str
    claims: list[Claim] = Field(default_factory=list)


class Draft(BaseModel):
    case_id: str
    assessment_type: str
    sections: list[DraftSection] = Field(default_factory=list)
