# Original Open WebUI with Hermes

HERMES_ONLY=True preserves the upstream Open WebUI interface and storage/UI
routers. The original Sidebar, Chat, composer, messages, controls, settings,
workspace, notes, calendar, folders, search, and shortcuts remain in use.

The Chat execution hook uses the native Hermes dashboard JSON-RPC protocol.
It sends the user text and raw attachments, without Open WebUI system prompts,
history replay, provider parameters, memory, filters, or tools. Hermes owns the
agent, model provider, prompt/context, tool execution, and manual approvals.
Clarification/approval requests appear in the upstream modal.

Backend configuration:
~~~dotenv
HERMES_ONLY=True
HERMES_DASHBOARD_URL=http://hermes:9119
HERMES_DASHBOARD_USERNAME=your-dashboard-user
HERMES_DASHBOARD_PASSWORD=your-dashboard-password
~~~
Keep credentials in private server configuration. Dashboard cookies stay in a
process-local cache; each connection uses a fresh one-use ticket.

For the agreed single-user private deployment, WEBUI_AUTH=False skips login
while retaining the application session. /home redirects to the original chat /.
The optional React host remains at /modules/<id>; see application-modules.md.
The older /hermes route remains available for diagnostics.

Open WebUI storage is a presentation copy, not the agent's context. The sidebar
imports metadata for the latest 200 Hermes sessions; opening one resumes its
native history. Uploads remain raw files, and Hermes processes attachments.

Open WebUI's separate AI startup, completions, provider APIs, plugins, RAG,
scheduler, and event/webhook hooks remain disabled. Some actions are not yet
mapped to native Hermes, including edit/regenerate, continue, fork/clone and
multi-model comparison. Unsupported actions report a failure rather than
modifying agent history or constructing extra prompts.

The complete user-facing list, exact API policy, disabled feature flags and
other differences are in [hermes-ui-differences.md](hermes-ui-differences.md).
The policy is implemented in backend/open_webui/utils/hermes_mode.py.

Verification includes native-frame tests, backend UI-versus-agent boundary
checks, raw upload behavior, production build, and browser verification of
the restored upstream components. Tests do not claim full upstream type checking.

Separate module publishing, upstream releases, HTTPS/installed-PWA verification
and automatic deployment still need a release workflow.
