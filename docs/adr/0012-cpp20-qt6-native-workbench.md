# ADR-0012: C++20 and Qt 6 native Workbench

- Status: Accepted
- Date: 2026-11-23

## Context

The historical Tauri desktop implementation is deleted. HEPLab needs a native
Windows first, cross-platform desktop application that can remain independent
of the public ASP.NET site and local web server.

## Decision

Use C++20, CMake and Qt 6 Widgets for the native application shell and Qt
OpenGL for interactive scientific rendering. Qt Widgets provides predictable
panels, native controls, accessibility hooks and no browser runtime.

Qt Quick/QML and WebEngine are not selected for the initial implementation.
Qt Quick 3D or VTK may be evaluated only after the event model and selection
protocol are established.

## Consequences

- Python remains the scientific and worker control implementation.
- Rust remains a selective numerical backend.
- The Qt shell communicates with the worker only through the versioned JSON-lines
  IPC contract.
- The public website remains a separate read-only product.
- A native C++ compiler and Qt 6 SDK are release prerequisites.
- Debug and Release CMake/Ninja builds have been established for Windows x64
  with MSVC 2022 and Qt 6.8.3.
