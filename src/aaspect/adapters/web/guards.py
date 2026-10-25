"""ASGI middleware that applies to every response: body size limit and security headers."""

from collections.abc import Callable

from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Scripts and styles only from this server: report text comes from uploaded files, so an
# injected <script> must not run even if escaping were ever bypassed.
_HEADERS = {
    "content-security-policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.decode() not in _HEADERS
                ]
                headers += [(k.encode(), v.encode()) for k, v in _HEADERS.items()]
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, send_with_headers if scope["type"] == "http" else send)


class SameOriginPosts:
    """Refuses POSTs sent by other websites.

    The server usually runs on the user's own machine: without this, any page the user
    visits could post uploads to it through an ordinary form.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and _cross_site(scope):
            await PlainTextResponse("Cross-site request refused.", 403)(scope, receive, send)
            return
        await self._app(scope, receive, send)


def _cross_site(scope: Scope) -> bool:
    headers = {name.decode("latin-1"): value.decode("latin-1") for name, value in scope["headers"]}
    fetch_site = headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site not in ("same-origin", "none")
    origin = headers.get("origin")
    # Browsers without Fetch Metadata still send Origin on cross-site form posts.
    return origin is not None and origin.split("://", 1)[-1] != headers.get("host")


class _TooLarge(Exception):
    pass


class BodySizeLimit:
    """Rejects request bodies over `max_bytes` while they arrive, before any parsing.

    Checks the declared Content-Length and also counts the bytes actually received, since
    a client can omit or understate the header.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, too_large: Callable[[], Response]) -> None:
        self._app = app
        self._max = max_bytes
        self._too_large = too_large

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"0")
        if declared.isdigit() and int(declared) > self._max:
            await self._too_large()(scope, receive, send)
            return
        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self._max:
                raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self._app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if started:
                raise
            await self._too_large()(scope, receive, send)
