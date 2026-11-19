from azure.ai.documentintelligence.models import AnalyzeResult

from caa.ingestion.layout import Paragraph, paragraphs_from_layout


def _para(content: str, page: int, role: str | None = None) -> dict[str, object]:
    para: dict[str, object] = {
        "content": content,
        "boundingRegions": [{"pageNumber": page, "polygon": []}],
    }
    if role:
        para["role"] = role
    return para


def test_keeps_page_numbers_and_marks_headings() -> None:
    result = AnalyzeResult(
        {
            "paragraphs": [
                _para("Intake Note", 1, "title"),
                _para("Referred by school.", 1),
                _para("Health", 2, "sectionHeading"),
                _para("Has asthma.", 2),
            ]
        }
    )
    assert paragraphs_from_layout(result) == [
        Paragraph(page=1, text="Intake Note", is_heading=True),
        Paragraph(page=1, text="Referred by school.", is_heading=False),
        Paragraph(page=2, text="Health", is_heading=True),
        Paragraph(page=2, text="Has asthma.", is_heading=False),
    ]


def test_drops_page_furniture_and_blank_paragraphs() -> None:
    result = AnalyzeResult(
        {
            "paragraphs": [
                _para("SYNTHETIC RECORD FOR DEMONSTRATION. Page 1", 1, "pageFooter"),
                _para("Header text", 1, "pageHeader"),
                _para("1", 1, "pageNumber"),
                _para("   ", 1),
                _para("Body.", 1),
            ]
        }
    )
    assert [p.text for p in paragraphs_from_layout(result)] == ["Body."]


def test_empty_result() -> None:
    assert paragraphs_from_layout(AnalyzeResult({})) == []
