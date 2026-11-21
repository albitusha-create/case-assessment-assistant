"""The assessment form the mock agency portal owns.

A generic adult core psychosocial assessment: a header, then one narrative per
life domain. The portal publishes this schema so a client (our assistant, or an
MCP tool) can map onto it without guessing field names.

`assistant_may_prefill` is the portal's own rule, enforced when a draft is
saved: clinical domains and the person's own self-rating are never pre-filled
by software, whatever the caller sends.
"""

from typing import Literal

from pydantic import BaseModel

FORM_ID = "core-assessment"
FORM_VERSION = "1.0"

PortalAssessmentType = Literal["initial", "update", "annual_review"]
FilledBy = Literal["worker", "clinician"]


class Domain(BaseModel):
    id: str
    title: str
    guidance: str
    filled_by: FilledBy = "worker"
    assistant_may_prefill: bool = True


class InformationSource(BaseModel):
    id: str
    label: str


class FormSchema(BaseModel):
    form_id: str = FORM_ID
    version: str = FORM_VERSION
    title: str = "Core Assessment"
    assessment_types: dict[PortalAssessmentType, str]
    information_sources: list[InformationSource]
    domains: list[Domain]

    def domain(self, domain_id: str) -> Domain | None:
        return next((d for d in self.domains if d.id == domain_id), None)


SCHEMA = FormSchema(
    assessment_types={
        "initial": "Initial: first assessment since the current program start date",
        "update": "Update: changes made between annual reviews",
        "annual_review": "Annual review: completed at yearly renewal",
    },
    information_sources=[
        InformationSource(id="person_interview", label="Interview with the person"),
        InformationSource(id="internal_records", label="Earlier records held by this agency"),
        InformationSource(id="external_records", label="Records from other providers or schools"),
        InformationSource(id="collateral_contacts", label="Family or other contacts interviewed"),
    ],
    domains=[
        Domain(
            id="strengths",
            title="Strengths",
            guidance="Strengths the person names, strengths staff have seen, and strengths "
            "others describe. These feed the goals in the service plan.",
        ),
        Domain(
            id="life_satisfaction",
            title="Life satisfaction and goals",
            guidance="The person's own hopes and goals, what they have achieved, and their "
            "self-rating from 1 to 10. Ask in the conversation.",
            assistant_may_prefill=False,
        ),
        Domain(
            id="basic_needs",
            title="Basic needs",
            guidance="How food, shelter, clothing and safety are met today, and whether the "
            "person feels those needs are met.",
        ),
        Domain(
            id="social_network_family",
            title="Social network and family",
            guidance="Family and friends, now and in the past: who matters to the person, "
            "who helps, and which relationships are hard.",
        ),
        Domain(
            id="community_living",
            title="Community living, housing and daily living skills",
            guidance="Where and with whom the person lives, a typical day, and how they "
            "manage daily tasks such as laundry, cleaning and transportation.",
        ),
        Domain(
            id="employment_education",
            title="Employment and education",
            guidance="School history and any education plan, work history and volunteering.",
        ),
        Domain(
            id="physical_health",
            title="Physical health",
            guidance="Current and past physical health issues, including early "
            "developmental concerns.",
        ),
        Domain(
            id="finances_benefits",
            title="Finances and benefits",
            guidance="Income, benefits and other help with money, and how the person "
            "manages their finances.",
        ),
        Domain(
            id="legal_status",
            title="Legal status",
            guidance="Current or past court involvement, custody matters and protective orders.",
        ),
        Domain(
            id="mental_health",
            title="Mental health",
            guidance="History, current services and diagnosis. Completed by the clinician.",
            filled_by="clinician",
            assistant_may_prefill=False,
        ),
        Domain(
            id="substance_use",
            title="Substance use",
            guidance="Current and past use. Completed by the clinician.",
            filled_by="clinician",
            assistant_may_prefill=False,
        ),
        Domain(
            id="trauma_stressors",
            title="Trauma and significant life stressors",
            guidance="Completed by the clinician.",
            filled_by="clinician",
            assistant_may_prefill=False,
        ),
    ],
)
