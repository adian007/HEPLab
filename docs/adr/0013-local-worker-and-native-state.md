# ADR-0013: Local worker process and native application state

- Status: Accepted
- Date: 2026-11-23

## Context

The surviving Python scientific services and Rust numerical kernel provide most
existing backend capability. The Qt shell must not duplicate physics.

## Decision

The desktop process uses a versioned, fixed-argv local worker over length/error
bounded JSON-lines IPC. The worker owns scientific execution and result writes;
Qt owns presentation, draft project state and run-history views.

Draft configuration, running job state and committed artifact state are distinct.
The UI must never promote failed, cancelled or partial work to a completed run.

## Consequences

- Protocol and worker executable identity are checked during handshake.
- Paths and response sizes are validated.
- Cancellation requests are separate from final job status.
- Every committed artifact carries an immutable run/artifact identity and
  reproducibility metadata as implemented by the service.
- The first native implementation is a Qt Widgets shell plus a JSON-lines
  `QProcess` client. It launches one supported educational reference bench,
  polls immutable job state, supports cancellation, and exports a versioned
  desktop result envelope. It does not bundle or freeze the worker yet.
- Project manifests are versioned JSON records under the native app-data
  project directory. Opening or creating a project restarts the worker with
  that project's root, preventing run artifacts from leaking across projects.
