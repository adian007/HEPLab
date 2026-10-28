# Frontend architecture

## Selected direction

React, TypeScript and Vite implement the modular single-page public project
overview with a static build. Observable Plot renders the source-backed evidence
figures. This site does not run the simulator; the local simulator remains a
separate Python application, with a desktop app planned. The Python server
serves `web/dist` at `/` and retains the current simulator workbench at
`/workbench`.

## Workspace layout

```text
web/
├── package.json                 frontend scripts and pinned dependencies
├── tsconfig.json                strict type checking
├── vite.config.ts               development proxy and static build
├── public/                      licensed static identity assets
└── src/
    ├── app/                     routes, shells, boundaries
    ├── api/                     typed transport and contract adapters
    ├── components/              shared accessible primitives
    ├── features/
    │   ├── project-home/
    │   ├── simulator/
    │   ├── runs/
    │   └── datasets/
    ├── lib/                     presentation-only utilities
    ├── state/                   ephemeral UI state
    └── styles/                  tokens, base, responsive layout
```

Each feature owns its route and presentation flow. Keep scientific computation,
randomness, model defaults and physics formulas in the Python/Rust backend.
Frontend state stores edits and view settings; a run snapshot is submitted as an
immutable, validated request through the API.

## UI state boundaries

- **Session state:** discovered capabilities and in-memory session token.
- **Draft state:** editable parameters, explicitly marked unsaved/changed.
- **Run state:** server-owned lifecycle and immutable completed output.
- **View state:** selected event/object, projection, camera and filters.
- **URL state:** navigable project pages and opaque run IDs only; no secrets or
  large payloads.

Changing parameters never silently rewrites a completed result. A new run gets a
new identity and records the exact configuration and backend.

## Rendering

Use semantic HTML for navigation, data tables, status and captions. Use
Observable Plot for bounded, source-linked statistical figures and provide
descriptive accessible labels. Reserve Canvas for the separate simulator
detector/event viewport; the project overview does not render live events.

## Design and accessibility

- Keyboard operation and visible focus for all actions; do not make canvas the
  only route to event information.
- Associate units, bounds and validation errors with every scientific input.
- Announce run status changes with a polite live region; preserve actionable
  error detail without flooding screen readers with progress events.
- Support reduced motion, high contrast, narrow windows and zoom.
- Use color plus labels/shapes for model status and object classes.
- Provide data tables and downloadable values for plotted content.

## Build and dependency policy

Use strict TypeScript, lock dependencies, production build reproducibly, and keep
the browser bundle free of secrets, event caches and native simulator binaries.
The landing page can deploy statically. Runtime API base selection must be
explicit: hosted project pages are read-only information; local simulator mode
connects only to a user-started local service. The public overview uses local
system serif and monospace font stacks. No analytics or telemetry are included.

## Development integration

During development Vite proxies `/api/v1` to the local FastAPI server. In
production the service serves the built static bundle from `/`; when it has not
been built, the original embedded client remains available as fallback. Both
clients use the same routes and server security guards.
