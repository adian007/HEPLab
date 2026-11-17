"""Small depth-tested OpenGL 2.1 renderer using Qt's existing GL bindings."""

from __future__ import annotations

from array import array
from collections.abc import Mapping
from dataclasses import dataclass
from math import dist
from typing import Any

from PySide6.QtGui import QColor, QMatrix4x4, QVector3D
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram

from .cms_geometry import MUON_CHAMBER_LAYERS

DEPTH_TEST, BLEND, CULL_FACE, SCISSOR_TEST = 0x0B71, 0x0BE2, 0x0B44, 0x0C11
TRIANGLES, LINES, FLOAT = 0x0004, 0x0001, 0x1406
ONE, SRC_ALPHA, ONE_MINUS_SRC_ALPHA = 0x0001, 0x0302, 0x0303
COLOR_BUFFER_BIT, DEPTH_BUFFER_BIT, LEQUAL = 0x4000, 0x0100, 0x0203
_RPC_THICKNESS_LIMIT_M = 0.005
_RPC_FADE_START_PX = 0.25
_RPC_FADE_END_PX = 0.40


def _partition_rpc_outlines(vertices: array) -> tuple[array, int]:
    """Pack a single RPC perimeter first, then the edges needed at close range."""
    segments = [
        (tuple(vertices[i : i + 3]), tuple(vertices[i + 3 : i + 6]))
        for i in range(0, len(vertices), 6)
    ]
    # The short thickness edges pair corresponding front and back vertices.
    paired = {}
    for a, b in segments:
        if dist(a, b) <= _RPC_THICKNESS_LIMIT_M:
            paired[a], paired[b] = b, a
    perimeter, detail = array("f"), array("f")
    seen = set()
    for a, b in segments:
        a_peer, b_peer = paired.get(a, a), paired.get(b, b)
        edge = tuple(sorted((a, b)))
        peer_edge = tuple(sorted((a_peer, b_peer)))
        key = min(edge, peer_edge) if paired.get(a_peer) == a and paired.get(b_peer) == b else edge
        target = detail if a_peer == b or key in seen else perimeter
        target.extend((*a, *b))
        seen.add(key)
    return perimeter + detail, len(perimeter) // 3

_VERTEX = """
#version 120
attribute vec3 position;
attribute vec4 color;
attribute vec3 normal;
uniform mat4 mvp;
uniform float alphaScale;
varying vec4 vertexColor;
void main() {
    float light = length(normal) < 0.1 ? 1.0
        : 0.65 + 0.35 * abs(dot(normalize(normal), normalize(vec3(0.4, -0.5, 0.8))));
    vertexColor = vec4(color.rgb * light, color.a * alphaScale);
    gl_Position = mvp * vec4(position, 1.0);
}
"""
_FRAGMENT = """
#version 120
varying vec4 vertexColor;
void main() { gl_FragColor = vertexColor; }
"""


@dataclass
class Triangle:
    vertices: tuple
    color: QColor
    normal: tuple


def face_normal(a, b, c) -> tuple[float, float, float]:
    u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = sum(x * x for x in n) ** 0.5 or 1.0
    return tuple(x / length for x in n)


class GLScene:
    """GPU buffers belong to the current widget context and are recreated on loss."""

    def __init__(self, context) -> None:
        self.functions = context.functions()
        self.functions.initializeOpenGLFunctions()
        self.program = QOpenGLShaderProgram()
        for kind, source in (
            (QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX),
            (QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT),
        ):
            if not self.program.addShaderFromSourceCode(kind, source):
                raise RuntimeError(self.program.log())
        if not self.program.link():
            raise RuntimeError(self.program.log())
        self._alpha_scale_location = self.program.uniformLocation("alphaScale")
        self.buffers = [QOpenGLBuffer() for _ in range(5)]
        for buffer in self.buffers:
            if not buffer.create():
                raise RuntimeError("OpenGL vertex buffer allocation failed")
        self._revision = None
        self._opaque_count = self._line_count = 0
        self._transparent: list[tuple[tuple[float, float, float], bytes]] = []
        self._static_mesh_ranges: dict[str, tuple[int, int]] = {}
        self._static_outline_ranges: dict[str, tuple[int, int]] = {}
        self._rpc_perimeter_count = 0
        self.last_triangle_count = 0

    def destroy(self) -> None:
        for buffer in self.buffers:
            buffer.destroy()
        self.program.removeAllShaders()

    @staticmethod
    def _vertex(out: array, point, color: QColor, normal=(0.0, 0.0, 0.0)) -> None:
        out.extend((*point, color.redF(), color.greenF(), color.blueF(), color.alphaF(), *normal))

    def _upload(self, index: int, data: array | bytes) -> int:
        buffer = self.buffers[index]
        buffer.bind()
        raw = data if isinstance(data, bytes) else data.tobytes()
        buffer.allocate(raw, len(raw))
        buffer.release()
        return len(raw) // 40

    def upload_static_geometry(
        self,
        meshes: Mapping[str, array],
        outlines: Mapping[str, array],
        colors: Mapping[str, QColor],
    ) -> None:
        """Upload immutable position-only CMS meshes once per GL context.

        CMS geometry is batched by subsystem into two static VBOs. This avoids
        creating hundreds of thousands of Python triangle objects or uploading
        unchanged detector geometry on each event update.
        """
        self._static_mesh_ranges = {}
        self._static_outline_ranges = {}
        self._rpc_perimeter_count = 0
        packed_meshes, packed_outlines = array("f"), array("f")

        def append_colored(target: array, vertices: array, color: QColor) -> None:
            rgba = (color.redF(), color.greenF(), color.blueF(), 1.0)
            for index in range(0, len(vertices), 3):
                target.extend(vertices[index : index + 3])
                target.extend(rgba)

        for layer, vertices in meshes.items():
            if len(vertices) % 9:
                raise ValueError(f"CMS mesh {layer!r} is not a sequence of triangles")
            start = len(packed_meshes) // 7
            append_colored(packed_meshes, vertices, colors[layer])
            self._static_mesh_ranges[layer] = (start, len(vertices) // 3)
        for layer, vertices in outlines.items():
            if len(vertices) % 6:
                raise ValueError(f"CMS outline {layer!r} is not a sequence of line pairs")
            if layer == "rpc":
                vertices, self._rpc_perimeter_count = _partition_rpc_outlines(vertices)
            start = len(packed_outlines) // 7
            append_colored(packed_outlines, vertices, colors[layer])
            self._static_outline_ranges[layer] = (start, len(vertices) // 3)
        self._upload_positions(3, packed_meshes)
        self._upload_positions(4, packed_outlines)

    def _upload_positions(self, index: int, data: array) -> None:
        buffer = self.buffers[index]
        buffer.bind()
        raw = data.tobytes()
        buffer.allocate(raw, len(raw))
        buffer.release()

    def _draw(self, index: int, count: int, mode: int) -> None:
        if not count:
            return
        self.buffers[index].bind()
        self.functions.glUniform1f(self._alpha_scale_location, 1.0)
        for name, offset, size in (("position", 0, 3), ("color", 12, 4), ("normal", 28, 3)):
            self.program.enableAttributeArray(name)
            self.program.setAttributeBuffer(name, FLOAT, offset, size, 40)
        self.functions.glDrawArrays(mode, 0, count)
        for name in ("position", "color", "normal"):
            self.program.disableAttributeArray(name)
        self.buffers[index].release()

    def _draw_static(
        self,
        index: int,
        start: int,
        count: int,
        mode: int,
        alpha: float,
    ) -> None:
        if not count:
            return
        self.buffers[index].bind()
        self.functions.glUniform1f(self._alpha_scale_location, min(1.0, max(0.0, alpha)))
        self.program.enableAttributeArray("position")
        self.program.enableAttributeArray("color")
        self.program.setAttributeBuffer("position", FLOAT, 0, 3, 28)
        self.program.setAttributeBuffer("color", FLOAT, 12, 4, 28)
        self.program.disableAttributeArray("normal")
        self.functions.glDrawArrays(mode, start, count)
        self.program.disableAttributeArray("position")
        self.buffers[index].release()

    def render(
        self,
        widget,
        plot,
        frame: dict[str, Any],
        triangles: list[Triangle],
        lines: list[tuple],
        revision: Any,
        background: QColor,
        static_styles: Mapping[str, tuple[QColor, float]] | None = None,
    ) -> None:
        f = self.functions
        ratio = widget.devicePixelRatioF()
        viewport = (
            round(plot.x() * ratio),
            round((widget.height() - plot.bottom()) * ratio),
            max(1, round(plot.width() * ratio)),
            max(1, round(plot.height() * ratio)),
        )
        f.glEnable(SCISSOR_TEST)
        f.glScissor(*viewport)
        f.glViewport(*viewport)
        f.glClearColor(background.redF(), background.greenF(), background.blueF(), 1.0)
        f.glDepthMask(True)
        f.glClear(COLOR_BUFFER_BIT | DEPTH_BUFFER_BIT)
        f.glEnable(DEPTH_TEST)
        f.glDepthFunc(LEQUAL)
        f.glDisable(CULL_FACE)  # translucent shells are intentionally visible from both sides
        f.glEnable(BLEND)
        # Keep the framebuffer opaque for QPainter and framebuffer readback.
        f.glBlendFuncSeparate(SRC_ALPHA, ONE_MINUS_SRC_ALPHA, ONE, ONE_MINUS_SRC_ALPHA)

        view, projection = QMatrix4x4(), QMatrix4x4()
        target, forward = frame["target"], frame["forward"]
        eye = [target[i] + forward[i] * frame["distance"] for i in range(3)]
        view.lookAt(QVector3D(*eye), QVector3D(*target), QVector3D(*frame["up"]))
        near, far = 0.01, max(100.0, frame["distance"] * 5.0)
        if frame.get("orthographic"):
            half_h = plot.height() * frame["distance"] / (2 * frame["focal"])
            half_w = half_h * plot.width() / max(1, plot.height())
            projection.ortho(-half_w, half_w, -half_h, half_h, near, far)
        else:
            import math

            fov = math.degrees(2 * math.atan(plot.height() / (2 * frame["focal"])))
            projection.perspective(fov, plot.width() / max(1, plot.height()), near, far)
        self.program.bind()
        self.program.setUniformValue("mvp", projection * view)

        if revision != self._revision:
            data = array("f")
            self._transparent = []
            for triangle in triangles:
                opaque = triangle.color.alphaF() >= 0.99
                vertices = data if opaque else array("f")
                for point in triangle.vertices:
                    self._vertex(vertices, point, triangle.color, triangle.normal)
                if not opaque:
                    a, b, c = triangle.vertices
                    center = tuple((a[i] + b[i] + c[i]) / 3 for i in range(3))
                    self._transparent.append((center, vertices.tobytes()))
            self._opaque_count = self._upload(0, data)
            data = array("f")
            for a, b, color in lines:
                self._vertex(data, a, color)
                self._vertex(data, b, color)
            self._line_count = self._upload(2, data)
            self._revision = revision
        f.glDepthMask(True)
        self._draw(0, self._opaque_count, TRIANGLES)
        # CMS systems are translucent display surfaces. Draw them in the
        # caller's outer-to-inner order without depth writes so inner systems
        # remain visible through the detector envelope.
        f.glDepthMask(False)
        f.glLineWidth(1.0)
        rpc_thickness_px = frame["focal"] * ratio * _RPC_THICKNESS_LIMIT_M / frame["distance"]
        for layer, (_color, alpha) in (static_styles or {}).items():
            mesh_range = self._static_mesh_ranges.get(layer)
            if mesh_range is not None:
                self._draw_static(3, *mesh_range, TRIANGLES, alpha)
            outline_range = self._static_outline_ranges.get(layer)
            if outline_range is not None:
                start, count = outline_range
                outline_alpha = (
                    min(0.20, 3 * alpha)
                    if layer in MUON_CHAMBER_LAYERS
                    else min(1.0, alpha + 0.28)
                )
                if layer != "rpc" or rpc_thickness_px >= _RPC_FADE_END_PX:
                    self._draw_static(4, start, count, LINES, outline_alpha)
                    continue

                perimeter_count = self._rpc_perimeter_count
                self._draw_static(4, start, perimeter_count, LINES, outline_alpha)
                if rpc_thickness_px > _RPC_FADE_START_PX and outline_alpha > 0:
                    t = (rpc_thickness_px - _RPC_FADE_START_PX) / (
                        _RPC_FADE_END_PX - _RPC_FADE_START_PX
                    )
                    fade = t * t * (3 - 2 * t)
                    self._draw_static(
                        4, start + perimeter_count, count - perimeter_count, LINES,
                        outline_alpha * fade,
                    )
        if self._transparent:
            # Eye position adds the same depth offset to every triangle.
            x, y, z = forward
            ordered = sorted(
                self._transparent,
                key=lambda item: item[0][0] * x + item[0][1] * y + item[0][2] * z,
            )
            count = self._upload(1, b"".join(vertices for _, vertices in ordered))
            self._draw(1, count, TRIANGLES)
        f.glLineWidth(1.5)
        self._draw(2, self._line_count, LINES)
        f.glDepthMask(True)
        self.program.release()
        f.glDisable(SCISSOR_TEST)
        f.glDisable(DEPTH_TEST)
        f.glDisable(BLEND)
        self.last_triangle_count = len(triangles)
