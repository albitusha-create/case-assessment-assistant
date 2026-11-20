"""Case state and the audit log.

Two Cosmos DB containers, both partitioned by case_id:
- `cases`: the current state of each case (one item per case, overwritten).
- `audit_events`: append-only. Every automated step and every human decision
  adds an event, so you can answer "who did what, when, based on what".

`MemoryStore` has the same methods and is used by tests and by local runs
without Cosmos.
"""

from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from azure.core.credentials import TokenCredential
from azure.cosmos import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from pydantic import BaseModel, Field

from caa.models import Draft
from caa.qa.report import QAReport

CaseStatus = Literal["new", "in_review", "approved", "returned"]


def now() -> datetime:
    return datetime.now(UTC)


class CaseRecord(BaseModel):
    case_id: str
    status: CaseStatus = "new"
    draft: Draft | None = None
    report: QAReport | None = None
    updated_at: datetime = Field(default_factory=now)


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    at: datetime = Field(default_factory=now)
    actor: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)


class Store(Protocol):
    def get_case(self, case_id: str) -> CaseRecord | None: ...
    def save_case(self, record: CaseRecord) -> None: ...
    def add_event(self, event: AuditEvent) -> None: ...
    def list_events(self, case_id: str) -> list[AuditEvent]: ...


class MemoryStore:
    def __init__(self) -> None:
        self.cases: dict[str, CaseRecord] = {}
        self.events: list[AuditEvent] = []

    def get_case(self, case_id: str) -> CaseRecord | None:
        return self.cases.get(case_id)

    def save_case(self, record: CaseRecord) -> None:
        self.cases[record.case_id] = record.model_copy(deep=True)

    def add_event(self, event: AuditEvent) -> None:
        self.events.append(event)

    def list_events(self, case_id: str) -> list[AuditEvent]:
        return sorted((e for e in self.events if e.case_id == case_id), key=lambda e: e.at)


class CosmosStore:
    def __init__(self, endpoint: str, database: str, credential: TokenCredential) -> None:
        db = CosmosClient(endpoint, credential=credential).get_database_client(database)
        self.cases: ContainerProxy = db.get_container_client("cases")
        self.audit: ContainerProxy = db.get_container_client("audit_events")

    def get_case(self, case_id: str) -> CaseRecord | None:
        try:
            item = self.cases.read_item(item=case_id, partition_key=case_id)
        except CosmosResourceNotFoundError:
            return None
        return CaseRecord.model_validate(item)

    def save_case(self, record: CaseRecord) -> None:
        # Cosmos needs an `id`; one item per case, so the case id is the item id.
        self.cases.upsert_item({"id": record.case_id, **record.model_dump(mode="json")})

    def add_event(self, event: AuditEvent) -> None:
        # create_item (not upsert): an audit event is never overwritten.
        self.audit.create_item(event.model_dump(mode="json"))

    def list_events(self, case_id: str) -> list[AuditEvent]:
        items = self.audit.query_items(
            query="SELECT * FROM c WHERE c.case_id = @case_id ORDER BY c.at",
            parameters=[{"name": "@case_id", "value": case_id}],
            partition_key=case_id,
        )
        return [AuditEvent.model_validate(item) for item in items]
