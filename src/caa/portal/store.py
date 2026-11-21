"""The mock portal's records: cases, attached documents and assessment forms.

This plays the third-party system of record. It keeps its own state, apart from
our app's Cosmos store, the way a real agency system would. State lives in
memory and resets on restart, which is fine for a mock seeded from synthetic data.

The rules that protect the worker live here, on the portal side, so they hold
for every caller (REST or MCP):
- A client can save a draft, never submit. Only a signed-in worker submits.
- A client never overwrites a form the worker has edited or submitted.
- Domains the schema marks as not pre-fillable are refused.
- Saving twice with the same Idempotency-Key changes nothing the second time.
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from caa.portal.form import SCHEMA, FormSchema, PortalAssessmentType
from caa.rules import calculate_due_date, load_criteria
from caa.synthetic import SYNTHETIC_SOURCE_DIR, load_case

PORTAL_SEED = SYNTHETIC_SOURCE_DIR / "portal-cases.json"
DOCUMENTS_DIR = SYNTHETIC_SOURCE_DIR.parent / "cases"

# Our criteria names on the left, the portal's assessment types on the right.
ASSESSMENT_TYPE_MAP: dict[str, PortalAssessmentType] = {
    "initial_assessment": "initial",
    "reassessment": "update",
}

FormStatus = Literal["not_started", "draft", "submitted"]


def now() -> datetime:
    return datetime.now(UTC)


class PortalDocument(BaseModel):
    doc_id: str
    title: str
    received: date


class PortalCase(BaseModel):
    case_id: str
    case_number: str
    client_name: str
    age: int
    pronouns: str
    program: str
    assigned_worker: str
    assessment_type: PortalAssessmentType
    program_start: date
    assessment_due: date
    documents: list[PortalDocument]

    def document(self, doc_id: str) -> PortalDocument | None:
        return next((d for d in self.documents if d.doc_id == doc_id), None)


class SourceRef(BaseModel):
    """Where a pre-filled statement came from: a document and page in this case."""

    doc_id: str
    page: int = Field(ge=1)


class DomainEntry(BaseModel):
    text: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    origin: Literal["assistant", "worker"] = "worker"
    updated_by: str = ""
    updated_at: datetime | None = None


class ReferenceNote(BaseModel):
    """A cited fact shown beside a field the clinician completes. Never fills the field."""

    text: str
    sources: list[SourceRef] = Field(default_factory=list)


class FormHeader(BaseModel):
    assessment_type: PortalAssessmentType | None = None
    abbreviated: bool = False
    abbreviated_reason: str = ""
    date_started: date | None = None
    date_completed: date | None = None
    meeting_dates: str = ""
    outside_provider: bool = False
    information_sources: list[str] = Field(default_factory=list)
    sources_detail: str = ""
    preferred_name: str = ""
    pronouns: str = ""


class AssessmentForm(BaseModel):
    case_id: str
    form_id: str = SCHEMA.form_id
    form_version: str = SCHEMA.version
    status: FormStatus = "not_started"
    header: FormHeader = Field(default_factory=FormHeader)
    domains: dict[str, DomainEntry] = Field(default_factory=dict)
    references: dict[str, list[ReferenceNote]] = Field(default_factory=dict)
    ask_in_interview: list[str] = Field(default_factory=list)
    # Set when a client saves a pre-filled draft.
    prefilled_by: str | None = None
    prefilled_at: datetime | None = None
    prefill_key: str | None = None
    prefilled_text: dict[str, str] = Field(default_factory=dict)
    # Set by the worker's actions in the portal.
    worker_edited: bool = False
    submitted_by: str | None = None
    submitted_at: datetime | None = None


class HeaderPrefill(BaseModel):
    """Header fields a client may suggest. Dates completed and attestation stay with the worker."""

    assessment_type: PortalAssessmentType | None = None
    date_started: date | None = None
    information_sources: list[str] = Field(default_factory=list)
    sources_detail: str = ""


class DomainPrefill(BaseModel):
    text: str
    sources: list[SourceRef] = Field(default_factory=list)


class DraftIn(BaseModel):
    """Body of PUT /cases/{id}/assessment/draft."""

    header: HeaderPrefill = Field(default_factory=HeaderPrefill)
    domains: dict[str, DomainPrefill] = Field(default_factory=dict)
    references: dict[str, list[ReferenceNote]] = Field(default_factory=dict)
    ask_in_interview: list[str] = Field(default_factory=list)


class SubmittedEvent(BaseModel):
    """What the portal tells subscribers when a worker submits a form."""

    case_id: str
    submitted_by: str
    submitted_at: datetime
    prefilled_by: str | None
    prefilled_domains: int
    changed_by_worker: int


class PortalConflict(Exception):
    """The form's state does not allow this change (maps to HTTP 409)."""


class PortalValidationError(Exception):
    """The request breaks a form rule (maps to HTTP 422)."""


def changed_prefilled_domains(form: AssessmentForm) -> int:
    return sum(
        1
        for domain_id, text in form.prefilled_text.items()
        if form.domains.get(domain_id, DomainEntry()).text.strip() != text.strip()
    )


class PortalStore:
    def __init__(self, cases: list[PortalCase], schema: FormSchema = SCHEMA) -> None:
        self.schema = schema
        self.cases = {c.case_id: c for c in cases}
        self.forms = {c.case_id: AssessmentForm(case_id=c.case_id) for c in cases}
        self.listeners: list[Callable[[SubmittedEvent], None]] = []

    @classmethod
    def seeded(cls, seed: Path = PORTAL_SEED, today: date | None = None) -> "PortalStore":
        criteria = load_criteria()
        cases = []
        for raw in json.loads(seed.read_text())["cases"]:
            synthetic = load_case(raw["case_id"])
            rule = criteria.assessment_types[synthetic.assessment_type].due
            due = calculate_due_date(
                synthetic.start_date, rule, today or date.today(), criteria.holidays
            )
            cases.append(
                PortalCase(
                    **raw,
                    assessment_type=ASSESSMENT_TYPE_MAP[synthetic.assessment_type],
                    program_start=synthetic.start_date,
                    assessment_due=due.due_date,
                )
            )
        return cls(cases)

    def list_cases(self) -> list[PortalCase]:
        return sorted(self.cases.values(), key=lambda c: c.assessment_due)

    def get_case(self, case_id: str) -> PortalCase:
        if case_id not in self.cases:
            raise KeyError(case_id)
        return self.cases[case_id]

    def get_form(self, case_id: str) -> AssessmentForm:
        self.get_case(case_id)
        return self.forms[case_id]

    def save_prefill(
        self, case_id: str, draft: DraftIn, client: str, idempotency_key: str
    ) -> tuple[AssessmentForm, bool]:
        """Save a client's pre-filled draft. Returns the form and whether this was a replay."""
        form = self.get_form(case_id)
        if form.prefill_key == idempotency_key:
            return form, True
        if form.status == "submitted":
            raise PortalConflict("The form was already submitted by the worker")
        if form.worker_edited:
            raise PortalConflict("The worker has edited this form in the portal")
        self._validate(draft)

        at = now()
        header = form.header.model_copy(
            update={k: v for k, v in draft.header.model_dump().items() if v not in (None, [], "")}
        )
        form.header = header
        form.domains = {
            domain_id: DomainEntry(
                text=entry.text,
                sources=entry.sources,
                origin="assistant",
                updated_by=client,
                updated_at=at,
            )
            for domain_id, entry in draft.domains.items()
        }
        form.references = draft.references
        form.ask_in_interview = draft.ask_in_interview
        form.prefilled_text = {d: e.text for d, e in draft.domains.items()}
        form.status, form.prefilled_by, form.prefilled_at = "draft", client, at
        form.prefill_key = idempotency_key
        return form, False

    def _validate(self, draft: DraftIn) -> None:
        for domain_id in [*draft.domains, *draft.references, *draft.ask_in_interview]:
            if self.schema.domain(domain_id) is None:
                raise PortalValidationError(f"Unknown domain: {domain_id}")
        for domain_id in draft.domains:
            domain = self.schema.domain(domain_id)
            if domain is not None and not domain.assistant_may_prefill:
                raise PortalValidationError(f"{domain_id} cannot be pre-filled by a client")
        known_sources = {s.id for s in self.schema.information_sources}
        unknown = set(draft.header.information_sources) - known_sources
        if unknown:
            raise PortalValidationError(f"Unknown information sources: {sorted(unknown)}")

    def worker_save(
        self, case_id: str, worker: str, header: FormHeader, domain_text: dict[str, str]
    ) -> AssessmentForm:
        """Save what the worker typed in the portal form."""
        form = self.get_form(case_id)
        if form.status == "submitted":
            raise PortalConflict("The form was already submitted")
        at = now()
        for domain_id, text in domain_text.items():
            if self.schema.domain(domain_id) is None:
                raise PortalValidationError(f"Unknown domain: {domain_id}")
            current = form.domains.get(domain_id, DomainEntry())
            if text.strip() != current.text.strip():
                form.domains[domain_id] = current.model_copy(
                    update={
                        "text": text,
                        "origin": "worker",
                        "updated_by": worker,
                        "updated_at": at,
                    }
                )
                form.worker_edited = True
        if header != form.header:
            form.header = header
            form.worker_edited = True
        form.status = "draft"
        return form

    def submit(self, case_id: str, worker: str, attested: bool) -> SubmittedEvent:
        form = self.get_form(case_id)
        if form.status == "submitted":
            raise PortalConflict("The form was already submitted")
        if not attested:
            raise PortalValidationError("Tick the attestation box to submit")
        form.status, form.submitted_by, form.submitted_at = "submitted", worker, now()
        if form.header.date_completed is None:
            form.header.date_completed = form.submitted_at.date()
        event = SubmittedEvent(
            case_id=case_id,
            submitted_by=worker,
            submitted_at=form.submitted_at,
            prefilled_by=form.prefilled_by,
            prefilled_domains=len(form.prefilled_text),
            changed_by_worker=changed_prefilled_domains(form),
        )
        for listener in self.listeners:
            listener(event)
        return event
