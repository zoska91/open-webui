"""Authenticated application transport for the native Hermes gateway.

This router forwards Hermes JSON-RPC frames. It does not construct model inputs,
run tools, store transcripts, or call Open WebUI's completion middleware.
Dashboard credentials and the one-use WebSocket ticket stay on the backend.
One deployment belongs to one Hermes owner; use separate deployments for other
people rather than pointing multiple accounts at the same Hermes home.
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from starlette.websockets import WebSocketDisconnect
from yarl import URL


router = APIRouter()
log = logging.getLogger(__name__)

_MAX_FRAME_BYTES = 16 * 1024 * 1024
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)
_GATEWAY_PROTOCOL = "hermes-gateway-v1"
_TICKET_PROTOCOL_PREFIX = "hermes-gateway-ticket."

# Deliberately explicit: config, credentials, plugins, host and infrastructure
# administration are not part of the application chat transport. Parameter
# schemas remain Hermes' responsibility, including its own tool approvals.
ALLOWED_METHODS = frozenset(
    {
        "client.capabilities", "gateway.capabilities", "gateway.ping", "ping",
        "session.create", "session.resume", "session.activate", "session.list",
        "session.active_list", "session.most_recent", "session.history",
        "session.events.since", "session.events.stats", "session.status",
        "session.usage", "session.context_breakdown", "session.title",
        "session.close", "session.interrupt", "session.steer", "session.save",
        "session.branch", "session.branch_stored", "session.branch_whole",
        "session.undo", "session.compress", "session.set_hidden",
        "prompt.submit", "prompt.background", "prompt.btw",
        "clarify.lock", "approval.pending", "approval.received", "approval.respond",
    }
)


class HermesUnavailable(Exception):
    """A deliberately detail-free upstream failure, safe to surface to clients."""


@dataclass(frozen=True)
class DashboardSettings:
    base_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)

    @classmethod
    def from_env(cls):
        raw_url = os.environ.get("HERMES_DASHBOARD_URL", "http://hermes:9119").rstrip("/")
        parsed = urlsplit(raw_url)
        username = os.environ.get("HERMES_DASHBOARD_USERNAME", "")
        password = os.environ.get("HERMES_DASHBOARD_PASSWORD", "")
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not username
            or not password
        ):
            raise HermesUnavailable()
        return cls(raw_url, username, password)

    @property
    def origin(self):
        parsed = urlsplit(self.base_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    @property
    def websocket_url(self):
        parsed = urlsplit(self.base_url + "/api/ws")
        return urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, parsed.path, "", ""))


class DashboardAuthCache:
    """One owner's private dashboard login, held only in this backend process.

    Hermes counts successful password logins against its 10/minute/IP budget.
    Serialize login, then copy its cookies into independent connection jars.
    Tickets and live HTTP/WS sessions are never cached or shared. Generations
    prevent a late 401 from invalidating a newer login established by a peer.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._settings = None
        self._cookies = {}
        self._valid_until = 0.0
        self._generation = 0

    async def authorize(self, session, settings):
        async with self._lock:
            session.cookie_jar.clear()
            if (
                self._settings == settings
                and self._cookies
                and time.monotonic() < self._valid_until
            ):
                session.cookie_jar.update_cookies(self._cookies, response_url=URL(settings.base_url))
                return self._generation

            # Invalidate before login so a failure never leaves stale credentials
            # reusable. Never log response bodies, cookies or settings values.
            self._settings = None
            self._cookies = {}
            self._valid_until = 0.0
            async with session.post(
                settings.base_url + "/auth/password-login",
                headers={"Origin": settings.origin},
                json={"provider": "basic", "username": settings.username, "password": settings.password, "next": "/"},
                allow_redirects=False,
                timeout=_HTTP_TIMEOUT,
            ) as response:
                if response.status != 200:
                    raise HermesUnavailable()
                body = await response.json()
                if not isinstance(body, dict) or body.get("ok") is not True:
                    raise HermesUnavailable()
                # Bound memory retention, and respect shorter upstream lifetimes.
                lifetime = 300.0
                for cookie in response.cookies.values():
                    if cookie["max-age"]:
                        with contextlib.suppress(ValueError):
                            lifetime = min(lifetime, max(0, float(cookie["max-age"]) - 5))

            cookies = {
                name: cookie.value
                for name, cookie in session.cookie_jar.filter_cookies(URL(settings.base_url)).items()
            }
            if not cookies:
                raise HermesUnavailable()
            self._settings = settings
            self._cookies = cookies
            self._valid_until = time.monotonic() + lifetime
            self._generation += 1
            return self._generation

    async def invalidate(self, settings, generation):
        async with self._lock:
            if self._settings == settings and self._generation == generation:
                self._settings = None
                self._cookies = {}
                self._valid_until = 0.0


_dashboard_auth_cache = DashboardAuthCache()


async def _verified_http_user(request: Request):
    # Lazy import keeps the transport policy testable without initializing the
    # application's database. Reuse OWUI JWT validation, roles and revocation.
    from open_webui.utils.auth import get_optional_verified_user_from_request

    user = await get_optional_verified_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _websocket_token(websocket: WebSocket):
    authorization = websocket.headers.get("authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
        return None
    # The regular app sign-in sets this HttpOnly cookie, also in no-login mode.
    # Do not accept query parameters: access logs must not contain session JWTs.
    return websocket.cookies.get("token")


def _same_origin(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    scheme = "https" if websocket.url.scheme in {"https", "wss"} else "http"
    expected = f"{scheme}://{websocket.url.netloc}"
    return origin.rstrip("/") == expected


async def _verified_websocket_user(websocket: WebSocket):
    from open_webui.utils.auth import get_verified_user_by_token

    if not _same_origin(websocket):
        return None
    token = _websocket_token(websocket)
    if not token or token.startswith("sk-"):
        return None
    try:
        return await get_verified_user_by_token(token, getattr(websocket.app.state, "redis", None))
    except Exception:
        # Do not print the JWT or the decoder's error details.
        return None


async def _open_gateway(session: aiohttp.ClientSession, settings: DashboardSettings):
    """Reuse backend login but mint one fresh ticket for every WS connection."""
    headers = {"Origin": settings.origin}
    try:
        generation = await _dashboard_auth_cache.authorize(session, settings)
        for attempt in range(2):
            async with session.post(
                settings.base_url + "/api/auth/ws-ticket",
                headers=headers,
                allow_redirects=False,
                timeout=_HTTP_TIMEOUT,
            ) as response:
                if response.status == 401 and attempt == 0:
                    await _dashboard_auth_cache.invalidate(settings, generation)
                    generation = await _dashboard_auth_cache.authorize(session, settings)
                    continue
                if response.status != 200:
                    raise HermesUnavailable()
                body = await response.json()
                ticket = body.get("ticket") if isinstance(body, dict) else None
                if not isinstance(ticket, str) or not ticket:
                    raise HermesUnavailable()
                break

        # Only Hermes sees this credential-bearing protocol. The ticket is not
        # placed in a URL, browser frame, log, response, or selected subprotocol.
        return await asyncio.wait_for(
            session.ws_connect(
                settings.websocket_url,
                origin=settings.origin,
                protocols=(_GATEWAY_PROTOCOL, _TICKET_PROTOCOL_PREFIX + ticket),
                timeout=aiohttp.ClientWSTimeout(ws_close=5),
                max_msg_size=_MAX_FRAME_BYTES,
                heartbeat=20,
            ),
            timeout=15,
        )
    except HermesUnavailable:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
        raise HermesUnavailable() from None


def _rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _valid_id(value):
    return isinstance(value, (str, int)) and not isinstance(value, bool)


class FramePolicy:
    """Gate browser methods and correlate answers to native server questions."""

    def __init__(self):
        self.pending_server_requests = set()

    def observe_upstream(self, frame):
        if not isinstance(frame, dict):
            return
        if frame.get("method") and "id" in frame and _valid_id(frame["id"]):
            self.pending_server_requests.add(frame["id"])
        # Native resume and event replay return unanswered server questions.
        result = frame.get("result")
        if isinstance(result, dict):
            for request in result.get("open_requests") or []:
                if isinstance(request, dict) and _valid_id(request.get("id")) and request.get("method"):
                    self.pending_server_requests.add(request["id"])
        params = frame.get("params")
        if frame.get("method") == "event" and isinstance(params, dict) and params.get("type") == "request.cancel":
            payload = params.get("payload")
            if isinstance(payload, dict) and _valid_id(payload.get("id")):
                self.pending_server_requests.discard(payload.get("id"))

    def check_browser(self, frame):
        """Return (forward, local_error). Never transform permitted params."""
        if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
            return False, _rpc_error(None, -32600, "Invalid JSON-RPC frame")
        request_id = frame.get("id")
        if "id" in frame and not _valid_id(request_id):
            return False, _rpc_error(None, -32600, "Invalid JSON-RPC id")
        if "method" in frame:
            if (
                set(frame) - {"jsonrpc", "id", "method", "params"}
                or not isinstance(frame["method"], str)
                or ("params" in frame and not isinstance(frame["params"], dict))
            ):
                return False, _rpc_error(request_id, -32600, "Invalid JSON-RPC request")
            if frame["method"] not in ALLOWED_METHODS:
                return False, _rpc_error(request_id, -32601, "Method is not available in this application") if "id" in frame else None
            return True, None
        if (
            set(frame) - {"jsonrpc", "id", "result", "error"}
            or "id" not in frame
            or ("result" in frame) == ("error" in frame)
            or ("error" in frame and not isinstance(frame["error"], dict))
        ):
            return False, _rpc_error(request_id, -32600, "Invalid JSON-RPC response")
        if request_id not in self.pending_server_requests:
            return False, _rpc_error(request_id, -32600, "No pending Hermes request for this response")
        self.pending_server_requests.discard(request_id)
        return True, None


def _new_http_session():
    # Separate jars per connection; only a copy of the private cached login is
    # installed into them. No ambient proxy or browser auth settings are used.
    return aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
        trust_env=False,
    )


@router.get("/status")
async def status(user=Depends(_verified_http_user)):
    try:
        settings = DashboardSettings.from_env()
        async with _new_http_session() as session:
            async with await _open_gateway(session, settings) as upstream:
                message = await upstream.receive(timeout=10)
                if message.type == aiohttp.WSMsgType.TEXT:
                    frame = json.loads(message.data)
                    params = frame.get("params", {}) if isinstance(frame, dict) else {}
                    if isinstance(frame, dict) and isinstance(params, dict) and frame.get("method") == "event" and params.get("type") == "gateway.ready":
                        return {"connected": True}
    except (HermesUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        pass
    return {"connected": False, "error": "hermes_unavailable"}


async def _bridge(websocket: WebSocket, upstream):
    policy = FramePolicy()
    # The two directions can both return frames to the browser (RPC rejection
    # and upstream events). Serialize those writes without altering their data.
    send_lock = asyncio.Lock()

    async def send_browser(text):
        async with send_lock:
            await websocket.send_text(text)

    async def browser_to_hermes():
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            raw = message.get("text")
            if not isinstance(raw, str):
                await websocket.close(code=1003, reason="JSON text frames required")
                return
            if len(raw.encode("utf-8")) > _MAX_FRAME_BYTES:
                await websocket.close(code=1009, reason="Frame too large")
                return
            try:
                frame = json.loads(raw)
            except (ValueError, TypeError):
                await send_browser(json.dumps(_rpc_error(None, -32700, "Invalid JSON")))
                continue
            forward, error = policy.check_browser(frame)
            if forward:
                await upstream.send_str(raw)
            elif error is not None:
                await send_browser(json.dumps(error))

    async def hermes_to_browser():
        async for message in upstream:
            if message.type == aiohttp.WSMsgType.TEXT:
                try:
                    policy.observe_upstream(json.loads(message.data))
                except (ValueError, TypeError):
                    # The native gateway only speaks JSON. An invalid upstream
                    # frame is a failed transport, never content for the UI.
                    raise HermesUnavailable() from None
                await send_browser(message.data)
            elif message.type == aiohttp.WSMsgType.ERROR:
                raise HermesUnavailable()

    tasks = [asyncio.create_task(browser_to_hermes()), asyncio.create_task(hermes_to_browser())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@router.websocket("/ws")
async def websocket_proxy(websocket: WebSocket):
    user = await _verified_websocket_user(websocket)
    if user is None:
        await websocket.close(code=1008, reason="Authentication required")
        return
    accepted = False
    try:
        settings = DashboardSettings.from_env()
        async with _new_http_session() as session:
            async with await _open_gateway(session, settings) as upstream:
                await websocket.accept()
                accepted = True
                await _bridge(websocket, upstream)
    except WebSocketDisconnect:
        return
    except (HermesUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
        # Do not log URLs, cookies, RPC bodies, ticket protocols, or exception
        # messages. No retry here: the browser resumes/replays the native session.
        log.warning("Hermes gateway transport unavailable")
    finally:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1011 if accepted else 1013, reason="Hermes connection closed")
