"""Read the synthetic cases' metadata and ground truth (data/synthetic/source)."""

import json
from pathlib import Path

from pydantic import BaseModel

SYNTHETIC_SOURCE_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "source"


class ExpectedFact(BaseModel):
    id: str
    element: str
    statement: str
    doc_id: str
    page: int


class SyntheticCase(BaseModel):
    case_id: str
    assessment_type: str
    # Elements the case deliberately leaves undocumented (planted gaps).
    absent_elements: list[str] = []
    expected_facts: list[ExpectedFact]


def load_case(case_id: str, source_dir: Path = SYNTHETIC_SOURCE_DIR) -> SyntheticCase:
    raw = json.loads((source_dir / case_id / "case.json").read_text())
    return SyntheticCase.model_validate(raw)


def list_case_ids(source_dir: Path = SYNTHETIC_SOURCE_DIR) -> list[str]:
    return sorted(p.parent.name for p in source_dir.glob("case-*/case.json"))
