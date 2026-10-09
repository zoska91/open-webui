"""Verify that alternate app entry points cannot invoke Open WebUI AI.

These tests exercise the ASGI boundary independently from the application's
database and model dependencies. Run with the existing proxy test suite.
"""

import ast
from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


_SOURCE = Path(__file__).resolve().parents[1] / "utils" / "hermes_mode.py"
_SPEC = importlib.util.spec_from_file_location("hermes_mode_under_test", _SOURCE)
mode = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mode
_SPEC.loader.exec_module(mode)


def isolated_function(path, name, namespace):
    """Execute the actual function without booting unrelated model/DB imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class ApplicationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def call_boundary(self, path, scope_type="http", method="POST"):
        downstream_calls, messages = [], []

        async def downstream(scope, receive, send):
            downstream_calls.append(scope["path"])

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {"type": scope_type, "path": path, "method": method, "headers": []}
        await mode.HermesApplicationBoundary(downstream)(scope, receive, send)
        return downstream_calls, messages

    async def test_ai_completion_and_embedding_entry_points_never_reach_downstream(self):
        for path in (
            "/api/chat/completions", "/api/v1/chat/completions", "/api/chat/completed",
            "/api/chat/actions/tool", "/api/embeddings", "/api/v1/embeddings",
            "/api/message", "/api/v1/messages", "/api/v1/messages/count_tokens",
            "/api/models", "/api/models/unload",
            "/openai/chat/completions", "/openai/responses", "/ollama/api/chat",
        ):
            calls, messages = await self.call_boundary(path)
            self.assertEqual(calls, [], path)
            self.assertEqual(messages[0]["status"], 403, path)

    async def test_tool_plugin_memory_and_automation_routes_are_closed(self):
        for path in (
            "/api/v1/functions", "/api/v1/pipelines/upload", "/api/v1/tools",
            "/api/v1/memories", "/api/v1/retrieval",
            "/api/v1/automations", "/api/tasks", "/api/v1/audio/speech",
            "/api/v1/images/generations", "/api/events/webhooks", "/oauth/test/login",
        ):
            calls, messages = await self.call_boundary(path)
            self.assertEqual(calls, [], path)
            self.assertEqual(messages[0]["status"], 403, path)

    async def test_ui_assets_bootstrap_identity_and_hermes_transport_remain_available(self):
        for path in (
            "/", "/home", "/hermes", "/modules/recipes", "/static/favicon.png",
            "/_app/immutable/app.js", "/manifest.json", "/health", "/ready",
            "/api/config", "/api/version", "/api/v1/auths/signin",
            "/api/v1/auths/", "/api/v1/users/user/settings",
            "/api/hermes/status",
        ):
            calls, messages = await self.call_boundary(path, method="GET")
            self.assertEqual(calls, [path], path)
            self.assertEqual(messages, [], path)

    async def test_original_ui_storage_and_metadata_endpoints_remain_available(self):
        for path in (
            "/api/v1/chats/", "/api/v1/folders/create", "/api/v1/notes/create",
            "/api/v1/calendars/events", "/api/v1/channels/", "/api/v1/configs/",
            "/api/v1/prompts/create", "/api/v1/skills/create", "/api/v1/files/",
        ):
            calls, messages = await self.call_boundary(path)
            self.assertEqual(calls, [path], path)
            self.assertEqual(messages, [], path)
        for path in ("/api/models", "/api/v1/tools", "/api/v1/functions", "/api/v1/knowledge/list"):
            calls, messages = await self.call_boundary(path, method="GET")
            self.assertEqual(calls, [path], path)
            self.assertEqual(messages, [], path)
        calls, messages = await self.call_boundary("/ws/socket.io/", scope_type="websocket")
        self.assertEqual(calls, ["/ws/socket.io/"])
        self.assertEqual(messages, [])

    async def test_ui_can_read_catalogs_but_cannot_load_or_execute_code(self):
        for path in (
            "/api/v1/functions/create", "/api/v1/functions/sync",
            "/api/v1/tools/create", "/api/v1/knowledge/test/file/add",
            "/api/v1/files/test/data/content/update",
            "/api/v1/chats/test/compact", "/api/v1/chats/test/fork",
            "/api/v1/chats/test/clone",
        ):
            calls, messages = await self.call_boundary(path)
            self.assertEqual(calls, [], path)
            self.assertEqual(messages[0]["status"], 403, path)

    async def test_only_native_hermes_websocket_reaches_downstream(self):
        calls, messages = await self.call_boundary("/api/hermes/ws", scope_type="websocket")
        self.assertEqual(calls, ["/api/hermes/ws"])
        self.assertEqual(messages, [])
        for path in ("/api/v1/terminals/ws", "/api/hermes/status", "/any-socket"):
            calls, messages = await self.call_boundary(path, scope_type="websocket")
            self.assertEqual(calls, [], path)
            self.assertEqual(messages, [{"type": "websocket.close", "code": 1008}])

    async def test_allowed_path_names_cannot_prefix_other_ai_routes(self):
        for path in ("/api/configure", "/api/hermes-completions", "/api/v1/auths-plugins", "/api/v1/users-ai"):
            calls, messages = await self.call_boundary(path)
            self.assertEqual(calls, [], path)
            self.assertEqual(messages[0]["status"], 403, path)


class BackgroundAgentBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_auth_event_publisher_cannot_schedule_saved_plugins_or_webhooks(self):
        sink = SimpleNamespace(handle_event=AsyncMock())
        build = Mock(return_value=SimpleNamespace(event="auth.login"))
        namespace = {"HERMES_ONLY": True, "EVENT_SINKS": [sink], "build_event": build}
        publisher = isolated_function(_SOURCE.parents[1] / "events.py", "publish_event", namespace)
        await publisher(SimpleNamespace(), "auth.login")
        build.assert_not_called()
        sink.handle_event.assert_not_awaited()
        # The same source preserves the upstream mode when explicitly enabled.
        namespace["HERMES_ONLY"] = False
        await publisher(SimpleNamespace(), "auth.login")
        build.assert_called_once()
        sink.handle_event.assert_awaited_once()

    async def test_actual_hermes_lifespan_does_not_start_upstream_model_or_scheduler_runtime(self):
        runtime = AsyncMock()
        events = AsyncMock()
        install = AsyncMock()
        namespace = {
            "asynccontextmanager": asynccontextmanager,
            "asyncio": __import__("asyncio"),
            "THREAD_POOL_SIZE": 0,
            "INSTANCE_ID": "isolated-test",
            "start_logger": Mock(),
            "RESET_CONFIG_ON_START": False,
            "import_legacy_config_json": AsyncMock(),
            "seed_registered_defaults": AsyncMock(),
            "HERMES_ONLY": True,
            "get_redis_client": Mock(return_value=None),
            "initialize_runtime_config": runtime,
            "publish_event": events,
            "install_tool_and_function_dependencies": install,
        }
        lifespan = isolated_function(_SOURCE.parents[1] / "main.py", "lifespan", namespace)
        close = AsyncMock()
        app = SimpleNamespace(state=SimpleNamespace())
        with patch.dict(sys.modules, {"open_webui.utils.session_pool": SimpleNamespace(close_session=close)}):
            async with lifespan(app):
                self.assertTrue(app.state.startup_complete)
                self.assertIsNone(app.state.redis)
                self.assertFalse(hasattr(app.state, "scheduler_worker_loop"))
        runtime.assert_not_awaited()
        events.assert_not_awaited()
        install.assert_not_awaited()
        close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()


class RawAttachmentBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_upload_stores_bytes_without_scheduling_ai_extraction(self):
        handler = AsyncMock(return_value={"id": "test-file", "filename": "test.txt", "meta": {}})
        files = SimpleNamespace(
            update_file_data_by_id=AsyncMock(),
            get_file_by_id=AsyncMock(return_value={"id": "test-file", "filename": "test.txt", "meta": {}}),
        )
        empty = lambda *args, **kwargs: None
        namespace = {
            "router": SimpleNamespace(post=lambda *args, **kwargs: lambda fn: fn),
            "Depends": empty, "File": empty, "Form": empty, "Query": empty,
            "get_verified_user": Mock(), "get_async_session": Mock(), "FileModelResponse": object,
            "HERMES_ONLY": True, "upload_file_handler": handler, "Files": files,
            "publish_event": AsyncMock(), "EVENTS": SimpleNamespace(FILE_UPLOADED="file.uploaded"),
        }
        upload = isolated_function(_SOURCE.parents[1] / "routers" / "files.py", "upload_file", namespace)
        await upload(SimpleNamespace(), background_tasks=SimpleNamespace(), file=Mock(),
                     metadata=None, process=True, process_in_background=True, user=Mock(), db=None)
        self.assertFalse(handler.await_args.kwargs["process"])
        files.update_file_data_by_id.assert_awaited_once_with("test-file", {"status": "completed"}, db=None)


    async def test_actual_raw_file_delete_keeps_storage_cleanup_without_vector_runtime(self):
        stored = SimpleNamespace(user_id='owner', path='/test/raw-file', filename='fixture.txt', hash=None)
        storage = SimpleNamespace(delete_file=Mock())
        vector = SimpleNamespace(delete=AsyncMock(side_effect=RuntimeError('must not enter embedding runtime')))
        namespace = {
            'router': SimpleNamespace(delete=lambda *args, **kwargs: lambda fn: fn),
            'Depends': lambda *args, **kwargs: None,
            'get_verified_user': Mock(), 'get_async_session': Mock(),
            'HERMES_ONLY': True, 'asyncio': __import__('asyncio'),
            'Files': SimpleNamespace(get_file_by_id=AsyncMock(return_value=stored), delete_file_by_id=AsyncMock(return_value=True)),
            'Knowledges': SimpleNamespace(get_knowledges_by_file_id=AsyncMock(return_value=[])),
            'Storage': storage, 'ASYNC_VECTOR_DB_CLIENT': vector,
            'publish_event': AsyncMock(), 'EVENTS': SimpleNamespace(FILE_DELETED='file.deleted'),
        }
        delete = isolated_function(_SOURCE.parents[1] / 'routers' / 'files.py', 'delete_file_by_id', namespace)
        result = await delete(SimpleNamespace(), 'fixture', user=SimpleNamespace(id='owner', role='user'), db=None)
        self.assertEqual(result, {'message': 'File deleted successfully'})
        storage.delete_file.assert_called_once_with('/test/raw-file')
        vector.delete.assert_not_awaited()
