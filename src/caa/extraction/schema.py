"""Shapes for fact extraction.

`ModelFact` / `ModelOutput` are what the LLM must return (structured output).
`Fact` is what the rest of the app uses, after our code has checked the
model's chunk id and filled in the document and page from the index.
"""

from pydantic import BaseModel

from caa.models import Citation


class ModelFact(BaseModel):
    # A fact can support several elements, for example school absences are
    # both the reason for referral and part of education history.
    elements: list[str]
    statement: str
    chunk_id: str


class ModelOutput(BaseModel):
    facts: list[ModelFact]


class Fact(BaseModel):
    elements: list[str]
    statement: str
    citation: Citation


class RejectedFact(BaseModel):
    fact: ModelFact
    reason: str


class ExtractionResult(BaseModel):
    case_id: str
    facts: list[Fact]
    rejected: list[RejectedFact]
