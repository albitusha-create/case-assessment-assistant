"""Required sections and required elements check."""

from pydantic import BaseModel

from caa.models import GAP_ELEMENT, Draft
from caa.rules.criteria import SectionSpec


class MissingElement(BaseModel):
    section_id: str
    element: str


class CompletenessResult(BaseModel):
    missing_sections: list[str]
    missing_elements: list[MissingElement]
    # Elements no fact covers, but that a gap statement names. Shown to the
    # reviewer as known gaps; they do not block approval.
    acknowledged_gaps: list[MissingElement]
    unexpected_sections: list[str]

    @property
    def is_complete(self) -> bool:
        return not self.missing_sections and not self.missing_elements


def check_required_elements(draft: Draft, required: list[SectionSpec]) -> CompletenessResult:
    """Which required sections and elements the draft does not address.

    An element counts as addressed when at least one cited claim in its section
    is tagged with it. An element that only a gap statement names (anywhere in
    the draft) is an acknowledged gap. Whether tags are honest is the QA
    agent's job.
    """
    draft_sections = {section.id: section for section in draft.sections}
    gap_elements = {
        element
        for section in draft.sections
        for claim in section.claims
        if claim.is_gap_statement
        for element in claim.elements
        if element != GAP_ELEMENT
    }
    missing_sections: list[str] = []
    missing_elements: list[MissingElement] = []
    acknowledged: list[MissingElement] = []

    for spec in required:
        section = draft_sections.get(spec.id)
        if section is None:
            missing_sections.append(spec.id)
            continue
        # Gap statements address only the information_gaps element itself.
        tagged = {
            element
            for claim in section.claims
            for element in ([GAP_ELEMENT] if claim.is_gap_statement else claim.elements)
        }
        for element in spec.required_elements:
            if element in tagged:
                continue
            missing = MissingElement(section_id=spec.id, element=element)
            (acknowledged if element in gap_elements else missing_elements).append(missing)

    required_ids = {spec.id for spec in required}
    unexpected = [section_id for section_id in draft_sections if section_id not in required_ids]
    return CompletenessResult(
        missing_sections=missing_sections,
        missing_elements=missing_elements,
        acknowledged_gaps=acknowledged,
        unexpected_sections=unexpected,
    )
