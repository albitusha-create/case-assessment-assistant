"""Who is calling, and which app roles they hold (ADR 0005).

In Azure, Container Apps authentication (Easy Auth) signs the user in with
Entra ID and passes their claims to the app in the X-MS-CLIENT-PRINCIPAL
header (base64 JSON). App roles arrive as claims of type "roles".
The header cannot be forged from outside: Easy Auth strips it from incoming
requests and sets it itself.
"""

import base64
import json
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from caa.config import Settings, get_settings

CASEWORKER = "Caseworker"
SUPERVISOR = "Supervisor"
PRINCIPAL_HEADER = "x-ms-client-principal"


class User(BaseModel):
    name: str
    roles: set[str]


def parse_principal(header: str) -> User:
    data = json.loads(base64.b64decode(header))
    claims = data.get("claims", [])
    name_type = data.get("name_typ", "name")
    role_type = data.get("role_typ", "roles")
    name = next((c["val"] for c in claims if c["typ"] == name_type), "unknown")
    roles = {c["val"] for c in claims if c["typ"] in (role_type, "roles")}
    return User(name=name, roles=roles)


def current_user(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> User:
    header = request.headers.get(PRINCIPAL_HEADER)
    if header:
        return parse_principal(header)
    if settings.environment == "local":
        roles = {r.strip() for r in settings.dev_user_roles.split(",") if r.strip()}
        return User(name=settings.dev_user_name, roles=roles)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")


def require_role(role: str) -> Callable[..., User]:
    """Dependency that returns the user if they hold `role`, else 403."""

    def check(user: Annotated[User, Depends(current_user)]) -> User:
        if role not in user.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the {role} role")
        return user

    return check
