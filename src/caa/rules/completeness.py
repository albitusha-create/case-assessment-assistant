"""Required sections and required elements check."""

from pydantic import BaseModel

from caa.models import Draft
from caa.rules.criteria import SectionSpec


class MissingElement(BaseModel):
    section_id: str
    element: str


class CompletenessResult(BaseModel):
    missing_sections: list[str]
    missing_elements: list[MissingElement]
    unexpected_sections: list[str]

    @property
    def is_complete(self) -> bool:
        return not self.missing_sections and not self.missing_elements


def check_required_elements(draft: Draft, required: list[SectionSpec]) -> CompletenessResult:
    """Which required sections and elements the draft does not address.

    An element counts as addressed when at least one claim in its section is
    tagged with it. Whether the tag is honest is the QA agent's job.
    """
    draft_sections = {section.id: section for section in draft.sections}
    missing_sections: list[str] = []
    missing_elements: list[MissingElement] = []

    for spec in required:
        section = draft_sections.get(spec.id)
        if section is None:
            missing_sections.append(spec.id)
            continue
        tagged = {element for claim in section.claims for element in claim.elements}
        missing_elements.extend(
            MissingElement(section_id=spec.id, element=element)
            for element in spec.required_elements
            if element not in tagged
        )

    required_ids = {spec.id for spec in required}
    unexpected = [section_id for section_id in draft_sections if section_id not in required_ids]
    return CompletenessResult(
        missing_sections=missing_sections,
        missing_elements=missing_elements,
        unexpected_sections=unexpected,
    )
