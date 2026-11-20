"""The JSON shapes the Drafting and QA agents must return.

Every field is required and extra keys are forbidden, so the schema works with
strict structured output. The agent cites chunk ids only; our code looks up the
document and page, exactly as in extraction.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelClaim(_Strict):
    # "gap" means the claim says something is NOT documented. The model only
    # classifies; code applies the gap rules (see orchestrator.to_claim).
    kind: Literal["fact", "gap"]
    text: str
    elements: list[str]
    chunk_ids: list[str]


class ModelSection(_Strict):
    id: str
    title: str
    claims: list[ModelClaim]


class DraftOutput(_Strict):
    sections: list[ModelSection]


def draft_json_schema() -> dict[str, Any]:
    return DraftOutput.model_json_schema()


class QAFinding(_Strict):
    item_id: str
    passed: bool
    details: list[str]


class QAOutput(_Strict):
    findings: list[QAFinding]


def qa_json_schema() -> dict[str, Any]:
    return QAOutput.model_json_schema()
