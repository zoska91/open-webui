# Hermes application mode

This fork adds an opt-in application shell to Open WebUI. Hermes owns the agent,
model provider, prompts, memory, tools, approvals, and conversation storage.
Open WebUI renders the UI and forwards the native Hermes dashboard JSON-RPC
protocol without constructing model inputs.

Set these variables on the Open WebUI backend:

~~~dotenv
HERMES_ONLY=True
HERMES_DASHBOARD_URL=http://hermes:9119
HERMES_DASHBOARD_USERNAME=your-dashboard-user
HERMES_DASHBOARD_PASSWORD=your-dashboard-password
~~~

Keep dashboard credentials in private server configuration. They do not go into
the frontend, Git, URLs, or browser WebSocket messages. The backend reuses a
private authenticated dashboard session and mints a new ticket for each native
connection. Each deployment points to one owner's Hermes installation.

For a personal deployment reachable only through a private network,
`WEBUI_AUTH=False` skips the login screen. The shell still establishes the
regular application session and HttpOnly cookie for its HTTP/WebSocket transport.

## Application behavior

- `/home` opens a real React dashboard with Hermes connection status, the current
  date/time, a chat shortcut, and editable tile visibility.
- `/hermes` opens the native Hermes chat, including stored conversations, streaming
  text, tool/reasoning displays, and manual clarification/approval responses.
- `/modules/<id>` hosts a registered React module. See
  [application-modules.md](application-modules.md) for the component interface.
- The shell adapts to desktop, tablet, and phone widths. All use the same web build.
  Installing the PWA requires a browser-supported secure context.
- Tile preferences belong to the current browser; they do not synchronize devices.

In this mode the application does not start Open WebUI's AI runtime,
model discovery, RAG, plugin hooks, Socket.IO, or AI scheduler. Its completion,
provider, tool, memory, automation, and administration APIs are blocked by an
ASGI boundary. Authentication and UI-preference routes remain available.
Hermes's tool execution and approval rules remain on Hermes.

Future module backend routes must be registered explicitly and admitted in
`backend/open_webui/utils/hermes_mode.py`. Adding a React component alone does
not grant access to upstream AI or administration endpoints.

Without `HERMES_ONLY=True`, the original Open WebUI application remains selected.
Keep the Open WebUI and copied Hermes license notices when distributing builds.

## Verification

The frontend regressions are in `src/lib/apis/hermes/hermes.test.ts`; backend
transport and application-boundary checks are in `backend/open_webui/test/test_hermes*.py`.
The transport tests use a fake native dashboard, so they do not call a model.
Live verification additionally checks a real clarification response and restores
the same persisted Hermes conversation after reconnecting.

This initial fork has local module imports. Publishing a separate module package,
adopting upstream releases, building, and deployment still need a release pipeline;
they are not automatic merely because this shell exists.
