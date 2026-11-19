"""Group paragraphs into search chunks that never cross a page boundary.

One rule matters most here: a chunk belongs to exactly one page, so a citation
to a chunk is also a citation to a page. Inside a page we pack whole
paragraphs up to `max_chars`, and a heading always starts a new chunk, so each
chunk has a single section label.
"""

import re

from pydantic import BaseModel

from caa.ingestion.layout import Paragraph

DEFAULT_MAX_CHARS = 1200

# Search document keys allow letters, digits, underscore, dash and equals only.
_INVALID_KEY_CHARS = re.compile(r"[^A-Za-z0-9_\-=]")


class Chunk(BaseModel):
    chunk_id: str
    case_id: str
    doc_id: str
    page: int
    section: str
    text: str


def make_chunk_id(case_id: str, doc_id: str, page: int, index: int) -> str:
    """Deterministic id, so re-ingesting a document overwrites its chunks."""
    raw = f"{case_id}_{doc_id}_p{page}_c{index}"
    return _INVALID_KEY_CHARS.sub("-", raw)


def chunk_paragraphs(
    case_id: str,
    doc_id: str,
    paragraphs: list[Paragraph],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[str] = []
    page = paragraphs[0].page if paragraphs else 1
    section = ""  # most recent heading; carries over to the next page
    index_on_page = 0

    def flush() -> None:
        nonlocal index_on_page
        if buffer:
            chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(case_id, doc_id, page, index_on_page),
                    case_id=case_id,
                    doc_id=doc_id,
                    page=page,
                    section=section,
                    text="\n\n".join(buffer),
                )
            )
            buffer.clear()
            index_on_page += 1

    for para in paragraphs:
        if para.page != page:
            flush()
            page = para.page
            index_on_page = 0
        if para.is_heading:
            flush()
            section = para.text
        elif buffer and len("\n\n".join([*buffer, para.text])) > max_chars:
            flush()
        buffer.append(para.text)
    flush()

    return chunks
