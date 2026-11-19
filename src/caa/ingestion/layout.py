"""Turn a PDF into page-numbered paragraphs with Document Intelligence.

We use the prebuilt `layout` model because it returns each paragraph with the
page it came from and a role (title, sectionHeading, pageFooter, ...). The page
number is what makes page-level citations possible later.
"""

from dataclasses import dataclass

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult

# Repeated boilerplate on every page adds noise to search, so we drop it.
SKIPPED_ROLES = {"pageHeader", "pageFooter", "pageNumber"}
HEADING_ROLES = {"title", "sectionHeading"}


@dataclass(frozen=True)
class Paragraph:
    page: int
    text: str
    is_heading: bool


def paragraphs_from_layout(result: AnalyzeResult) -> list[Paragraph]:
    """Keep body and heading paragraphs, in reading order, with their page."""
    paragraphs: list[Paragraph] = []
    for para in result.paragraphs or []:
        if para.role in SKIPPED_ROLES or not para.bounding_regions:
            continue
        text = para.content.strip()
        if not text:
            continue
        paragraphs.append(
            Paragraph(
                page=para.bounding_regions[0].page_number,
                text=text,
                is_heading=para.role in HEADING_ROLES,
            )
        )
    return paragraphs


def analyze_layout(client: DocumentIntelligenceClient, pdf_bytes: bytes) -> list[Paragraph]:
    """Call the layout model and wait for the result (a long-running operation)."""
    poller = client.begin_analyze_document(
        "prebuilt-layout", AnalyzeDocumentRequest(bytes_source=pdf_bytes)
    )
    return paragraphs_from_layout(poller.result())
