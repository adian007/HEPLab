# ADR-0014: Native Qt OpenGL Event Inspector 3D

- Status: Accepted
- Date: 2026-11-23

## Context

The HEPLab Event Inspector needs a native, GPU-capable 3D view for trajectories,
predicted crossings and bounded detector-envelope geometry. VTK adds substantial
deployment and scene-management dependencies. Qt Quick 3D would introduce a
separate rendering/state model alongside the verified Qt Widgets workspace.

## Decision

Use a `QOpenGLWidget` backed by Qt OpenGL and small C++20 scene structures.
Vertex arrays contain only current-event trajectories, crossings and detector
envelope primitives. Qt camera matrices control display; they never enter physics
state or exported artifacts.

A software-backed or context-loss fallback remains required. If OpenGL
initialization fails, the inspector retains synchronized XY/XZ projections and
shows an explicit unavailable-3D state.

## Consequences

- OpenGL 3.2 core or a compatibility profile is required.
- The implementation remains local to Qt and CMake.
- Display operations are bounded and independent of simulation values.
- VTK remains a future option if complex picking/VTK widgets are required.
