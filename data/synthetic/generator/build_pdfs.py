"""Render the synthetic case sources (Markdown-like text) into PDFs.

Each `<<<PAGE>>>` marker in a source file starts a new PDF page, so the page
numbers in `case.json` match what Document Intelligence will report.

Usage:
    uv run --group data python data/synthetic/generator/build_pdfs.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.flowables import Flowable

SYNTHETIC_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = SYNTHETIC_DIR / "source"
OUTPUT_DIR = SYNTHETIC_DIR / "cases"
PAGE_MARKER = "<<<PAGE>>>"
FOOTER = "SYNTHETIC RECORD FOR DEMONSTRATION. All people and organizations are fictional."


def to_flowables(text: str) -> list[Flowable]:
    styles = getSampleStyleSheet()
    flowables: list[Flowable] = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if block == PAGE_MARKER:
            flowables.append(PageBreak())
        elif block.startswith("# "):
            flowables.append(Paragraph(block[2:], styles["Title"]))
        elif block.startswith("## "):
            flowables.append(Paragraph(block[3:], styles["Heading2"]))
        else:
            flowables.append(Paragraph(block.replace("\n", "<br/>"), styles["BodyText"]))
            flowables.append(Spacer(1, 6))
    return flowables


def draw_footer(canvas: Canvas, doc: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(72, 40, f"{FOOTER}  Page {doc.page}")
    canvas.restoreState()


def build(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # invariant=1 makes output byte-for-byte reproducible (no timestamps).
    doc = SimpleDocTemplate(str(target), pagesize=LETTER, invariant=1, title=source.stem)
    doc.build(to_flowables(source.read_text()), onFirstPage=draw_footer, onLaterPages=draw_footer)


def main() -> None:
    for source in sorted(SOURCE_DIR.glob("case-*/*.md")):
        target = OUTPUT_DIR / source.parent.name / f"{source.stem}.pdf"
        build(source, target)
        print(f"wrote {target.relative_to(SYNTHETIC_DIR)}")


if __name__ == "__main__":
    main()
