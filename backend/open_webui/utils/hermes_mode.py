"""Keep upstream UI/storage APIs while fencing off Open WebUI's agent runtime."""
import os
import re
from starlette.responses import JSONResponse

HERMES_ONLY = os.getenv('HERMES_ONLY', 'false').lower() == 'true'

UI_RESOURCE_PREFIXES = (
    '/api/v1/auths', '/api/v1/users', '/api/v1/chats', '/api/v1/folders',
    '/api/v1/notes', '/api/v1/calendars', '/api/v1/channels', '/api/v1/prompts',
    '/api/v1/configs', '/api/v1/groups', '/api/v1/models', '/api/v1/skills',
    '/api/v1/evaluations', '/api/v1/scim', '/api/v1/analytics',
    '/api/v1/notifications', '/api/v1/utils',
)
READ_ONLY_RESOURCES = ('/api/v1/tools', '/api/v1/functions', '/api/v1/knowledge', '/api/v1/terminals')
EXACT_UI_ROUTES = (
    '/api/config', '/api/version', '/api/version/updates', '/api/changelog',
    '/api/models', '/api/models/base',
)
AI_DISABLED_FEATURES = (
    'enable_plugins', 'enable_direct_connections', 'enable_direct_integrations',
    'enable_automations', 'enable_context_compaction', 'enable_tool_permissions',
    'enable_web_search', 'enable_code_interpreter',
    'enable_image_generation', 'enable_autocomplete_generation', 'enable_memories',
    'enable_user_webhooks',
)

def within(path, prefix):
    return path == prefix or path.startswith(prefix + '/')

def application_path_allowed(path: str, method: str = 'GET') -> bool:
    path = path.rstrip('/') or '/'
    if within(path, '/api/hermes') or within(path, '/ws/socket.io') :
        return True
    if path in EXACT_UI_ROUTES:
        return method == 'GET'
    # Compact invokes OWUI's model summarizer. Fork/clone would duplicate UI
    # history without a corresponding native Hermes branch.
    if within(path, '/api/v1/chats') and re.search(r'/(compact|fork|clone)$', path):
        return False
    if within(path, '/api/v1/files'):
        return not path.endswith('/data/content/update')
    if any(within(path, prefix) for prefix in READ_ONLY_RESOURCES):
        if method != 'GET':
            return False
        # Valve/terminal/knowledge retrieval endpoints can load executable code
        # or embeddings. Read only catalog metadata, not runtime data.
        tail = next(path[len(prefix):] for prefix in READ_ONLY_RESOURCES if within(path, prefix))
        return tail in ('', '/list', '/export', '/base') or bool(re.fullmatch(r'/id/[^/]+', tail))
    if any(within(path, prefix) for prefix in UI_RESOURCE_PREFIXES):
        return True
    return not any(within(path, prefix) for prefix in ('/api', '/openai', '/ollama', '/oauth', '/ws'))

class HermesApplicationBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            path = scope.get('path', '')
            allowed = application_path_allowed(path, scope.get('method', 'GET'))
            if scope['type'] == 'websocket':
                allowed = path == '/api/hermes/ws' or within(path.rstrip('/'), '/ws/socket.io')
            if not allowed:
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1008})
                else:
                    await JSONResponse(status_code=403, content={
                        'detail': 'Ta funkcja uruchamia logikę Open WebUI i jest wyłączona. AI obsługuje Hermes.',
                        'code': 'hermes_runtime_only',
                    })(scope, receive, send)
                return
        await self.app(scope, receive, send)
