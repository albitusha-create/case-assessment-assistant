from caa.ingestion.chunking import chunk_paragraphs, make_chunk_id
from caa.ingestion.layout import Paragraph


def body(page: int, text: str) -> Paragraph:
    return Paragraph(page=page, text=text, is_heading=False)


def heading(page: int, text: str) -> Paragraph:
    return Paragraph(page=page, text=text, is_heading=True)


def test_chunks_never_cross_a_page() -> None:
    chunks = chunk_paragraphs("case-001", "doc", [body(1, "a"), body(2, "b"), body(2, "c")])
    assert [(c.page, c.text) for c in chunks] == [(1, "a"), (2, "b\n\nc")]


def test_heading_starts_new_chunk_and_sets_section() -> None:
    paragraphs = [heading(1, "Referral"), body(1, "a"), heading(1, "Health"), body(1, "b")]
    chunks = chunk_paragraphs("case-001", "doc", paragraphs)
    assert [(c.section, c.text) for c in chunks] == [
        ("Referral", "Referral\n\na"),
        ("Health", "Health\n\nb"),
    ]


def test_section_carries_over_to_next_page() -> None:
    chunks = chunk_paragraphs(
        "case-001", "doc", [heading(1, "History"), body(1, "a"), body(2, "b")]
    )
    assert chunks[1].page == 2
    assert chunks[1].section == "History"


def test_long_page_splits_on_paragraph_boundaries() -> None:
    paragraphs = [body(1, "x" * 50), body(1, "y" * 50), body(1, "z" * 50)]
    chunks = chunk_paragraphs("case-001", "doc", paragraphs, max_chars=110)
    assert [c.text for c in chunks] == ["x" * 50 + "\n\n" + "y" * 50, "z" * 50]
    assert [c.chunk_id for c in chunks] == ["case-001_doc_p1_c0", "case-001_doc_p1_c1"]


def test_chunk_ids_are_deterministic_and_key_safe() -> None:
    assert make_chunk_id("case-001", "intake note.v2", 3, 0) == "case-001_intake-note-v2_p3_c0"
    first = chunk_paragraphs("case-001", "doc", [body(1, "a")])
    second = chunk_paragraphs("case-001", "doc", [body(1, "a")])
    assert first == second


def test_no_paragraphs_means_no_chunks() -> None:
    assert chunk_paragraphs("case-001", "doc", []) == []
