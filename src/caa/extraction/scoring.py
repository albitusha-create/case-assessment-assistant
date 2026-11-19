"""Score extracted facts against a case's ground truth.

Recall: a planted fact counts as found when some extracted fact carries its
element and cites the same document and page. Wording is not compared: that
needs a judge model and comes with the groundedness evals.

False fills: facts labeled with an element the case deliberately leaves out.
These matter more than misses, because they would hide a real information gap
from the QA step.
"""

from pydantic import BaseModel

from caa.extraction.schema import Fact
from caa.synthetic import ExpectedFact


class RecallReport(BaseModel):
    case_id: str
    expected: int
    found: list[str]
    missed: list[ExpectedFact]
    false_fills: list[str]

    @property
    def recall(self) -> float:
        return len(self.found) / self.expected if self.expected else 1.0


def score_recall(
    case_id: str,
    expected: list[ExpectedFact],
    facts: list[Fact],
    absent_elements: list[str] | None = None,
) -> RecallReport:
    extracted = {(e, f.citation.doc_id, f.citation.page) for f in facts for e in f.elements}
    found = [e.id for e in expected if (e.element, e.doc_id, e.page) in extracted]
    missed = [e for e in expected if e.id not in found]

    absent = set(absent_elements or [])
    false_fills = [
        f"{', '.join(sorted(absent & set(f.elements)))}: {f.statement}"
        for f in facts
        if absent & set(f.elements)
    ]
    return RecallReport(
        case_id=case_id,
        expected=len(expected),
        found=found,
        missed=missed,
        false_fills=false_fills,
    )
