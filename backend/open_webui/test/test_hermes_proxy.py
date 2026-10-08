"""Transport boundary tests; no model, Hermes state, or application DB required.

Run: python -m unittest discover -s backend/open_webui/test -p test_hermes_proxy.py
"""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
from starlette.datastructures import URL
from starlette.websockets import WebSocketDisconnect


_SOURCE = Path(__file__).resolve().parents[1] / "routers" / "hermes.py"
_SPEC = importlib.util.spec_from_file_location("hermes_proxy_under_test", _SOURCE)
hermes = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = hermes
_SPEC.loader.exec_module(hermes)


def browser_socket(token="app-jwt", origin="http://app.test:3000"):
    return SimpleNamespace(
        headers={"origin": origin},
        cookies={"token": token} if token else {},
        url=URL("ws://app.test:3000/api/hermes/ws?token=ignored-query-jwt"),
        app=SimpleNamespace(state=SimpleNamespace(redis=None)),
    )


class PolicyTests(unittest.TestCase):
    def test_chat_request_is_preserved_without_model_input_enrichment(self):
        frame = {"jsonrpc": "2.0", "id": 1, "method": "prompt.submit", "params": {"session_id": "s1", "text": "hello"}}
        before = json.dumps(frame)
        self.assertEqual(hermes.FramePolicy().check_browser(frame), (True, None))
        self.assertEqual(json.dumps(frame), before)

    def test_infrastructure_and_openwebui_completion_methods_are_denied(self):
        for method in ("config.set", "plugin.install", "host.shutdown", "chat.completions", "unknown", "event"):
            frame = {"jsonrpc": "2.0", "id": 3, "method": method, "params": {}}
            allowed, error = hermes.FramePolicy().check_browser(frame)
            self.assertFalse(allowed, method)
            self.assertEqual(error["error"]["code"], -32601)

    def test_unsolicited_or_repeated_server_request_answers_are_denied(self):
        policy = hermes.FramePolicy()
        reply = {"jsonrpc": "2.0", "id": "approval-1", "result": {"choice": "once"}}
        self.assertFalse(policy.check_browser(reply)[0])
        policy.observe_upstream({"jsonrpc": "2.0", "id": "approval-1", "method": "approval", "params": {"session_id": "s1"}})
        self.assertEqual(policy.check_browser(reply), (True, None))
        self.assertFalse(policy.check_browser(reply)[0])

    def test_resume_replay_recovers_pending_questions_and_cancel_withdraws_them(self):
        policy = hermes.FramePolicy()
        policy.observe_upstream({"jsonrpc": "2.0", "id": 1, "result": {"open_requests": [{"id": "q1", "method": "clarify", "params": {}}]}})
        reply = {"jsonrpc": "2.0", "id": "q1", "result": {"answer": "yes"}}
        self.assertTrue(policy.check_browser(reply)[0])
        policy.observe_upstream({"jsonrpc": "2.0", "id": "q2", "method": "secret", "params": {}})
        policy.observe_upstream({"jsonrpc": "2.0", "method": "event", "params": {"type": "request.cancel", "payload": {"id": "q2"}}})
        self.assertFalse(policy.check_browser({"jsonrpc": "2.0", "id": "q2", "result": {"value": "secret"}})[0])

    def test_invalid_shapes_and_conflicting_result_error_are_denied(self):
        for frame in (
            [], {"method": "ping"}, {"jsonrpc": "2.0", "id": True, "method": "ping"},
            {"jsonrpc": "2.0", "id": [], "method": "ping"},
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": []},
            {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}},
        ):
            self.assertFalse(hermes.FramePolicy().check_browser(frame)[0])

    def test_dashboard_configuration_does_not_repr_credentials_or_accept_url_credentials(self):
        settings = hermes.DashboardSettings("http://hermes:9119", "private-user", "private-password")
        self.assertNotIn("private-user", repr(settings))
        self.assertNotIn("private-password", repr(settings))
        with patch.dict(os.environ, {"HERMES_DASHBOARD_URL": "http://private-user:private-password@hermes:9119", "HERMES_DASHBOARD_USERNAME": "u", "HERMES_DASHBOARD_PASSWORD": "p"}):
            with self.assertRaises(hermes.HermesUnavailable):
                hermes.DashboardSettings.from_env()


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_uses_verified_app_cookie_without_query_credentials(self):
        lookup = AsyncMock(return_value=SimpleNamespace(id="owner", role="admin"))
        with patch.dict(sys.modules, {"open_webui.utils.auth": SimpleNamespace(get_verified_user_by_token=lookup)}):
            self.assertIsNotNone(await hermes._verified_websocket_user(browser_socket()))
            lookup.assert_awaited_once_with("app-jwt", None)
            lookup.reset_mock()
            self.assertIsNone(await hermes._verified_websocket_user(browser_socket(token=None)))
            lookup.assert_not_awaited()

    async def test_foreign_origin_invalid_role_and_api_keys_cannot_open_proxy(self):
        lookup = AsyncMock(return_value=None)
        with patch.dict(sys.modules, {"open_webui.utils.auth": SimpleNamespace(get_verified_user_by_token=lookup)}):
            self.assertIsNone(await hermes._verified_websocket_user(browser_socket(origin="http://evil.test")))
            self.assertIsNone(await hermes._verified_websocket_user(browser_socket(token="sk-key")))
            lookup.assert_not_awaited()
            self.assertIsNone(await hermes._verified_websocket_user(browser_socket(token="invalid-or-pending")))
            lookup.assert_awaited_once()


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bidirectional_bridge_preserves_native_frames_and_blocks_admin_calls(self):
        class Browser:
            def __init__(self):
                self.incoming = asyncio.Queue()
                self.sent = []

            async def receive(self):
                return await self.incoming.get()

            async def send_text(self, text):
                self.sent.append(text)

        class Upstream:
            def __init__(self):
                self.incoming = asyncio.Queue()
                self.sent = []

            def __aiter__(self):
                return self

            async def __anext__(self):
                return await self.incoming.get()

            async def send_str(self, text):
                self.sent.append(text)

        async def until(predicate):
            while not predicate():
                await asyncio.sleep(0)

        browser, upstream = Browser(), Upstream()
        bridge = asyncio.create_task(hermes._bridge(browser, upstream))
        try:
            question = '{"jsonrpc":"2.0","id":"q1","method":"clarify","params":{"session_id":"s","question":"Which?"}}'
            await upstream.incoming.put(SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=question))
            await asyncio.wait_for(until(lambda: len(browser.sent) == 1), timeout=2)
            answer = '{"jsonrpc":"2.0","id":"q1","result":{"answer":"A"}}'
            prompt = '{"jsonrpc":"2.0","id":8,"method":"prompt.submit","params":{"session_id":"s","text":"hello"}}'
            admin = '{"jsonrpc":"2.0","id":9,"method":"config.set","params":{"key":"model","value":"changed"}}'
            for text in (answer, prompt, admin):
                await browser.incoming.put({"type": "websocket.receive", "text": text})
            await asyncio.wait_for(until(lambda: len(upstream.sent) == 2 and len(browser.sent) == 2), timeout=2)
            self.assertEqual(upstream.sent, [answer, prompt])
            self.assertEqual(browser.sent[0], question)
            self.assertEqual(json.loads(browser.sent[1])["error"]["code"], -32601)
            await browser.incoming.put({"type": "websocket.disconnect"})
            await asyncio.wait_for(bridge, timeout=2)
        finally:
            bridge.cancel()
            await asyncio.gather(bridge, return_exceptions=True)


class NativeDashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ticket = "upstream-private-ticket"
        self.requests = []
        self.mode = "ready"
        self.login_count = 0
        self.ticket_count = 0
        self.rejected_tickets = 0
        self.reject_barrier_count = 0
        self.reject_barrier = asyncio.Event()
        self.available_tickets = set()
        self.used_tickets = []
        self.cache_patch = patch.object(hermes, "_dashboard_auth_cache", hermes.DashboardAuthCache())
        self.cache_patch.start()
        app = web.Application()
        app.router.add_post("/auth/password-login", self.login)
        app.router.add_post("/api/auth/ws-ticket", self.ticket_request)
        app.router.add_get("/api/ws", self.gateway)
        self.server = TestServer(app)
        await self.server.start_server()
        self.base = str(self.server.make_url("/")).rstrip("/")
        self.environment = patch.dict(os.environ, {
            "HERMES_DASHBOARD_URL": self.base,
            "HERMES_DASHBOARD_USERNAME": "upstream-private-user",
            "HERMES_DASHBOARD_PASSWORD": "upstream-private-password",
        })
        self.environment.start()

    async def asyncTearDown(self):
        self.environment.stop()
        self.cache_patch.stop()
        await self.server.close()

    async def login(self, request):
        self.requests.append((request.path, request.headers, await request.json()))
        self.login_count += 1
        # Make simultaneous callers overlap while authentication is in flight.
        await asyncio.sleep(0.02)
        if self.mode == "denied":
            return web.json_response({"detail": "private upstream failure", "password": "upstream-private-password"}, status=401)
        self.assertEqual(request.headers["Origin"], self.base)
        self.assertEqual(request.headers["Host"], self.base.removeprefix("http://"))
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual((await request.json())["password"], "upstream-private-password")
        response = web.json_response({"ok": True})
        response.set_cookie("native-cookie", f"upstream-private-cookie-{self.login_count}", max_age=600)
        return response

    async def ticket_request(self, request):
        self.requests.append((request.path, request.headers, None))
        self.ticket_count += 1
        cookie = request.cookies.get("native-cookie", "")
        self.assertTrue(cookie.startswith("upstream-private-cookie-"))
        if self.mode == "always_unauthorized" or (self.mode == "expire_first_login" and cookie == "upstream-private-cookie-1"):
            self.rejected_tickets += 1
            if self.reject_barrier_count:
                if self.rejected_tickets >= self.reject_barrier_count:
                    self.reject_barrier.set()
                await self.reject_barrier.wait()
            return web.json_response({"detail": "private-expired-session"}, status=401)
        ticket = f"{self.ticket}-{self.ticket_count}"
        self.available_tickets.add(ticket)
        return web.json_response({"ticket": ticket})

    async def gateway(self, request):
        self.requests.append((request.path, request.headers, None))
        self.assertFalse(request.query)
        self.assertEqual(request.headers["Origin"], self.base)
        self.assertIn("hermes-gateway-v1", request.headers["Sec-WebSocket-Protocol"])
        protocols = [protocol.strip() for protocol in request.headers["Sec-WebSocket-Protocol"].split(",")]
        ticket = next(protocol.removeprefix("hermes-gateway-ticket.") for protocol in protocols if protocol.startswith("hermes-gateway-ticket."))
        self.assertIn(ticket, self.available_tickets)
        self.available_tickets.remove(ticket)
        self.used_tickets.append(ticket)
        ws = web.WebSocketResponse(protocols=["hermes-gateway-v1"])
        await ws.prepare(request)
        await ws.send_json({"jsonrpc": "2.0", "method": "event", "params": {"type": "gateway.ready", "payload": {}}})
        async for message in ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                await ws.send_str(message.data)
        return ws

    async def test_status_checks_real_native_handshake_without_revealing_credentials(self):
        result = await hermes.status(user=SimpleNamespace(id="owner"))
        self.assertEqual(result, {"connected": True})
        serialized = json.dumps(result)
        for secret in ("upstream-private-user", "upstream-private-password", "upstream-private-cookie", self.ticket):
            self.assertNotIn(secret, serialized)
        self.assertEqual([row[0] for row in self.requests], ["/auth/password-login", "/api/auth/ws-ticket", "/api/ws"])

    async def test_upstream_login_error_is_sanitized(self):
        self.mode = "denied"
        result = await hermes.status(user=SimpleNamespace(id="owner"))
        self.assertEqual(result, {"connected": False, "error": "hermes_unavailable"})
        self.assertNotIn("private", json.dumps(result))

    async def test_native_gateway_payloads_remain_unchanged(self):
        settings = hermes.DashboardSettings.from_env()
        async with hermes._new_http_session() as session:
            async with await hermes._open_gateway(session, settings) as ws:
                self.assertEqual(ws.protocol, "hermes-gateway-v1")
                await ws.receive()
                raw = '{"jsonrpc":"2.0","id":8,"method":"prompt.submit","params":{"session_id":"s","text":"hello"}}'
                await ws.send_str(raw)
                reply = await ws.receive(timeout=2)
                self.assertEqual(reply.data, raw)

    async def test_concurrent_status_and_connections_share_one_login_but_fresh_tickets(self):
        settings = hermes.DashboardSettings.from_env()
        jars = []

        async def connect():
            async with hermes._new_http_session() as session:
                jars.append(session.cookie_jar)
                async with await hermes._open_gateway(session, settings) as ws:
                    message = await ws.receive(timeout=2)
                    self.assertEqual(message.type, aiohttp.WSMsgType.TEXT)
            return True

        calls = [hermes.status(user=SimpleNamespace(id="owner")) for _ in range(6)]
        calls.extend(connect() for _ in range(6))
        results = await asyncio.wait_for(asyncio.gather(*calls), timeout=5)
        self.assertTrue(all(result is True or result == {"connected": True} for result in results))
        self.assertEqual(self.login_count, 1)
        self.assertEqual(self.ticket_count, 12)
        self.assertEqual(len(self.used_tickets), 12)
        self.assertEqual(len(set(self.used_tickets)), 12)
        self.assertEqual(len({id(jar) for jar in jars}), 6)
        # Repeated status after those sockets close still uses the private login.
        self.assertEqual(await hermes.status(user=SimpleNamespace(id="owner")), {"connected": True})
        self.assertEqual(self.login_count, 1)

    async def test_concurrent_expired_tickets_invalidate_only_their_generation(self):
        self.mode = "expire_first_login"
        self.reject_barrier_count = 8
        results = await asyncio.wait_for(asyncio.gather(*[
            hermes.status(user=SimpleNamespace(id="owner")) for _ in range(8)
        ]), timeout=5)
        self.assertEqual(results, [{"connected": True}] * 8)
        self.assertEqual(self.login_count, 2)
        self.assertEqual(self.rejected_tickets, 8)
        self.assertEqual(self.ticket_count, 16)
        self.assertEqual(len(set(self.used_tickets)), 8)

    async def test_persistent_ticket_401_retries_once_without_unbounded_logins(self):
        self.mode = "always_unauthorized"
        result = await hermes.status(user=SimpleNamespace(id="owner"))
        self.assertEqual(result, {"connected": False, "error": "hermes_unavailable"})
        self.assertEqual(self.login_count, 2)
        self.assertEqual(self.ticket_count, 2)
        self.assertEqual(self.used_tickets, [])

    async def test_changed_credentials_and_expired_memory_cache_trigger_new_login(self):
        self.assertEqual(await hermes.status(user=SimpleNamespace(id="owner")), {"connected": True})
        self.assertEqual(self.login_count, 1)
        hermes._dashboard_auth_cache._valid_until = 0
        self.assertEqual(await hermes.status(user=SimpleNamespace(id="owner")), {"connected": True})
        self.assertEqual(self.login_count, 2)
        # Changing the configured principal must not reuse another login's cookies.
        settings = hermes.DashboardSettings(self.base, "different-owner", "upstream-private-password")
        async with hermes._new_http_session() as session:
            async with await hermes._open_gateway(session, settings) as ws:
                await ws.receive(timeout=2)
        self.assertEqual(self.login_count, 3)


if __name__ == "__main__":
    unittest.main()
