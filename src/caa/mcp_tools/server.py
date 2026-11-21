"""MCP server over the same portal client and approval gate the web app uses.

An agent gets the same operations as our REST integration, and the same limits:
- Read tools: list cases, read a case, read the form schema, read a form.
- One write tool, `portal_send_approved_draft`. It takes only a case id, never
  free text, and sends the draft a supervisor approved in our app, through the
  same code path as the Approve button. Unapproved cases are refused.
- There is no submit tool. Submitting stays a person's click in the portal.

It is served at /mcp on our app over streamable HTTP, and only answers requests
addressed to localhost (the SDK's DNS rebinding protection), so it is for local
use and demos. In production it would sit behind Entra ID or API Management.
"""

from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from caa.api.auth import SUPERVISOR, User
from caa.integrations.portal_client import PortalClient, PortalError
from caa.integrations.portal_sync import PushError, push_approved_draft
from caa.storage.store import Store
from caa.synthetic import list_case_ids, load_case

MCP_ACTOR = User(name="mcp-client", roles={SUPERVISOR})
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


def build_mcp_server(app: FastAPI) -> MCPServer:
    """Tools read the app's state when called, so tests can swap the HTTP client."""
    server = MCPServer(
        name="agency-portal",
        instructions=(
            "Tools for a human services agency portal (mock, synthetic data). You can read "
            "cases and assessment forms, and send a supervisor-approved draft to the portal "
            "as a pre-filled draft. You cannot write free text or submit a form: a worker "
            "reviews and submits in the portal."
        ),
    )

    def client() -> PortalClient:
        return PortalClient(app.state.portal_http, app.state.portal_api_key)

    def call(fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except PortalError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=READ_ONLY)
    def portal_list_cases() -> list[dict[str, Any]]:
        """List cases in the worker's caseload with due dates and form status."""
        return [c.model_dump(mode="json") for c in call(client().list_cases)]

    @server.tool(annotations=READ_ONLY)
    def portal_get_case(case_id: str) -> dict[str, Any]:
        """Read one case record and the documents attached to it."""
        return dict(call(client().get_case, case_id).model_dump(mode="json"))

    @server.tool(annotations=READ_ONLY)
    def portal_get_form_schema() -> dict[str, Any]:
        """The core assessment form: fields, domains, and which ones software may pre-fill."""
        return dict(call(client().get_schema).model_dump(mode="json"))

    @server.tool(annotations=READ_ONLY)
    def portal_get_assessment(case_id: str) -> dict[str, Any]:
        """Read a case's assessment form as it is in the portal now, including its status."""
        return dict(call(client().get_form, case_id).model_dump(mode="json"))

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
        )
    )
    def portal_send_approved_draft(case_id: str) -> dict[str, Any]:
        """Send the supervisor-approved draft for a case to the portal as a pre-filled draft.

        Refused unless the case is approved in the Case Assessment Assistant. Never
        overwrites a form the worker has edited. Never submits.
        """
        if case_id not in list_case_ids():
            raise ToolError(f"Unknown case: {case_id}")
        store: Store = app.state.store
        try:
            form = push_approved_draft(store, client(), load_case(case_id), MCP_ACTOR)
        except PushError as exc:
            raise ToolError(str(exc)) from exc
        if form is None:
            last = store.list_events(case_id)[-1]
            raise ToolError(f"Portal did not accept the draft: {last.details}")
        return {
            "case_id": case_id,
            "form_status": form.status,
            "prefilled_domains": sorted(form.domains),
            "ask_in_interview": form.ask_in_interview,
            "next_step": "The worker reviews, edits and submits the form in the portal.",
        }

    return server
