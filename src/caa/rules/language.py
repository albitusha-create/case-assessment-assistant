"""Flag language that reads as a determination the AI must not make."""

import re

from pydantic import BaseModel

from caa.models import Draft


class ProhibitedMatch(BaseModel):
    section_id: str
    claim_index: int
    phrase: str
    text: str


def find_prohibited_phrases(text: str, phrases: list[str]) -> list[str]:
    """Prohibited phrases found in `text`, case-insensitive whole phrases, in list order."""
    return [
        phrase for phrase in phrases if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE)
    ]


def check_prohibited_language(draft: Draft, phrases: list[str]) -> list[ProhibitedMatch]:
    """Case-insensitive whole-phrase matches of prohibited phrases in each claim."""
    matches: list[ProhibitedMatch] = []
    for section in draft.sections:
        for index, claim in enumerate(section.claims):
            for phrase in find_prohibited_phrases(claim.text, phrases):
                matches.append(
                    ProhibitedMatch(
                        section_id=section.id, claim_index=index, phrase=phrase, text=claim.text
                    )
                )
    return matches
