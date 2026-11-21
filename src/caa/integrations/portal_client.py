"""Typed client for the agency portal's REST API v1.

Our app talks to the portal only through this class, over HTTP, as it would to
any third-party system. The request and response models are the portal's
published ones; with a real vendor they would be generated from its OpenAPI spec.
"""

import httpx
from pydantic import TypeAdapter

from caa.portal.api import CaseSummary
from caa.portal.form import FormSchema
from caa.portal.store import AssessmentForm, DraftIn, PortalCase

API = "/portal/api/v1"


class PortalError(Exception):
    """The portal could not be reached, or refused the request."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PortalConflictError(PortalError):
    """The form's state in the portal does not allow the change (HTTP 409)."""


class PortalClient:
    def __init__(self, http: httpx.Client, api_key: str) -> None:
        self.http = http
        self.api_key = api_key

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        all_headers = {"Authorization": f"Bearer {self.api_key}", **(headers or {})}
        try:
            response = self.http.request(method, API + path, headers=all_headers, json=json)
        except httpx.HTTPError as exc:
            raise PortalError(f"Portal unreachable: {exc}") from exc
        if response.status_code == 409:
            raise PortalConflictError(_detail(response), 409)
        if response.is_error:
            raise PortalError(_detail(response), response.status_code)
        return response

    def list_cases(self) -> list[CaseSummary]:
        data = self._request("GET", "/cases").json()
        return TypeAdapter(list[CaseSummary]).validate_python(data)

    def get_case(self, case_id: str) -> PortalCase:
        return PortalCase.model_validate(self._request("GET", f"/cases/{case_id}").json())

    def get_schema(self) -> FormSchema:
        data = self._request("GET", "/forms/core-assessment/schema").json()
        return FormSchema.model_validate(data)

    def get_form(self, case_id: str) -> AssessmentForm:
        data = self._request("GET", f"/cases/{case_id}/assessment").json()
        return AssessmentForm.model_validate(data)

    def save_draft(self, case_id: str, draft: DraftIn, idempotency_key: str) -> AssessmentForm:
        """Save a pre-filled draft. Safe to retry with the same key."""
        response = self._request(
            "PUT",
            f"/cases/{case_id}/assessment/draft",
            headers={"Idempotency-Key": idempotency_key},
            json=draft.model_dump(mode="json"),
        )
        return AssessmentForm.model_validate(response.json())


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    return f"Portal returned {response.status_code}: {detail or response.text[:200]}"
