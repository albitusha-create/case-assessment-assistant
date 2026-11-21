"""Map an approved draft onto the portal's core assessment form.

Deterministic code, no model call: each claim goes to a form domain by the
elements the drafting agent tagged (and the rules verified). The table below is
the whole mapping, so a reviewer can check it line by line.

- Claims for worker domains become pre-filled text, with their citations.
- Claims for clinical topics become reference notes beside the clinician's
  field. They never fill it: the portal refuses that, and so do we.
- Gap statements and the summary are not copied. Instead, every worker domain
  left empty is listed as a topic to ask about in the interview.
"""

from datetime import date

from caa.models import Claim, Draft
from caa.portal.form import FormSchema
from caa.portal.store import (
    ASSESSMENT_TYPE_MAP,
    DomainPrefill,
    DraftIn,
    HeaderPrefill,
    PortalCase,
    ReferenceNote,
    SourceRef,
)

# Our criteria element -> the portal domain it pre-fills. An element can fill two.
ELEMENT_TO_DOMAINS: dict[str, tuple[str, ...]] = {
    "strengths": ("strengths",),
    "client_stated_needs": ("basic_needs",),
    "living_situation": ("community_living", "basic_needs"),
    "changes_in_circumstances": ("community_living",),
    "family_social_history": ("social_network_family",),
    "natural_supports": ("social_network_family",),
    "education_or_employment": ("employment_education",),
    "health_history": ("physical_health",),
}

# Our criteria element -> the clinician's domain where it is shown as a reference.
ELEMENT_TO_REFERENCE: dict[str, str] = {
    "reason_for_referral": "mental_health",
    "prior_services": "mental_health",
    "services_received": "mental_health",
    "substance_use_history": "substance_use",
}


def _sources(claims: list[Claim]) -> list[SourceRef]:
    seen: dict[tuple[str, int], SourceRef] = {}
    for claim in claims:
        for c in claim.citations:
            seen.setdefault((c.doc_id, c.page), SourceRef(doc_id=c.doc_id, page=c.page))
    return list(seen.values())


def draft_to_form(draft: Draft, case: PortalCase, schema: FormSchema, start_date: date) -> DraftIn:
    domain_claims: dict[str, list[Claim]] = {}
    references: dict[str, list[ReferenceNote]] = {}

    for section in draft.sections:
        for claim in section.claims:
            if claim.is_gap_statement or not claim.citations:
                continue
            targets = {d for e in claim.elements for d in ELEMENT_TO_DOMAINS.get(e, ())}
            for domain_id in sorted(targets):
                if claim not in domain_claims.setdefault(domain_id, []):
                    domain_claims[domain_id].append(claim)
            for ref_domain in sorted(
                {ELEMENT_TO_REFERENCE[e] for e in claim.elements if e in ELEMENT_TO_REFERENCE}
            ):
                note = ReferenceNote(text=claim.text, sources=_sources([claim]))
                if note not in references.setdefault(ref_domain, []):
                    references[ref_domain].append(note)

    domains = {
        domain_id: DomainPrefill(
            text=" ".join(c.text.strip() for c in claims), sources=_sources(claims)
        )
        for domain_id, claims in domain_claims.items()
        if (spec := schema.domain(domain_id)) is not None and spec.assistant_may_prefill
    }
    ask = [d.id for d in schema.domains if d.filled_by == "worker" and d.id not in domains]

    cited = {s.doc_id for d in domains.values() for s in d.sources} | {
        s.doc_id for notes in references.values() for n in notes for s in n.sources
    }
    titles = [doc.title for doc in case.documents if doc.doc_id in cited]
    header = HeaderPrefill(
        assessment_type=ASSESSMENT_TYPE_MAP.get(draft.assessment_type),
        date_started=start_date,
        sources_detail=("Documents reviewed: " + "; ".join(titles) + ".") if titles else "",
    )
    return DraftIn(header=header, domains=domains, references=references, ask_in_interview=ask)
