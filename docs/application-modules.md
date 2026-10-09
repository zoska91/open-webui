# Application modules

The original Svelte application hosts complete React modules. Both the browser and installed PWA load the same
build. The registry is application metadata only; importing the sidebar does not load React.

## Add a module

1. Put a React component in a `.tsx` file under `src/lib/modules/<id>/`. Its default export receives
   `ApplicationModuleProps` from `src/lib/modules/types.ts`.
2. Add one entry to `applicationModules` in `src/lib/modules/registry.ts`: `id`, `title`, `icon`,
   `path: '/modules/<id>'`, and a lazy `load: () => import('./<id>/YourModule')`.
3. Use the existing `/modules/[moduleId]` route. The current built-in module is `dashboard` at `/modules/dashboard`.
   These additional routes are not replacements for the original sidebar; `/home` redirects to the original chat.
4. Keep styles scoped to the module's root class. Use responsive layouts and the shell's `.dark`
   class. The host owns the React root and unmounts it when navigating away, so effects must return
   their normal cleanup functions.

The dashboard is a working example in `src/lib/modules/dashboard/Dashboard.tsx`. TypeScript uses
`jsx: 'react-jsx'`, so modules can use regular JSX, hooks, and imported React components without
additional compiler setup. The registry resolves the `.tsx` file through its extension-free import.
A separate React package can export its component through the same interface.

## Runtime context

- `context.navigate(path)` uses the application's navigation.
- `context.getJson<T>('/api/...', signal)` reads same-origin application data with the app session.
  It does not expose the Hermes API key. Backend routes must enforce the appropriate permissions.
- `context.preferences` stores module-specific UI preferences in this browser, scoped to the
  current app user. These preferences do not synchronize between a phone and computer.
- `context.locale`, `context.timeZone`, and `context.userName` supply display context.

Modules implement application features and data views. They must not introduce model clients,
system prompts, agent loops, or AI processing. Hermes owns those features. Secrets and service
credentials belong in server configuration, outside the frontend bundle and Git repository.

The dashboard reads `GET /api/hermes/status`. The required field is `connected: boolean`.
It displays `version`, `model`, and `session_count` only when the server returns them; unavailable
values are omitted. Refreshing this status must not run a model. Tile visibility is a browser
preference, editable through the dashboard.

## Keep upstream updates manageable

Keep custom module code in `src/lib/modules/` and the adapter in `src/lib/components/modules/`.
The central registry is the single integration point for navigation. When adopting upstream changes,
review the module route integration and runtime authentication, then rebuild and check `/` and a module
route at phone and desktop widths. Do not overwrite upstream files with an unreviewed script.

A separate module package can later replace the local imports in the registry. Publishing a package
does not update a running deployment by itself: the app still needs a build, verification, and rollout.
This initial integration does not create repositories, release workflows, or automatic deployments.
