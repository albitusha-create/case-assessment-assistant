"""The JSON shape the Drafting agent must return.

Every field is required and extra keys are forbidden, so the schema works with
strict structured output. The agent cites chunk ids only; our code looks up the
document and page, exactly as in extraction.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelClaim(_Strict):
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
