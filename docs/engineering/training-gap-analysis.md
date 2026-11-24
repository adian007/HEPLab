# HEPLab Education and Training Programme — repository gap analysis

Status: 2026-11-23. This document distinguishes executable capabilities from
design proposals. It supersedes desktop claims that refer to removed
Tauri/WebView or Rust IPC implementations.

## Audit conclusion

HEPLab has a usable Python public API, a synthetic Z-boson teaching workflow,
the dimuon analysis, catalog and artifact services, a JSON-lines desktop worker,
and a native C++20/Qt 6 shell that is only partially connected. The native
3D/2D event inspector, native plots, project persistence UI, and full
PYTHIA8/DELPHES workflow are not complete. Those states must remain visibly
unavailable in training material.

| Status | Meaning |
|---|---|
| Implemented | Executable code and focused tests exist |
| Verified | Implemented and exercised by the documented or automated acceptance workflow |
| Partial | A backend or contract exists but the desktop/UI workflow is incomplete |
| Runtime-gated | It can work only after the pinned external runtime and dependencies are installed |
| Proposal | Documentation or an ADR describes a target, not a delivered feature |

## Capability matrix

| Capability | Status | Evidence | Training decision |
|---|---|---|---|
| Public `heplab.run` dimuon analysis | Implemented and verified | `src/heplab/__init__.py`, `src/heplab/analyses/dimuon/run.py`, education tests | Teach in Modules 2, 4 and 5 |
| Synthetic Z practice events | Implemented and verified | `src/heplab/labs/z-boson.json`, `src/heplab/labs/z_boson.py` | Canonical beginner lab |
| Z lab Python checks and replay | Implemented and verified | `tests/test_z_boson_workflow.py`, notebook checks | Preserve; include synthetic-data label |
| Z lab desktop IPC and browser adapters | Implemented | JSON-lines worker and loopback FastAPI operations | Module 2 may teach; native Qt run controls require integration |
| JSON-lines worker | Implemented | `src/heplab/desktop/worker.py`, `operations.json` | Adapted contract for native desktop |
| Native C++20/Qt 6 shell | Partial | `desktop/src/MainWindow.cpp`, CMake targets | Navigation shell only; no false implementation claims |
| Native Qt event/plot views | Proposal | No implemented native viewport or plot | Module 3 must not describe missing native controls |
| Existing web/Canvas event display | Partial compatibility | `src/heplab/server/static/event-display-gl.js` | Do not call it native desktop functionality |
| NanoAOD/CMS ROOT reader | Implemented and scoped | `src/heplab/readers/nanoaod.py`, reader tests | CMS tutorials require supplied samples and certification |
| CERN manifest and certification | Partial | `manifests/datasets`, `manifests/certification`, CLI | Teach only checked-in/certified examples |
| PYTHIA8/DELPHES chain | Runtime-gated | `src/heplab/sim/pipeline.py`, pinned runtime inventory | Show unavailable explicitly; no default success claim |
| Rust numerical core | Implemented in bounded scope | `kernels/physics-core`, parity tests | Advanced optional cross-check only |
| Immutable artifact and replay | Implemented | `src/heplab/io/artifacts.py`, Z lab reproduction | Module 8 completion evidence |
| Notebook | One verified Z notebook | `notebooks/masterclass/z-boson.ipynb` | Baseline; expand gallery incrementally |
| Notebook gallery | Proposal | `notebooks/README.md` planned entries | No untested planned notebook may be labelled runnable |
| Hosted progress/classroom service | Proposal | `learning-platform.md` | Not required for the offline desktop design |

## Repeated outdated references

`desktop/`, the Tauri shell and the historical Rust IPC core are not present in
the current checkout. Documentation must refer to the C++20/Qt 6 rebuild and
to the surviving Python JSON-lines worker. The existing Z-boson public artifact
schema, synthetic generator and replay workflow remain unchanged.

## Requirements matrix

| ID | Requirement | Current state | Verified evidence | Next gate |
|---|---|---|---|---|
| EDU-001 | Structured 8-module catalogue | Implemented | `src/heplab/training/curriculum.json` | Add per-module accessible handbook pages |
| EDU-002 | Resumable evidence-based progress | Partial | `TrainingSession`; Z lab progress and checks | Qt persistence and real-state adapter |
| EDU-003 | Z-boson practical module | Implemented | Z lab API, worker, notebook and tests | Qt guided UI integration |
| EDU-004 | Native desktop learning panel | Partial | Qt navigation shell | Load versioned catalogue and real control states |
| EDU-005 | Event Inspector training | Blocked | No native viewport | Native viewport and event contract |
| EDU-006 | Python/Jupyter gallery | Partial | One Z notebook | Executable gallery with fixture checks |
| EDU-007 | CERN Open Data module | Partial | Reader/catalog/certification backend | Checked-in local fixture and UI workflow |
| EDU-008 | PYTHIA/DELPHES module | Runtime-gated | Discovery and execution adapter | Pinned runtime acceptance evidence |
| EDU-009 | Independent project | Implemented primitive | Reproducible Z artifact and replay | Notebook/report template |
| EDU-010 | Quality gates | Partial | pytest and notebook tools | Schema, link, notebook and cross-interface CI |

The machine-readable requirement record is
[training-gap-analysis.json](training-gap-analysis.json).
