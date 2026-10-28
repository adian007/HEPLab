# Website, local API and desktop security

## Threat model

The static project website is public content. The local simulator is a desktop
application with a loopback HTTP service; a malicious website can attempt to
send requests to that service. Localhost binding alone is not an authorization
boundary. Run artifacts and caches can contain research data and must remain
under the user's control.

## Required controls

- Bind only to loopback; validate Host and Origin and reject untrusted origins.
- Require a random per-session token for state-changing requests, compare it in
  constant time, and keep it in process memory.
- Accept registered IDs and bounded schemas, never arbitrary paths, commands,
  executable names, image tags or code.
- Resolve artifacts under configured roots and defend traversal, symlink and
  junction escapes. Apply byte, event, object, time and memory budgets.
- Escape data as text. Treat labels, logs, metadata and event strings as untrusted.
- Redact secrets from diagnostics; do not upload telemetry or user files by
  default.
- Keep session tokens out of URLs, local storage, analytics, crash reports and
  ordinary logs.
- Package only explicitly licensed assets and disclose native dependency
  licenses/citations separately from HEPLab's Apache-2.0 source.

## Data and network behavior

Explain whether a feature reads local files, fetches CERN Open Data, or invokes a
native runtime before the action. Show cache/output locations and provenance.
The hosted site does not access the user's machine. Local mode should work
without third-party runtime network requests once dependencies and source data
are available. No analytics or remote fonts/scripts are included by default.

## Release review

Run dependency/license review, static asset inspection, API origin/CSRF/path
checks, and clean-install/update review before enabling public downloads. Record
the threat review and known limits in the release evidence. See the authoritative
service constraints in `docs/engineering/12-interfaces.md` and
`docs/engineering/13-preservation-and-trust.md`.
