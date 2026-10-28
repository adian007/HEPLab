"""Dashboard backend (Phase 4, ADR-0009).

FastAPI service over cached events and run artifacts: browse the catalog,
launch/inspect runs, serve histograms and closure reports, and feed the 3D
event viewer. Binds to localhost only — no auth, no multi-user claims.
"""
