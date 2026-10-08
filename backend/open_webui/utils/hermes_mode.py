"""Application boundary for deployments whose only agent runtime is Hermes."""

import os

from starlette.responses import JSONResponse


HERMES_ONLY = os.getenv('HERMES_ONLY', 'false').lower() == 'true'


def application_path_allowed(path: str) -> bool:
    if path.rstrip('/') in (
        '/api/config', '/api/version', '/api/changelog',
        '/api/v1/auths', '/api/v1/auths/signin', '/api/v1/auths/signout',
        '/api/v1/auths/update/timezone',
        '/api/v1/users/user/settings', '/api/v1/users/user/settings/update',
    ):
        return True
    if path == '/api/hermes' or path.startswith('/api/hermes/'):
        return True
    # Static assets and app navigation remain available. All other backend
    # APIs are closed, including alternate OpenAI/Anthropic compatibility URLs.
    return not any(path == prefix or path.startswith(prefix + '/') for prefix in (
        '/api', '/openai', '/ollama', '/oauth', '/ws',
    ))


class HermesApplicationBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            path = scope.get('path', '')
            allowed = application_path_allowed(path)
            if scope['type'] == 'websocket':
                allowed = path == '/api/hermes/ws'
            if not allowed:
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1008})
                else:
                    await JSONResponse(
                        status_code=404,
                        content={'detail': 'This application uses the Hermes runtime.'},
                    )(scope, receive, send)
                return
        await self.app(scope, receive, send)
