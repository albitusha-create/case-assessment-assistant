"""Read the synthetic cases' metadata and ground truth (data/synthetic/source)."""

import json
from datetime import date
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
    start_date: date
    summary: str = ""
    # Elements the case deliberately leaves undocumented (planted gaps).
    absent_elements: list[str] = []
    expected_facts: list[ExpectedFact]


PAGE_MARKER = "<<<PAGE>>>"


class SourceBlock(BaseModel):
    kind: str  # "title", "heading" or "text"
    text: str


class SourcePage(BaseModel):
    """One page of a synthetic source document, as the PDF generator lays it out."""

    doc_id: str
    page: int
    page_count: int
    blocks: list[SourceBlock]


def list_source_docs(case_id: str, source_dir: Path = SYNTHETIC_SOURCE_DIR) -> list[str]:
    return sorted(p.stem for p in (source_dir / case_id).glob("*.md") if p.stem != "README")


def load_source_page(
    case_id: str, doc_id: str, page: int, source_dir: Path = SYNTHETIC_SOURCE_DIR
) -> SourcePage | None:
    """The text of one cited page, so a reviewer can check a citation.

    The PDFs in data/synthetic/cases are rendered from these files, one page per
    `<<<PAGE>>>` marker, so page numbers match the citations. Only documents that
    exist in the case folder are read (the id is never used to build a free path).
    """
    if doc_id not in list_source_docs(case_id, source_dir):
        return None
    pages = (source_dir / case_id / f"{doc_id}.md").read_text().split(PAGE_MARKER)
    if not 1 <= page <= len(pages):
        return None
    blocks = []
    for raw in pages[page - 1].strip().split("\n\n"):
        first, _, rest = raw.strip().partition("\n")
        if first.startswith("## "):
            blocks.append(SourceBlock(kind="heading", text=first[3:]))
        elif first.startswith("# "):
            blocks.append(SourceBlock(kind="title", text=first[2:]))
        else:
            rest = f"{first}\n{rest}".strip()
        if rest.strip():
            blocks.append(SourceBlock(kind="text", text=rest.strip()))
    return SourcePage(doc_id=doc_id, page=page, page_count=len(pages), blocks=blocks)


def load_case(case_id: str, source_dir: Path = SYNTHETIC_SOURCE_DIR) -> SyntheticCase:
    raw = json.loads((source_dir / case_id / "case.json").read_text())
    return SyntheticCase.model_validate(raw)


def list_case_ids(source_dir: Path = SYNTHETIC_SOURCE_DIR) -> list[str]:
    return sorted(p.parent.name for p in source_dir.glob("case-*/case.json"))
