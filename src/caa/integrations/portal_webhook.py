"""Receives the portal's "form submitted" webhook and writes it to our audit log."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from caa.integrations.portal_sync import record_submitted
from caa.portal.store import SubmittedEvent
from caa.portal.webhooks import EVENTS_PATH, SIGNATURE_HEADER, verify
from caa.storage.store import Store
from caa.synthetic import list_case_ids

router = APIRouter(tags=["integrations"])


@router.post(EVENTS_PATH, status_code=status.HTTP_204_NO_CONTENT)
async def portal_event(request: Request) -> Response:
    body = await request.body()
    key: str = request.app.state.portal_api_key
    if not verify(key, body, request.headers.get(SIGNATURE_HEADER, "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    event = SubmittedEvent.model_validate_json(body)
    if event.case_id not in list_case_ids():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown case")
    store: Store = request.app.state.store
    record_submitted(store, event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
