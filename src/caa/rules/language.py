"""Flag language that reads as a determination the AI must not make."""

import re

from pydantic import BaseModel

from caa.models import Draft


class ProhibitedMatch(BaseModel):
    section_id: str
    claim_index: int
    phrase: str
    text: str


def check_prohibited_language(draft: Draft, phrases: list[str]) -> list[ProhibitedMatch]:
    """Case-insensitive whole-phrase matches of prohibited phrases in each claim."""
    patterns = [
        (phrase, re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)) for phrase in phrases
    ]
    matches: list[ProhibitedMatch] = []
    for section in draft.sections:
        for index, claim in enumerate(section.claims):
            for phrase, pattern in patterns:
                if pattern.search(claim.text):
                    matches.append(
                        ProhibitedMatch(
                            section_id=section.id, claim_index=index, phrase=phrase, text=claim.text
                        )
                    )
    return matches
