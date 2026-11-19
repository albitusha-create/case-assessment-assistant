"""Score extracted facts against a case's ground truth.

A planted fact counts as found when some extracted fact has the same element
and cites the same document and page. Wording is not compared: that needs a
judge model and comes with the groundedness evals.
"""

from pydantic import BaseModel

from caa.extraction.schema import Fact
from caa.synthetic import ExpectedFact


class RecallReport(BaseModel):
    case_id: str
    expected: int
    found: list[str]
    missed: list[ExpectedFact]

    @property
    def recall(self) -> float:
        return len(self.found) / self.expected if self.expected else 1.0


def score_recall(case_id: str, expected: list[ExpectedFact], facts: list[Fact]) -> RecallReport:
    extracted = {(f.element, f.citation.doc_id, f.citation.page) for f in facts}
    found = [e.id for e in expected if (e.element, e.doc_id, e.page) in extracted]
    missed = [e for e in expected if e.id not in found]
    return RecallReport(case_id=case_id, expected=len(expected), found=found, missed=missed)
