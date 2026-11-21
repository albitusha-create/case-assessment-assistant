"""The portal's outbound webhook: tell a subscriber when a worker submits a form.

The body is signed with HMAC-SHA256 so the receiver can check it came from the
portal and was not changed. A failed delivery is logged, never raised: the
worker's submit in the portal must not fail because a subscriber is down.
"""

import hashlib
import hmac
import logging
from collections.abc import Callable

import httpx

from caa.portal.store import SubmittedEvent

SIGNATURE_HEADER = "X-Portal-Signature"
EVENTS_PATH = "/api/integrations/portal/events"
logger = logging.getLogger(__name__)


def sign(key: str, body: bytes) -> str:
    return "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def verify(key: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(key, body), signature)


def webhook_sender(
    get_http: Callable[[], httpx.Client], key: str
) -> Callable[[SubmittedEvent], None]:
    def send(event: SubmittedEvent) -> None:
        body = event.model_dump_json().encode()
        headers = {SIGNATURE_HEADER: sign(key, body), "Content-Type": "application/json"}
        try:
            get_http().post(EVENTS_PATH, content=body, headers=headers).raise_for_status()
        except httpx.HTTPError:
            logger.exception("Portal webhook delivery failed for %s", event.case_id)

    return send
