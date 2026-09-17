"""Optional shared-passphrase gate for the whole app.

No-op unless AUTH_PASSWORD is set -- today's local/dev/test behavior is
unchanged, zero config. Only a real deployment with that env var set
(see deploy.sh) actually requires a login, via the browser's native HTTP
Basic Auth prompt: no login page to build, and it covers the static
page load and the API uniformly since it's applied to the whole app.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        password = os.environ.get("AUTH_PASSWORD")
        if not password:
            return await call_next(request)

        username = os.environ.get("AUTH_USERNAME", "play")
        if _credentials_match(request, username, password):
            return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Product: The Game"'},
        )


def _credentials_match(request: Request, username: str, password: str) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    given_user, _, given_pass = decoded.partition(":")
    return secrets.compare_digest(given_user, username) and secrets.compare_digest(
        given_pass, password
    )
