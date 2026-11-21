"""The MCP tools: same portal client, same approval gate, no submit and no free text."""

from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

from caa.mcp_tools.server import build_mcp_server
from caa.models import Draft
from caa.portal.store import PortalStore
from caa.storage.store import MemoryStore
from tests.unit.test_api import CASEWORKER, SUPERVISOR, make_client


def call(client: TestClient, tool: str, **args: Any) -> tuple[bool, Any]:
    """Call a tool in process. Returns (is_error, structured result or error message)."""
    server = build_mcp_server(client.app)  # type: ignore[arg-type]
    try:
        result = anyio.run(server.call_tool, tool, args)
    except ToolError as exc:
        return True, str(exc)
    data = result.structured_content or {}  # type: ignore[union-attr]
    return False, data.get("result", data)


@pytest.fixture
def client(complete_draft: Draft) -> TestClient:
    return make_client(MemoryStore(), complete_draft)


def test_tool_list_has_no_submit_and_no_free_text_write(client: TestClient) -> None:
    server = build_mcp_server(client.app)  # type: ignore[arg-type]
    tools = {t.name: t for t in anyio.run(server.list_tools)}
    assert set(tools) == {
        "portal_list_cases",
        "portal_get_case",
        "portal_get_form_schema",
        "portal_get_assessment",
        "portal_send_approved_draft",
    }
    assert not any("submit" in name for name in tools)
    write = tools["portal_send_approved_draft"]
    assert list(write.input_schema["properties"]) == ["case_id"]


def test_read_tools(client: TestClient) -> None:
    error, cases = call(client, "portal_list_cases")
    assert not error
    assert {c["case_id"] for c in cases} == {"case-001", "case-002", "case-003", "case-004"}
    error, case = call(client, "portal_get_case", case_id="case-002")
    assert case["case_number"] == "2026-YF-20317"
    error, form = call(client, "portal_get_assessment", case_id="case-002")
    assert form["status"] == "not_started"
    error, _ = call(client, "portal_get_case", case_id="case-999")
    assert error


def test_send_is_refused_until_a_supervisor_approves(client: TestClient) -> None:
    error, message = call(client, "portal_send_approved_draft", case_id="case-001")
    assert error and "approved" in message

    client.post("/cases/case-001/run", headers=CASEWORKER)
    client.post("/cases/case-001/approve", headers=SUPERVISOR)
    error, result = call(client, "portal_send_approved_draft", case_id="case-001")
    assert not error
    assert result["form_status"] == "draft"
    assert "strengths" in result["prefilled_domains"]

    store: MemoryStore = client.app.state.store  # type: ignore[attr-defined]
    last = store.list_events("case-001")[-1]
    assert (last.actor, last.action) == ("mcp-client", "portal_draft_pushed")


def test_send_reports_a_portal_refusal(client: TestClient) -> None:
    client.post("/cases/case-001/run", headers=CASEWORKER)
    client.post("/cases/case-001/approve", headers=SUPERVISOR)
    portal: PortalStore = client.app.state.portal  # type: ignore[attr-defined]
    portal.submit("case-001", "casey", attested=True)
    client.post("/cases/case-001/run", headers=CASEWORKER)  # a later approval
    client.post("/cases/case-001/approve", headers=SUPERVISOR)
    error, message = call(client, "portal_send_approved_draft", case_id="case-001")
    assert error and "submitted" in message
