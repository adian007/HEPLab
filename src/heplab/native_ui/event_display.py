"""Small native Qt event viewer for existing HEPLab event payloads.

This widget is deliberately a display adapter: it reads the ``tracks``,
``trajectory.crossings`` and ``geometry.surfaces`` fields that are already in
an event payload.  It does not build or infer detector hits, tracks, or
ancestry.
"""

from __future__ import annotations

import math
from array import array
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from .cms_geometry import load_cms_geometry
from .design_tokens import FONT_FAMILY, FONT_MONO, FONT_SMALL_PT, LIGHT, PDG_COLORS, SURFACE_COLORS
from .display_geometry import build_chamber_prisms, build_chambers
from .gl_scene import GLScene, Triangle, face_normal

MUON_FILL_OPACITY_PERCENT = 3

_LIGHT_BG, _PANEL_BG = QColor(LIGHT["canvas"]), QColor(LIGHT["panel"])
_PANEL_LINE, _TEXT = QColor(LIGHT["border"]), QColor(LIGHT["text"])
_MUTED, _GRID, _AXIS = (QColor(LIGHT[k]) for k in ("muted", "grid", "axis"))
_SURFACE_COLORS = {key: QColor(value) for key, value in SURFACE_COLORS.items()}
_PDG_COLORS = {key: QColor(value) for key, value in PDG_COLORS.items()}

_Vec3 = tuple[float, float, float]
_Point2 = tuple[float, float]
_PRISM_EDGES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)
_PDG_NAMES = {
    "11": "Electron",
    "-11": "Positron",
    "13": "Muon −",
    "-13": "Muon +",
    "22": "Photon",
    "211": "Pion +",
    "-211": "Pion −",
}
_CMS_MESH_LAYERS = {
    "pixels": ("pixel",),
    "strips": ("strips",),
    "ecal": ("ecal",),
    "hcal": ("hcal",),
    "muon": ("dt", "csc", "rpc"),
}
_CMS_STYLE_ORDER = ("yoke", "solenoid", "muon", "hcal", "ecal", "strips", "pixels")
_CMS_LABELS = {
    "pixels": "Pixel tracker",
    "strips": "Strip tracker",
    "ecal": "ECAL",
    "hcal": "HCAL",
    "muon": "Muon chambers · DT / CSC / RPC",
    "solenoid": "Solenoid cryostat envelope",
    "yoke": "Return-yoke envelope",
}
_CMS_COLOR_KEYS = {"pixels": "pixel"}
_CMS_ENVELOPE_BOUNDS = {
    # CMS magnetic-system dimensions: cryostat inner diameter 5.945 m and
    # coil envelope length 13 m. The drawn cylinder is explicitly an envelope.
    "solenoid": ((-2.9725, -2.9725, -6.5), (2.9725, 2.9725, 6.5)),
    # Twelve-sided yoke outer envelope, 13.99 m barrel inscribed diameter,
    # 13.91 m endcap inscribed diameter, 21.61 m total length.
    "yoke": ((-7.24, -7.24, -10.805), (7.24, 7.24, 10.805)),
}


def _cms_reference_envelopes() -> dict[str, array]:
    """Create low-cost line cages from published CMS magnet dimensions.

    These are display envelopes, not solids or transport geometry. Dimensions
    are from the CMS magnetic-system model (CERN CDS 2773274).
    """
    result: dict[str, array] = {"solenoid": array("f"), "yoke": array("f")}

    def ring(radius: float, z: float, sides: int) -> list[_Vec3]:
        return [
            (
                radius * math.cos(2 * math.pi * index / sides),
                radius * math.sin(2 * math.pi * index / sides),
                z,
            )
            for index in range(sides)
        ]

    def add_ring(lines: array, points: list[_Vec3]) -> None:
        for first, second in zip(points, points[1:] + points[:1], strict=False):
            lines.extend((*first, *second))

    cylinder_radius, cylinder_half_length = 5.945 / 2, 13.0 / 2
    cylinder_segments = 64
    lower_cylinder = ring(cylinder_radius, -cylinder_half_length, cylinder_segments)
    upper_cylinder = ring(cylinder_radius, cylinder_half_length, cylinder_segments)
    for z in (-cylinder_half_length, cylinder_half_length):
        points = lower_cylinder if z < 0 else upper_cylinder
        add_ring(result["solenoid"], points)
    for index in range(0, cylinder_segments, 8):
        lower, upper = lower_cylinder[index], upper_cylinder[index]
        result["solenoid"].extend((*lower, *upper))

    sides, half_length = 12, 21.61 / 2
    barrel_radius = (13.99 / 2) / math.cos(math.pi / sides)
    endcap_radius = (13.91 / 2) / math.cos(math.pi / sides)
    lower = ring(barrel_radius, -half_length, sides)
    upper = ring(barrel_radius, half_length, sides)
    add_ring(result["yoke"], lower)
    add_ring(result["yoke"], upper)
    for first, second in zip(lower, upper, strict=True):
        result["yoke"].extend((*first, *second))
    # Endcap outlines use their separately published inscribed diameter.
    add_ring(result["yoke"], ring(endcap_radius, -half_length, sides))
    add_ring(result["yoke"], ring(endcap_radius, half_length, sides))
    return result


class EventDisplayWidget(QOpenGLWidget):
    """Paint event tracks and supplied detector surfaces on an OpenGL canvas.

    Projections accepted by :meth:`set_projection` are ``"xy+xz"`` (the
    synchronized orthographic pair), ``"xy"``, ``"xz"`` and ``"3d"`` (a
    perspective camera with orbit controls). Drag to orbit in 3D or pan in
    orthographic views, wheel to zoom, and press ``R`` to reset.

    Layer keys are ``tracks``, ``ideal_trajectories``, ``crossings``,
    ``surfaces``, ``pixels``, ``solenoid`` and ``guides``. Missing layers
    remain empty; in particular, no hit markers are inferred from crossings.
    """

    track_selected = Signal(dict)
    chamber_selected = Signal(dict)
    renderer_status = Signal(str)

    _PROJECTIONS = {"xy+xz", "xy", "xz", "3d"}
    _ALIASES = {"pair": "xy+xz", "isometric": "3d", "iso": "3d"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        surface_format = QSurfaceFormat()
        surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        surface_format.setVersion(2, 1)
        surface_format.setDepthBufferSize(24)
        surface_format.setSamples(0)
        self.setFormat(surface_format)
        self.setObjectName("heplabEventDisplay")
        self.setMinimumSize(420, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), _LIGHT_BG)
        palette.setColor(self.foregroundRole(), _TEXT)
        self.setPalette(palette)
        self.setToolTip(
            "3D: drag to orbit · projections: drag to pan · wheel to zoom · "
            "click a track to select · R resets view"
        )

        self._payload: dict[str, Any] = {}
        self._tracks: list[dict[str, Any]] = []
        self._surfaces: list[dict[str, Any]] = []
        self._cms_geometry = load_cms_geometry()
        self._cms_envelopes = _cms_reference_envelopes()
        self._chambers = build_chambers()
        self._gl_scene: GLScene | None = None
        self._gl_error = ""
        self._revision = 0
        self._scene_cache: tuple | None = None
        self._world_cache: tuple | None = None
        self._fit_cache: tuple | None = None
        self._selected_chamber: dict | None = None
        self._selected_track: dict | None = None
        self._fit_mode = "detector"
        self._perspective = True
        self._thickness_scale = 1.0
        self._color_mode = "pdg"
        self._opacity = {
            "pixels": 0.16,
            "strips": 0.18,
            "ecal": 0.22,
            "hcal": 0.16,
            "muon": MUON_FILL_OPACITY_PERCENT / 100,
            "solenoid": 0.08,
            "yoke": 0.18,
            "guides": 0.10,
            "irpc_re3": 0.28,
            "irpc_re4": 0.28,
        }
        self._projection = "xy+xz"
        self._layers = {
            "tracks": True,
            "ideal_trajectories": True,
            "crossings": True,
            "surfaces": True,
            "pixels": True,
            "strips": True,
            "ecal": True,
            "hcal": True,
            "muon": True,
            "solenoid": True,
            "yoke": True,
            "guides": True,
            "irpc_re3": True,
            "irpc_re4": True,
            "irpc_internals": False,
        }
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._camera_yaw = math.radians(38.0)
        self._camera_pitch = math.radians(35.0)
        self._press_pos: QPointF | None = None
        self._press_pan = QPointF(0.0, 0.0)
        self._press_yaw = self._camera_yaw
        self._press_pitch = self._camera_pitch
        self._dragged = False

    def set_event(self, payload: Mapping[str, Any] | None) -> None:
        """Display a payload as received; unsupported fields are ignored."""
        self._payload = dict(payload) if isinstance(payload, Mapping) else {}
        raw_tracks = self._payload.get("tracks")
        self._tracks = (
            [dict(track) for track in raw_tracks if isinstance(track, Mapping)]
            if isinstance(raw_tracks, list)
            else []
        )

        geometry = self._payload.get("geometry")
        raw_surfaces = geometry.get("surfaces") if isinstance(geometry, Mapping) else None
        self._surfaces = (
            [dict(surface) for surface in raw_surfaces if isinstance(surface, Mapping)]
            if isinstance(raw_surfaces, list)
            else []
        )

        self._reset_view()
        self._selected_track = self._selected_chamber = None
        self._revision += 1
        self.update()

    def initializeGL(self) -> None:  # noqa: N802
        try:
            self._gl_scene = GLScene(self.context())
            meshes = {
                layer_id: geometry.positions
                for layer_id, geometry in self._cms_geometry.items()
            }
            outlines = {
                layer_id: geometry.outlines
                for layer_id, geometry in self._cms_geometry.items()
            }
            outlines.update(self._cms_envelopes)
            layer_colors = {
                layer_id: QColor(
                    _SURFACE_COLORS[
                        "muon"
                        if layer_id in {"dt", "csc", "rpc"}
                        else layer_id
                    ]
                )
                for layer_id in self._cms_geometry
            }
            layer_colors["solenoid"] = QColor(_SURFACE_COLORS["solenoid"])
            layer_colors["yoke"] = QColor(_SURFACE_COLORS["yoke"])
            self._gl_scene.upload_static_geometry(meshes, outlines, layer_colors)
            self.context().aboutToBeDestroyed.connect(self._release_gl)
            self._gl_error = ""
            self.renderer_status.emit("OpenGL 2.1 · depth-tested meshes")
        except (RuntimeError, TypeError, AttributeError) as exc:
            self._gl_error = str(exc)
            self.renderer_status.emit(f"Outline fallback · {exc}")

    def _release_gl(self) -> None:
        if self._gl_scene is not None:
            self.makeCurrent()
            self._gl_scene.destroy()
            self._gl_scene = None
            self.doneCurrent()

    def set_layer_opacity(self, key: str, value: float) -> None:
        self._opacity[key] = min(1.0, max(0.0, float(value)))
        self._revision += 1
        self.update()

    def set_thickness_exaggeration(self, value: float) -> None:
        self._thickness_scale = min(100.0, max(1.0, float(value)))
        self._revision += 1
        self.update()

    def set_color_mode(self, mode: str) -> None:
        self._color_mode = "pt" if mode == "pt" else "pdg"
        self._revision += 1
        self.update()

    def set_perspective(self, enabled: bool) -> None:
        self._perspective = bool(enabled)
        self.update()

    def set_view_preset(self, name: str) -> None:
        self._camera_yaw, self._camera_pitch = {
            "front": (0.0, math.pi / 2 - 0.001),
            "side": (math.pi / 2, 0.0),
            "top": (0.0, math.pi / 2 - 0.001),
            "isometric": (math.radians(38), math.radians(35)),
        }.get(name, (math.radians(38), math.radians(35)))
        self._fit_mode = "detector"
        self._zoom, self._pan = 1.0, QPointF()
        self._fit_cache = None
        self.update()

    def fit_to(self, mode: str) -> None:
        self._fit_mode = mode if mode in {"event", "detector", "selection"} else "detector"
        self._zoom, self._pan = 1.0, QPointF()
        self._fit_cache = None
        self.update()

    def reset_camera(self) -> None:
        self._reset_view()
        self.update()

    def select_track(self, track: dict) -> None:
        self._selected_track, self._selected_chamber = track, None
        self._revision += 1
        self.update()

    def set_projection(self, name: str) -> None:
        """Set ``xy+xz``, ``xy``, ``xz`` or isometric ``3d`` projection."""
        projection = self._ALIASES.get(str(name).strip().lower(), str(name).strip().lower())
        if projection not in self._PROJECTIONS:
            raise ValueError(f"unknown event-display projection: {name!r}")
        if projection != self._projection:
            self._projection = projection
            self.update()

    def set_layers(self, layers: Mapping[str, Any]) -> None:
        """Update track, crossing, and independent detector-surface visibility."""
        if not isinstance(layers, Mapping):
            raise TypeError("layers must be a mapping")
        aliases = {"trajectory": "ideal_trajectories", "guide_surfaces": "guides"}
        for key, value in layers.items():
            canonical = aliases.get(str(key), str(key))
            if canonical in self._layers:
                self._layers[canonical] = bool(value)
        self._revision += 1
        self.update()

    def paintGL(self) -> None:  # noqa: N802 - Qt override
        """Render the low-complexity event scene with Qt's OpenGL paint engine."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), _LIGHT_BG)

        specs = self._panel_specs()
        for projection, rect, label in specs:
            self._draw_panel(painter, projection, rect, label)

        painter.end()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.RightButton:
            self._reset_view()
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._press_pos = QPointF(event.position())
            self._press_pan = QPointF(self._pan)
            self._press_yaw = self._camera_yaw
            self._press_pitch = self._camera_pitch
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current = QPointF(event.position())
            delta = current - self._press_pos
            if math.hypot(delta.x(), delta.y()) > 3.0:
                self._dragged = True
            if self._dragged:
                if self._projection == "3d":
                    self._camera_yaw = self._press_yaw + delta.x() * 0.008
                    self._camera_pitch = min(
                        math.radians(85.0),
                        max(math.radians(-85.0), self._press_pitch + delta.y() * 0.008),
                    )
                else:
                    self._pan = self._press_pan + delta
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            if not self._dragged:
                selected = self._hit_test(QPointF(event.position()))
                chamber = self._hit_test_chamber(QPointF(event.position()))
                if (
                    selected is not None
                    and chamber is not None
                    and self._projection == "3d"
                    and self._layers["irpc_internals"]
                    and self._opacity.get("irpc_internals", 1.0) >= 0.99
                    and len(self._display_prisms(chamber)) > 1
                    and self._chamber_pick_depth < self._track_pick_depth
                ):
                    selected = None
                if selected is not None:
                    self.select_track(selected)
                    self.track_selected.emit(dict(selected))
                else:
                    if chamber is not None:
                        self._selected_chamber, self._selected_track = chamber, None
                        self._revision += 1
                        self.chamber_selected.emit(dict(chamber))
                        self.update()
            self._press_pos = None
            self._dragged = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        position = QPointF(event.position())
        panel = self._panel_at(position)
        if panel is None:
            panel = self._panel_specs()[0] if self._panel_specs() else None
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        new_zoom = min(30.0, max(0.15, self._zoom * factor))
        if self._projection != "3d" and panel is not None:
            projection, rect, _label = panel
            plot = self._plot_rect(rect)
            bounds = self._projected_bounds(projection)
            base_scale = self._base_scale(bounds, plot)
            if base_scale > 0:
                center = plot.center()
                ratio = new_zoom / self._zoom
                self._pan = position - center - (position - center - self._pan) * ratio
        self._zoom = new_zoom
        self.update()
        event.accept()

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_R:
            self._reset_view()
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def _reset_view(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._camera_yaw = math.radians(38.0)
        self._camera_pitch = math.radians(35.0)
        self._fit_mode = "detector"
        self._fit_cache = None

    def _panel_specs(self) -> list[tuple[str, QRectF, str]]:
        bounds = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        if self._projection == "xy+xz":
            gap = 8.0
            panel_width = max(1.0, (bounds.width() - gap) / 2.0)
            left = QRectF(bounds.left(), bounds.top(), panel_width, bounds.height())
            right = QRectF(left.right() + gap, bounds.top(), panel_width, bounds.height())
            return [("xy", left, "XY · transverse (m)"), ("xz", right, "XZ · longitudinal (m)")]
        labels = {
            "xy": "XY · transverse (m)",
            "xz": "XZ · longitudinal (m)",
            "3d": f"{'Perspective' if self._perspective else 'Orthographic'} 3D · metres",
        }
        label = labels[self._projection]
        return [(self._projection, bounds, label)]

    def _panel_at(self, point: QPointF) -> tuple[str, QRectF, str] | None:
        for spec in self._panel_specs():
            if spec[1].contains(point):
                return spec
        return None

    @staticmethod
    def _plot_rect(rect: QRectF) -> QRectF:
        return rect.adjusted(48, 32, -12, -34)

    def _draw_panel(self, painter: QPainter, projection: str, rect: QRectF, label: str) -> None:
        painter.setPen(QPen(_PANEL_LINE, 1.0))
        painter.setBrush(_PANEL_BG)
        painter.drawRoundedRect(rect, 3.0, 3.0)

        painter.setPen(_TEXT)
        painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT, QFont.Weight.DemiBold))
        painter.drawText(
            rect.adjusted(10, 6, -8, -rect.height() + 25),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )

        if projection == "3d":
            self._draw_3d_scene(painter, rect)
            return

        plot = self._plot_rect(rect)
        bounds = self._projected_bounds(projection)
        transform = self._transform(bounds, plot)
        self._draw_grid(painter, projection, plot, bounds, transform)
        painter.save()
        painter.setClipRect(plot)
        self._draw_cms_bounds_2d(painter, projection, transform)
        if self._layers["surfaces"]:
            self._draw_surfaces(painter, projection, transform)
        if self._layers["crossings"]:
            self._draw_crossings(painter, projection, transform)
        if self._layers["ideal_trajectories"]:
            self._draw_ideal_trajectories(painter, projection, transform)
        if self._layers["tracks"]:
            self._draw_tracks(painter, projection, transform)
        self._draw_chambers_2d(painter, projection, transform)
        painter.restore()
        self._draw_scale(painter, plot, transform[0])
        self._draw_legend(painter, plot)

        painter.setPen(_MUTED)
        painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT))
        painter.drawText(
            QRectF(rect.left() + 8, rect.bottom() - 24, rect.width() - 16, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Drag to pan · wheel to zoom · R resets view",
        )

        if not self._tracks and not self._surfaces and not self._visible_chambers():
            painter.setPen(_MUTED)
            painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT + 2))
            painter.drawText(
                plot, Qt.AlignmentFlag.AlignCenter, "No event tracks or geometry in this payload"
            )

    def _draw_grid(
        self,
        painter: QPainter,
        projection: str,
        plot: QRectF,
        bounds: tuple[float, float, float, float],
        transform: tuple[float, QPointF],
    ) -> None:
        x0, x1, y0, y1 = bounds
        scale, origin = transform
        # Grid ticks are view references only; they do not add event data.
        spacing = _nice_step(max(x1 - x0, y1 - y0) / 6.0)
        if spacing <= 0:
            spacing = 1.0
        painter.save()
        painter.setClipRect(plot)
        grid_pen = QPen(_GRID, 1.0)
        axis_pen = QPen(_AXIS, 1.1)
        painter.setFont(QFont(FONT_MONO, FONT_SMALL_PT))

        start_x = math.floor(x0 / spacing) * spacing
        x = start_x
        while x <= x1 + spacing * 0.5:
            point = self._map((x, 0.0), scale, origin)
            painter.setPen(axis_pen if abs(x) < spacing * 1e-8 else grid_pen)
            painter.drawLine(QPointF(point.x(), plot.top()), QPointF(point.x(), plot.bottom()))
            if abs(x) > spacing * 1e-8:
                painter.setPen(_MUTED)
                painter.drawText(
                    QRectF(point.x() - 24, plot.bottom() + 3, 48, 14),
                    Qt.AlignmentFlag.AlignHCenter,
                    _fmt(x),
                )
            x += spacing

        start_y = math.floor(y0 / spacing) * spacing
        y = start_y
        while y <= y1 + spacing * 0.5:
            point = self._map((0.0, y), scale, origin)
            painter.setPen(axis_pen if abs(y) < spacing * 1e-8 else grid_pen)
            painter.drawLine(QPointF(plot.left(), point.y()), QPointF(plot.right(), point.y()))
            if abs(y) > spacing * 1e-8:
                painter.setPen(_MUTED)
                painter.drawText(
                    QRectF(plot.left() - 43, point.y() - 7, 37, 14),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    _fmt(y),
                )
            y += spacing

        painter.setPen(_AXIS)
        painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT, QFont.Weight.DemiBold))
        axes_by_projection = {
            "xy": ("x [m]", "y [m]"),
            "xz": ("x [m]", "z [m]"),
            "3d": ("projected x [m]", "projected y [m]"),
        }
        axes = axes_by_projection[projection]
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 17, plot.width(), 14),
            Qt.AlignmentFlag.AlignHCenter,
            axes[0],
        )
        painter.save()
        painter.translate(plot.left() - 37, plot.center().y())
        painter.rotate(-90)
        painter.drawText(
            QRectF(-plot.height() / 2.0, -7, plot.height(), 14),
            Qt.AlignmentFlag.AlignHCenter,
            axes[1],
        )
        painter.restore()
        painter.restore()

    def _draw_tracks(
        self, painter: QPainter, projection: str, transform: tuple[float, QPointF]
    ) -> None:
        painter.save()
        for track in self._tracks:
            points = _raw_track_points(track)
            if len(points) < 2:
                continue
            projected = [self._project(point, projection) for point in points]
            color = self._color_for_track(track)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            screen = [self._map(point, *transform) for point in projected]
            for first, second in zip(screen, screen[1:], strict=False):
                painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(first, second)

        painter.restore()

    def _draw_ideal_trajectories(
        self, painter: QPainter, projection: str, transform: tuple[float, QPointF]
    ) -> None:
        """Draw explicitly supplied ideal-solenoid trajectory samples."""
        painter.save()
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        for track in self._tracks:
            trajectory = track.get("trajectory")
            model = trajectory.get("model") if isinstance(trajectory, Mapping) else None
            if not isinstance(model, str) or not model.startswith("ideal-solenoid"):
                continue
            points = _trajectory_points(track)
            if len(points) < 2:
                continue
            screen = [self._map(self._project(point, projection), *transform) for point in points]
            painter.setPen(
                QPen(
                    _MUTED,
                    1.05,
                    Qt.PenStyle.DashLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPolyline(QPolygonF(screen))
        painter.restore()

    def _draw_crossings(
        self, painter: QPainter, projection: str, transform: tuple[float, QPointF]
    ) -> None:
        painter.save()
        painter.setPen(QPen(QColor(LIGHT["warning"]), 1.4))
        painter.setBrush(QColor(LIGHT["panel"]))
        for track in self._tracks:
            trajectory = track.get("trajectory")
            crossings = trajectory.get("crossings") if isinstance(trajectory, Mapping) else None
            if not isinstance(crossings, list):
                continue
            for crossing in crossings:
                if not isinstance(crossing, Mapping):
                    continue
                position = _vec3(crossing.get("position_m"))
                if position is None:
                    continue
                x, y = self._map(self._project(position, projection), *transform)
                diamond = QPolygonF(
                    [QPointF(x, y - 4), QPointF(x + 4, y), QPointF(x, y + 4), QPointF(x - 4, y)]
                )
                painter.drawPolygon(diamond)
        painter.restore()

    def _draw_surfaces(
        self, painter: QPainter, projection: str, transform: tuple[float, QPointF]
    ) -> None:
        if not self._layers["surfaces"]:
            return
        painter.save()
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        for surface in self._visible_surfaces():
            lines = _surface_lines(surface)
            if not lines:
                continue
            subsystem = str(surface.get("subsystem", ""))
            color = QColor(_SURFACE_COLORS.get(subsystem, _AXIS))
            layer = {"pixel": "pixels", "solenoid": "solenoid"}.get(subsystem, "guides")
            color.setAlphaF(min(1.0, self._opacity[layer] + 0.2))
            painter.setPen(QPen(color, 1.0, Qt.PenStyle.DashLine))
            for points in lines:
                projected = [
                    self._map(self._project(point, projection), *transform) for point in points
                ]
                if len(projected) > 1:
                    painter.drawPolyline(QPolygonF(projected))
        painter.restore()

    def _draw_3d_scene(self, painter: QPainter, panel: QRectF) -> None:
        """Draw depth-tested scene meshes, then paint legible screen overlays."""
        plot = panel.adjusted(14, 34, -14, -38)
        points = self._visible_world_points()
        if not points:
            painter.setPen(_MUTED)
            painter.drawText(
                plot, Qt.AlignmentFlag.AlignCenter, "No event geometry or tracks to display"
            )
            return

        frame = self._camera_frame(points, plot)
        painter.save()
        painter.setClipRect(plot)
        painter.fillRect(plot, _LIGHT_BG)
        if self._gl_scene is not None:
            triangles, lines, revision = self._scene_geometry()
            painter.beginNativePainting()
            try:
                self._gl_scene.render(
                    self,
                    plot,
                    frame,
                    triangles,
                    lines,
                    revision,
                    _LIGHT_BG,
                    self._visible_cms_styles(),
                )
            except (RuntimeError, TypeError, AttributeError) as exc:
                self._gl_error = str(exc)
                self._gl_scene.destroy()
                self._gl_scene = None
                self.renderer_status.emit(f"Outline fallback · {exc}")
                # The failed frame was fitted to the full GL scene.
                frame = self._camera_frame(self._visible_world_points(), plot)
            finally:
                painter.endNativePainting()
        if self._gl_scene is None:
            # GL shader/context failures keep a clearly labelled outline-only view usable.
            self._draw_3d_floor(painter, plot, frame)
            self._draw_chambers_fallback(painter, frame)
            if self._layers["tracks"]:
                self._draw_3d_tracks(painter, frame)
            if self._layers["ideal_trajectories"]:
                self._draw_3d_ideal_trajectories(painter, frame)
        if self._layers["crossings"]:
            self._draw_3d_crossings(painter, frame)
        self._draw_3d_axis_triad(painter, plot, frame)
        self._draw_scale(painter, plot, frame["focal"] / frame["distance"], "at focus plane")
        self._draw_legend(painter, plot, show_static=self._gl_scene is not None)
        painter.restore()

        painter.setPen(_MUTED)
        painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT))
        painter.drawText(
            QRectF(panel.left() + 10, panel.bottom() - 26, panel.width() - 20, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ("OpenGL · depth tested" if self._gl_scene else "Outline fallback")
            + "  |  Drag to orbit · wheel to zoom · R reset · click to inspect",
        )
        painter.drawText(
            panel.adjusted(10, 5, -12, -panel.height() + 25),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "CMS detector · tracker + calorimeters + muon system · referenced envelopes",
        )
        if self._layers["irpc_internals"] and self._thickness_scale > 1:
            painter.setPen(QColor(LIGHT["selection"]))
            painter.drawText(
                plot.adjusted(10, 0, -10, -8),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                f"Layer thickness ×{self._thickness_scale:g} · display only",
            )

    def _visible_chambers(self) -> list[dict]:
        return [
            c
            for c in self._chambers
            if self._layers["irpc_re3" if c["station"] == "RE3/1" else "irpc_re4"]
        ]

    def _display_prisms(self, chamber: dict) -> list[dict]:
        selected = self._selected_chamber and chamber["id"] == self._selected_chamber["id"]
        detail = self._layers["irpc_internals"] and (
            selected or (self._zoom >= 2.0 and self._selected_chamber is None)
        )
        return build_chamber_prisms(
            chamber, detail=bool(detail), thickness_scale=self._thickness_scale
        )

    def _scene_geometry(self) -> tuple:
        from .display_geometry import TRIANGLES as prism_triangles

        detail = self._layers["irpc_internals"] and (
            self._zoom >= 2.0 or self._selected_chamber is not None
        )
        key = (self._revision, detail)
        if self._scene_cache is not None and self._scene_cache[0] == key:
            return self._scene_cache[1], self._scene_cache[2], key
        triangles, lines = [], []

        def add_face(face, color):
            for i in range(1, len(face) - 1):
                vertices = (face[0], face[i], face[i + 1])
                triangles.append(Triangle(vertices, color, face_normal(*vertices)))

        if self._layers["surfaces"]:
            for surface in self._visible_surfaces():
                subsystem = str(surface.get("subsystem", ""))
                layer = {"pixel": "pixels", "solenoid": "solenoid"}.get(subsystem, "guides")
                color = QColor(_SURFACE_COLORS.get(subsystem, _AXIS))
                color.setAlphaF(self._opacity.get(layer, 0.12))
                for face in _surface_faces(surface):
                    add_face(face, color)
                edge = QColor(color)
                edge.setAlphaF(min(0.65, self._opacity.get(layer, 0.12) + 0.20))
                for polyline in _surface_lines(surface):
                    lines.extend((a, b, edge) for a, b in zip(polyline, polyline[1:], strict=False))
        for chamber in self._visible_chambers():
            layer = "irpc_re3" if chamber["station"] == "RE3/1" else "irpc_re4"
            selected = self._selected_chamber is not None and (
                chamber["id"] == self._selected_chamber["id"]
            )
            close = detail and (not self._selected_chamber or selected)
            for prism in self._display_prisms(chamber):
                color = QColor(
                    _SURFACE_COLORS.get(
                        prism["material"] if close else layer, _SURFACE_COLORS[layer]
                    )
                )
                color.setAlphaF(
                    self._opacity.get("irpc_internals", 1.0) if close else self._opacity[layer]
                )
                vertices = prism["vertices"]
                for a, b, c in prism_triangles:
                    add_face((vertices[a], vertices[b], vertices[c]), color)
                edge = QColor(LIGHT["selection"]) if selected else QColor(_SURFACE_COLORS[layer])
                edge.setAlphaF(1.0 if selected else 0.65)
                for a, b in _PRISM_EDGES:
                    lines.append((vertices[a], vertices[b], edge))
        if self._layers["tracks"]:
            for track in self._tracks:
                color = self._color_for_track(track)
                points = _raw_track_points(track)
                lines.extend((a, b, color) for a, b in zip(points, points[1:], strict=False))
        if self._layers["ideal_trajectories"]:
            for track in self._tracks:
                model = (track.get("trajectory") or {}).get("model", "")
                if str(model).startswith("ideal-solenoid"):
                    points = _trajectory_points(track)
                    # Alternating stored segments communicate model paths without inventing hits.
                    lines.extend(
                        (a, b, _MUTED)
                        for i, (a, b) in enumerate(zip(points, points[1:], strict=False))
                        if i % 2 == 0
                    )
        self._scene_cache = (key, triangles, lines)
        return triangles, lines, key

    def _visible_cms_styles(self) -> dict[str, tuple[QColor, float]]:
        """Return visible static mesh styles in outer-to-inner draw order."""
        styles: dict[str, tuple[QColor, float]] = {}
        for layer in _CMS_STYLE_ORDER:
            if not self._layers[layer]:
                continue
            color = QColor(_SURFACE_COLORS[_CMS_COLOR_KEYS.get(layer, layer)])
            opacity = self._opacity.get(layer, 0.2)
            if layer in _CMS_MESH_LAYERS:
                for mesh_id in _CMS_MESH_LAYERS[layer]:
                    if mesh_id in self._cms_geometry:
                        styles[mesh_id] = (color, opacity)
            elif layer in self._cms_envelopes:
                styles[layer] = (color, opacity)
        return styles

    def _cms_layer_bounds(self, layer: str) -> tuple[_Vec3, _Vec3] | None:
        if layer in _CMS_ENVELOPE_BOUNDS:
            return _CMS_ENVELOPE_BOUNDS[layer]
        geometry_ids = _CMS_MESH_LAYERS.get(layer, ())
        bounds = [
            self._cms_geometry[mesh_id].bounds
            for mesh_id in geometry_ids
            if mesh_id in self._cms_geometry
        ]
        if not bounds:
            return None
        low = tuple(min(bound[0][axis] for bound in bounds) for axis in range(3))
        high = tuple(max(bound[1][axis] for bound in bounds) for axis in range(3))
        return low, high

    def _draw_cms_bounds_2d(self, painter: QPainter, projection: str, transform) -> None:
        """Show subsystem envelopes in orthographic views; 3D draws full meshes."""
        painter.save()
        for layer in _CMS_STYLE_ORDER:
            if not self._layers[layer]:
                continue
            bounds = self._cms_layer_bounds(layer)
            if bounds is None:
                continue
            low, high = bounds
            color = QColor(_SURFACE_COLORS[_CMS_COLOR_KEYS.get(layer, layer)])
            color.setAlphaF(min(0.9, self._opacity.get(layer, 0.2) + 0.35))
            painter.setPen(QPen(color, 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if projection == "xy":
                radius = max(abs(low[0]), abs(high[0]), abs(low[1]), abs(high[1]))
                upper_left = self._map((-radius, radius), *transform)
                lower_right = self._map((radius, -radius), *transform)
                painter.drawEllipse(QRectF(upper_left, lower_right).normalized())
            else:
                upper_left = self._map((low[0], high[2]), *transform)
                lower_right = self._map((high[0], low[2]), *transform)
                painter.drawRect(QRectF(upper_left, lower_right).normalized())
        painter.restore()

    def _color_for_track(self, track: Mapping) -> QColor:
        selected_id = (self._selected_track or {}).get(
            "object_id", (self._selected_track or {}).get("id")
        )
        if self._selected_track is track or (
            selected_id is not None and track.get("object_id", track.get("id")) == selected_id
        ):
            return QColor(LIGHT["selection"])
        if self._color_mode == "pt":
            pt = _track_pt(track)
            return _pt_color(pt) if pt is not None else _MUTED
        return _track_color(track)

    def _draw_legend(
        self, painter: QPainter, plot: QRectF, *, show_static: bool = True
    ) -> None:
        painter.save()
        painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT))
        rows = []
        if self._layers["tracks"]:
            seen = set()
            for track in self._tracks:
                pdg = str(track.get("pdg_id", "?"))
                if pdg not in seen:
                    seen.add(pdg)
                    value = _track_pt(track)
                    suffix = (
                        f" · {value:.3g} GeV/c"
                        if self._color_mode == "pt" and value is not None
                        else ""
                    )
                    rows.append(
                        (
                            self._color_for_track(track),
                            f"{_PDG_NAMES.get(pdg, 'Particle')}  {pdg}{suffix}",
                        )
                    )
        for layer, label in (("irpc_re3", "RE3/1 · iRPC"), ("irpc_re4", "RE4/1 · iRPC")):
            if self._layers[layer]:
                rows.append((_SURFACE_COLORS[layer], label))
        for layer in _CMS_STYLE_ORDER if show_static else ():
            if self._layers[layer]:
                color_key = _CMS_COLOR_KEYS.get(layer, layer)
                rows.append((_SURFACE_COLORS[color_key], _CMS_LABELS[layer]))
        rows = rows[:8]
        if rows:
            rect = QRectF(plot.left() + 10, plot.top() + 10, 280, len(rows) * 20 + 12)
            panel = QColor(_PANEL_BG)
            panel.setAlpha(240)
            painter.fillRect(rect, panel)
            for i, (color, label) in enumerate(rows):
                y = rect.top() + 17 + i * 20
                painter.setPen(QPen(color, 3))
                painter.drawLine(QPointF(rect.left() + 10, y - 4), QPointF(rect.left() + 28, y - 4))
                painter.setPen(_TEXT)
                painter.drawText(QPointF(rect.left() + 36, y), label)
        painter.restore()

    def _draw_scale(self, painter: QPainter, plot: QRectF, scale: float, suffix="") -> None:
        length = _nice_step(90 / max(scale, 1e-9))
        pixels = length * scale
        origin = QPointF(plot.left() + 16, plot.bottom() - 18)
        painter.setPen(QPen(_TEXT, 1.5))
        painter.drawLine(origin, origin + QPointF(pixels, 0))
        for dx in (0, pixels):
            painter.drawLine(origin + QPointF(dx, -4), origin + QPointF(dx, 4))
        painter.setFont(QFont(FONT_MONO, FONT_SMALL_PT))
        painter.drawText(origin + QPointF(0, -8), f"{length:g} m  {suffix}")

    def _draw_chambers_2d(self, painter: QPainter, projection: str, transform) -> None:
        painter.save()
        for c in self._visible_chambers():
            layer = "irpc_re3" if c["station"] == "RE3/1" else "irpc_re4"
            color = QColor(_SURFACE_COLORS[layer])
            color.setAlphaF(min(1.0, self._opacity[layer] + 0.2))
            painter.setPen(QPen(color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for prism in self._display_prisms(c):
                vertices = prism["vertices"]
                for a, b in _PRISM_EDGES:
                    painter.drawLine(
                        self._map(self._project(vertices[a], projection), *transform),
                        self._map(self._project(vertices[b], projection), *transform),
                    )
        painter.restore()

    def _draw_chambers_fallback(self, painter: QPainter, frame: Mapping) -> None:
        if self._layers["surfaces"]:
            painter.setPen(QPen(_AXIS, 1))
            for surface in self._visible_surfaces():
                for line in _surface_lines(surface):
                    points = [self._camera_project(p, frame) for p in line]
                    for a, b in zip(points, points[1:], strict=False):
                        if a and b:
                            painter.drawLine(a[0], b[0])
        for c in self._visible_chambers():
            painter.setPen(
                QPen(_SURFACE_COLORS["irpc_re3" if c["station"] == "RE3/1" else "irpc_re4"], 1)
            )
            for a, b in _PRISM_EDGES:
                p, q = (
                    self._camera_project(c["vertices"][a], frame),
                    self._camera_project(c["vertices"][b], frame),
                )
                if p and q:
                    painter.drawLine(p[0], q[0])

    def _visible_world_points(self) -> list[_Vec3]:
        show_static = not self._gl_error
        key = (self._revision, show_static)
        if self._world_cache is not None and self._world_cache[0] == key:
            return self._world_cache[1]
        points: list[_Vec3] = []
        if self._layers["tracks"]:
            for track in self._tracks:
                points.extend(_raw_track_points(track))
        if self._layers["ideal_trajectories"]:
            for track in self._tracks:
                trajectory = track.get("trajectory")
                model = trajectory.get("model") if isinstance(trajectory, Mapping) else None
                if isinstance(model, str) and model.startswith("ideal-solenoid"):
                    points.extend(_trajectory_points(track))
        if self._layers["crossings"]:
            for track in self._tracks:
                trajectory = track.get("trajectory")
                crossings = trajectory.get("crossings") if isinstance(trajectory, Mapping) else None
                if isinstance(crossings, list):
                    points.extend(
                        position
                        for crossing in crossings
                        if isinstance(crossing, Mapping)
                        and (position := _vec3(crossing.get("position_m"))) is not None
                    )
        if self._layers["surfaces"]:
            for surface in self._visible_surfaces():
                for line in _surface_lines(surface):
                    points.extend(line)
        for layer in _CMS_STYLE_ORDER if show_static else ():
            if not self._layers[layer]:
                continue
            bounds = self._cms_layer_bounds(layer)
            if bounds is None:
                continue
            low, high = bounds
            points.extend(
                (x, y, z)
                for x in (low[0], high[0])
                for y in (low[1], high[1])
                for z in (low[2], high[2])
            )
        for chamber in self._visible_chambers():
            points.extend(chamber["vertices"])
        self._world_cache = (key, points)
        return points

    def _fit_world_points(self) -> list[_Vec3]:
        key = (self._revision, self._fit_mode, not self._gl_error)
        if self._fit_cache is not None and self._fit_cache[0] == key:
            return self._fit_cache[1]
        points = []
        if self._fit_mode == "selection":
            if self._selected_chamber:
                points = [
                    p
                    for prism in self._display_prisms(self._selected_chamber)
                    for p in prism["vertices"]
                ]
            elif self._selected_track:
                points = _raw_track_points(self._selected_track)
        elif self._fit_mode == "event":
            points = [p for t in self._tracks for p in _raw_track_points(t)]
        points = points or self._visible_world_points()
        if points:
            lows = [min(p[i] for p in points) for i in range(3)]
            highs = [max(p[i] for p in points) for i in range(3)]
            points = [
                (x, y, z)
                for x in (lows[0], highs[0])
                for y in (lows[1], highs[1])
                for z in (lows[2], highs[2])
            ]
        self._fit_cache = (key, points)
        return points

    def _camera_frame(self, points: list[_Vec3], plot: QRectF) -> dict[str, Any]:
        points = self._fit_world_points() or points
        lows = tuple(min(point[axis] for point in points) for axis in range(3))
        highs = tuple(max(point[axis] for point in points) for axis in range(3))
        target: _Vec3 = tuple((low + high) / 2.0 for low, high in zip(lows, highs, strict=True))
        radius = max(
            0.15,
            0.5 * math.sqrt(sum((high - low) ** 2 for low, high in zip(lows, highs, strict=True))),
        )
        yaw, pitch = self._camera_yaw, self._camera_pitch
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        right: _Vec3 = (-sy, cy, 0.0)
        up: _Vec3 = (-sp * cy, -sp * sy, cp)
        forward: _Vec3 = (cp * cy, cp * sy, sp)
        focal = min(plot.width(), plot.height()) / (2.0 * math.tan(math.radians(25.0)))
        safe_half_width = max(1.0, plot.width() * 0.43)
        safe_half_height = max(1.0, plot.height() * 0.43)
        required_distance = 0.0
        farthest_point = -math.inf
        for point in points:
            delta = tuple(point[index] - target[index] for index in range(3))
            camera_x = sum(delta[index] * right[index] for index in range(3))
            camera_y = sum(delta[index] * up[index] for index in range(3))
            camera_z = sum(delta[index] * forward[index] for index in range(3))
            farthest_point = max(farthest_point, camera_z)
            required_distance = max(
                required_distance,
                camera_z + focal * abs(camera_x) / safe_half_width,
                camera_z + focal * abs(camera_y) / safe_half_height,
            )
        distance = max(required_distance * 1.32, farthest_point + radius * 0.12, 0.5)
        if self._perspective:
            distance /= self._zoom
        else:
            focal *= self._zoom
        return {
            "target": target,
            "right": right,
            "up": up,
            "forward": forward,
            "distance": distance,
            "focal": focal,
            "center": plot.center(),
            "bounds": (lows, highs),
            "orthographic": not self._perspective,
        }

    @staticmethod
    def _camera_project(point: _Vec3, frame: Mapping[str, Any]) -> tuple[QPointF, float] | None:
        target = frame["target"]
        delta = tuple(point[index] - target[index] for index in range(3))
        right = sum(delta[index] * frame["right"][index] for index in range(3))
        up = sum(delta[index] * frame["up"][index] for index in range(3))
        toward_camera = sum(delta[index] * frame["forward"][index] for index in range(3))
        depth = frame["distance"] - toward_camera
        if depth <= 0.02:
            return None
        factor = frame["focal"] / (frame["distance"] if frame.get("orthographic") else depth)
        center = frame["center"]
        return QPointF(center.x() + right * factor, center.y() - up * factor), depth

    def _draw_3d_floor(self, painter: QPainter, plot: QRectF, frame: Mapping[str, Any]) -> None:
        lows, highs = frame["bounds"]
        span = max(highs[0] - lows[0], highs[1] - lows[1], 1.0)
        step = _nice_step(span / 7.0)
        x0, x1 = math.floor(lows[0] / step) * step, math.ceil(highs[0] / step) * step
        y0, y1 = math.floor(lows[1] / step) * step, math.ceil(highs[1] / step) * step
        painter.setPen(QPen(_GRID, 1.0))
        x = x0
        while x <= x1 + step * 0.5:
            first = self._camera_project((x, y0, 0.0), frame)
            second = self._camera_project((x, y1, 0.0), frame)
            if first is not None and second is not None:
                painter.drawLine(first[0], second[0])
            x += step
        y = y0
        while y <= y1 + step * 0.5:
            first = self._camera_project((x0, y, 0.0), frame)
            second = self._camera_project((x1, y, 0.0), frame)
            if first is not None and second is not None:
                painter.drawLine(first[0], second[0])
            y += step

    def _draw_3d_tracks(self, painter: QPainter, frame: Mapping[str, Any]) -> None:
        segments: list[tuple[float, QColor, QPointF, QPointF]] = []
        for track in self._tracks:
            points = _raw_track_points(track)
            color = self._color_for_track(track)
            for first, second in zip(points, points[1:], strict=False):
                p0, p1 = self._camera_project(first, frame), self._camera_project(second, frame)
                if p0 is None or p1 is None:
                    continue
                segments.append(((p0[1] + p1[1]) / 2.0, color, p0[0], p1[0]))
        for _depth, color, first, second in sorted(
            segments, key=lambda item: item[0], reverse=True
        ):
            painter.setPen(QPen(color, 2.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(first, second)

    def _draw_3d_ideal_trajectories(self, painter: QPainter, frame: Mapping[str, Any]) -> None:
        for track in self._tracks:
            trajectory = track.get("trajectory")
            model = trajectory.get("model") if isinstance(trajectory, Mapping) else None
            if not isinstance(model, str) or not model.startswith("ideal-solenoid"):
                continue
            projected = [self._camera_project(point, frame) for point in _trajectory_points(track)]
            if any(point is None for point in projected):
                continue
            painter.setPen(QPen(_MUTED, 1.0, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawPolyline(QPolygonF([point[0] for point in projected if point is not None]))

    def _draw_3d_crossings(self, painter: QPainter, frame: Mapping[str, Any]) -> None:
        projected_crossings = []
        clip = painter.clipBoundingRect()
        for track in self._tracks:
            trajectory = track.get("trajectory")
            crossings = trajectory.get("crossings") if isinstance(trajectory, Mapping) else None
            if not isinstance(crossings, list):
                continue
            for crossing in crossings:
                if not isinstance(crossing, Mapping):
                    continue
                position = _vec3(crossing.get("position_m"))
                projected = self._camera_project(position, frame) if position is not None else None
                if projected is not None and clip.contains(projected[0]):
                    projected_crossings.append(projected)

        painter.setPen(QPen(QColor(LIGHT["warning"]), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = 2.5
        spacing_squared = (2 * radius + 1) ** 2
        drawn = []
        for point, _depth in sorted(projected_crossings, key=lambda crossing: crossing[1]):
            x, y = point.x(), point.y()
            if any((x - a.x()) ** 2 + (y - a.y()) ** 2 < spacing_squared for a in drawn):
                continue
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, y - radius),
                        QPointF(x + radius, y),
                        QPointF(x, y + radius),
                        QPointF(x - radius, y),
                    ]
                )
            )
            drawn.append(point)

    def _draw_3d_axis_triad(
        self, painter: QPainter, plot: QRectF, frame: Mapping[str, Any]
    ) -> None:
        origin = QPointF(plot.right() - 54, plot.bottom() - 50)
        axes = (
            ((1.0, 0.0, 0.0), "X", _PDG_COLORS[-211]),
            ((0.0, 1.0, 0.0), "Y", _PDG_COLORS[13]),
            ((0.0, 0.0, 1.0), "Z", _PDG_COLORS[11]),
        )
        painter.save()
        painter.setFont(QFont(FONT_FAMILY, FONT_SMALL_PT, QFont.Weight.DemiBold))
        for direction, label, color in axes:
            vector = QPointF(
                direction[0] * frame["right"][0] + direction[1] * frame["right"][1],
                -(
                    direction[0] * frame["up"][0]
                    + direction[1] * frame["up"][1]
                    + direction[2] * frame["up"][2]
                ),
            )
            length = math.hypot(vector.x(), vector.y()) or 1.0
            vector = vector * (24.0 / length)
            painter.setPen(QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(origin, origin + vector)
            painter.setPen(color)
            painter.drawText(origin + vector + QPointF(3, -2), label)
        painter.restore()

    def _projected_bounds(self, projection: str) -> tuple[float, float, float, float]:
        points = [self._project(p, projection) for p in self._fit_world_points()]
        if not points:
            return (-1.0, 1.0, -1.0, 1.0)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        pad = max(max(xs) - min(xs), max(ys) - min(ys), 0.2) * 0.08
        return min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad

    def _visible_surfaces(self) -> list[dict[str, Any]]:
        visible = []
        for surface in self._surfaces:
            subsystem = str(surface.get("subsystem", ""))
            if subsystem == "pixel" and not self._layers["pixels"]:
                continue
            if subsystem == "solenoid" and not self._layers["solenoid"]:
                continue
            if subsystem not in {"pixel", "solenoid"} and not self._layers["guides"]:
                continue
            visible.append(surface)
        return visible

    @staticmethod
    def _base_scale(bounds: tuple[float, float, float, float], rect: QRectF) -> float:
        x0, x1, y0, y1 = bounds
        width, height = max(x1 - x0, 1e-12), max(y1 - y0, 1e-12)
        return max(1e-12, min(rect.width() / width, rect.height() / height))

    def _transform(
        self, bounds: tuple[float, float, float, float], rect: QRectF
    ) -> tuple[float, QPointF]:
        x0, x1, y0, y1 = bounds
        scale = self._base_scale(bounds, rect) * self._zoom
        center = rect.center()
        center_world = QPointF((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        origin = (
            QPointF(center.x() - center_world.x() * scale, center.y() + center_world.y() * scale)
            + self._pan
        )
        return scale, origin

    @staticmethod
    def _map(point: _Point2, scale: float, origin: QPointF) -> QPointF:
        return QPointF(origin.x() + point[0] * scale, origin.y() - point[1] * scale)

    @staticmethod
    def _project(point: _Vec3, projection: str) -> _Point2:
        x, y, z = point
        if projection == "xy":
            return (x, y)
        if projection == "xz":
            return (x, z)
        # Fixed isometric camera, chosen for a legible separation of the axes.
        return ((x - y) * math.sqrt(0.5), (x + y) / math.sqrt(6.0) + z * math.sqrt(2.0 / 3.0))

    def _hit_test(self, position: QPointF) -> dict[str, Any] | None:
        self._track_pick_depth = math.inf
        panel = self._panel_at(position)
        if panel is None or not (self._layers["tracks"] or self._layers["ideal_trajectories"]):
            return None
        projection, panel_rect, _label = panel
        plot = (
            panel_rect.adjusted(14, 34, -14, -38)
            if projection == "3d"
            else self._plot_rect(panel_rect)
        )
        if not plot.contains(position):
            return None
        frame = None
        transform = None
        if projection == "3d":
            world_points = self._visible_world_points()
            if not world_points:
                return None
            frame = self._camera_frame(world_points, plot)
        else:
            transform = self._transform(self._projected_bounds(projection), plot)
        nearest: tuple[float, dict[str, Any]] | None = None
        for track in self._tracks:
            if self._layers["tracks"]:
                points = _raw_track_points(track)
            else:
                trajectory = track.get("trajectory")
                model = trajectory.get("model") if isinstance(trajectory, Mapping) else None
                if not isinstance(model, str) or not model.startswith("ideal-solenoid"):
                    continue
                points = _trajectory_points(track)
            if len(points) < 2:
                continue
            if projection == "3d":
                projected = [self._camera_project(point, frame) for point in points]
                screen_points = [point[0] if point is not None else None for point in projected]
            else:
                screen_points = [
                    self._map(self._project(point, projection), *transform) for point in points
                ]
            if len(screen_points) < 2:
                continue
            candidates = [
                (_distance_to_segment(position, a, b), i)
                for i, (a, b) in enumerate(zip(screen_points, screen_points[1:], strict=False))
                if a is not None and b is not None
            ]
            distance, segment_index = min(candidates, default=(math.inf, 0))
            if distance <= 8.0 and (nearest is None or distance < nearest[0]):
                nearest = (distance, track)
                if frame is not None:
                    a, b = screen_points[segment_index : segment_index + 2]
                    dx, dy = b.x() - a.x(), b.y() - a.y()
                    u = max(
                        0.0,
                        min(
                            1.0,
                            ((position.x() - a.x()) * dx + (position.y() - a.y()) * dy)
                            / (dx * dx + dy * dy or 1),
                        ),
                    )
                    d0, d1 = projected[segment_index][1], projected[segment_index + 1][1]
                    self._track_pick_depth = (
                        (1 - u) * d0 + u * d1
                        if frame["orthographic"]
                        else 1 / ((1 - u) / d0 + u / d1)
                    )
        return nearest[1] if nearest else None

    def _hit_test_chamber(self, position: QPointF) -> dict | None:
        self._chamber_pick_depth = math.inf
        from .display_geometry import TRIANGLES as prism_triangles

        panel = self._panel_at(position)
        if panel is None:
            return None
        projection, rect, _ = panel
        plot = rect.adjusted(14, 34, -14, -38) if projection == "3d" else self._plot_rect(rect)
        if not plot.contains(position):
            return None
        frame = (
            self._camera_frame(self._visible_world_points(), plot) if projection == "3d" else None
        )
        transform = (
            self._transform(self._projected_bounds(projection), plot) if frame is None else None
        )
        hits = []
        if frame is not None:
            dx = (position.x() - frame["center"].x()) / frame["focal"]
            dy = -(position.y() - frame["center"].y()) / frame["focal"]
            eye = tuple(
                frame["target"][i] + frame["forward"][i] * frame["distance"] for i in range(3)
            )
            offset = tuple(frame["right"][i] * dx + frame["up"][i] * dy for i in range(3))
            origin = (
                tuple(eye[i] + offset[i] * frame["distance"] for i in range(3))
                if frame["orthographic"]
                else eye
            )
            direction = tuple(
                -frame["forward"][i] + (0 if frame["orthographic"] else offset[i]) for i in range(3)
            )
        for c in self._visible_chambers():
            for prism in self._display_prisms(c):
                vertices = prism["vertices"]
                if frame is not None:
                    for a, b, d in prism_triangles:
                        depth = _ray_triangle_distance(
                            origin, direction, vertices[a], vertices[b], vertices[d]
                        )
                        if depth is not None and depth > 0.02:
                            hits.append((depth, c))
                else:
                    screen = [self._map(self._project(p, projection), *transform) for p in vertices]
                    if QPolygonF(screen[:4]).containsPoint(position, Qt.FillRule.OddEvenFill):
                        hits.append((abs(c["z_m"]), c))
                    else:
                        distance = min(
                            _distance_to_segment(position, screen[a], screen[b])
                            for a, b in _PRISM_EDGES
                        )
                        if distance < 5:
                            hits.append((distance, c))
        if hits:
            self._chamber_pick_depth, chamber = min(hits, key=lambda h: h[0])
            return chamber
        return None


def _ray_triangle_distance(origin, direction, a, b, c) -> float | None:
    """Two-sided ray/triangle intersection, in camera-forward depth units."""

    def cross(u, v):
        return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

    def dot(u, v):
        return sum(x * y for x, y in zip(u, v, strict=True))

    edge1, edge2 = tuple(b[i] - a[i] for i in range(3)), tuple(c[i] - a[i] for i in range(3))
    h = cross(direction, edge2)
    determinant = dot(edge1, h)
    if abs(determinant) < 1e-12:
        return None
    delta = tuple(origin[i] - a[i] for i in range(3))
    u = dot(delta, h) / determinant
    q = cross(delta, edge1)
    v = dot(direction, q) / determinant
    if u < 0 or v < 0 or u + v > 1:
        return None
    t = dot(edge2, q) / determinant
    return t if t > 0 else None


def _vec3(value: Any) -> _Vec3 | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 3:
        return None
    try:
        result = (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError, OverflowError):
        return None
    return result if all(math.isfinite(component) for component in result) else None


def _raw_track_points(track: Mapping[str, Any]) -> list[_Vec3]:
    points = track.get("points")
    if not isinstance(points, list):
        return []
    return [point for value in points if (point := _vec3(value)) is not None]


def _trajectory_points(track: Mapping[str, Any]) -> list[_Vec3]:
    trajectory = track.get("trajectory")
    points = trajectory.get("points") if isinstance(trajectory, Mapping) else None
    if not isinstance(points, list):
        return []
    return [point for value in points if (point := _vec3(value)) is not None]


def _surface_lines(surface: Mapping[str, Any]) -> list[list[_Vec3]]:
    """Make view polylines from the dimensions explicitly supplied by a surface."""
    kind = surface.get("kind")
    lines: list[list[_Vec3]] = []
    if kind == "cylinder":
        try:
            radius = float(surface["radius_m"])
            half_length = float(surface["half_length_m"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return []
        if not all(math.isfinite(value) and value > 0 for value in (radius, half_length)):
            return []
        segments = 48
        for z in (-half_length, half_length):
            lines.append(
                [
                    (
                        radius * math.cos(2 * math.pi * i / segments),
                        radius * math.sin(2 * math.pi * i / segments),
                        z,
                    )
                    for i in range(segments + 1)
                ]
            )
        for angle in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
            x, y = radius * math.cos(angle), radius * math.sin(angle)
            lines.append([(x, y, -half_length), (x, y, half_length)])
    elif kind == "disk":
        try:
            inner_radius = float(surface["inner_radius_m"])
            outer_radius = float(surface["outer_radius_m"])
            z = float(surface["z_m"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return []
        if (
            not all(math.isfinite(value) for value in (inner_radius, outer_radius, z))
            or not 0 <= inner_radius < outer_radius
        ):
            return []
        segments = 48
        for radius in (inner_radius, outer_radius):
            lines.append(
                [
                    (
                        radius * math.cos(2 * math.pi * i / segments),
                        radius * math.sin(2 * math.pi * i / segments),
                        z,
                    )
                    for i in range(segments + 1)
                ]
            )
        for index in range(8):
            angle = 2 * math.pi * index / 8
            lines.append(
                [
                    (inner_radius * math.cos(angle), inner_radius * math.sin(angle), z),
                    (outer_radius * math.cos(angle), outer_radius * math.sin(angle), z),
                ]
            )
    return lines


def _surface_faces(surface: Mapping[str, Any]) -> list[list[_Vec3]]:
    """Return lightweight quads for translucent cylinder and disk shells."""
    kind = surface.get("kind")
    faces: list[list[_Vec3]] = []
    segments = 48
    if kind == "cylinder":
        try:
            radius = float(surface["radius_m"])
            half_length = float(surface["half_length_m"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return faces
        if not all(math.isfinite(value) and value > 0 for value in (radius, half_length)):
            return faces
        for index in range(segments):
            angle0 = 2 * math.pi * index / segments
            angle1 = 2 * math.pi * (index + 1) / segments
            lower0 = (radius * math.cos(angle0), radius * math.sin(angle0), -half_length)
            lower1 = (radius * math.cos(angle1), radius * math.sin(angle1), -half_length)
            upper0 = (lower0[0], lower0[1], half_length)
            upper1 = (lower1[0], lower1[1], half_length)
            faces.append([lower0, lower1, upper1, upper0])
    elif kind == "disk":
        try:
            inner = float(surface["inner_radius_m"])
            outer = float(surface["outer_radius_m"])
            z = float(surface["z_m"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return faces
        if not all(math.isfinite(value) for value in (inner, outer, z)) or not 0 <= inner < outer:
            return faces
        for index in range(segments):
            angle0 = 2 * math.pi * index / segments
            angle1 = 2 * math.pi * (index + 1) / segments
            faces.append(
                [
                    (inner * math.cos(angle0), inner * math.sin(angle0), z),
                    (outer * math.cos(angle0), outer * math.sin(angle0), z),
                    (outer * math.cos(angle1), outer * math.sin(angle1), z),
                    (inner * math.cos(angle1), inner * math.sin(angle1), z),
                ]
            )
    return faces


def _track_color(track: Mapping[str, Any]) -> QColor:
    pdg = track.get("pdg_id")
    try:
        pdg_value = int(pdg)
    except (TypeError, ValueError, OverflowError):
        pdg_value = None
    if pdg_value in _PDG_COLORS:
        return QColor(_PDG_COLORS[pdg_value])
    if pdg_value is not None:
        return QColor(_MUTED)
    charge = track.get("charge")
    try:
        charge_value = float(charge)
    except (TypeError, ValueError, OverflowError):
        return QColor(_MUTED)
    if not math.isfinite(charge_value) or charge_value == 0:
        return QColor(_MUTED)
    return QColor(_PDG_COLORS[13 if charge_value < 0 else -13])


def _track_pt(track: Mapping) -> float | None:
    detector, truth = track.get("detector") or {}, track.get("truth") or {}
    value = detector.get("pt", truth.get("pt_gev", track.get("pt_gev")))
    if value is None:
        momentum = truth.get("momentum") or {}
        try:
            value = math.hypot(float(momentum["px"]), float(momentum["py"]))
        except (KeyError, ValueError, TypeError):
            return None
    try:
        pt = float(value)
        return pt if math.isfinite(pt) and pt >= 0 else None
    except (TypeError, ValueError):
        return None


def _pt_color(pt: float) -> QColor:
    # Display scale only: 0–100 GeV/c, logarithmic to retain low-pT contrast.
    t = min(1.0, max(0.0, math.log1p(pt) / math.log(101)))
    a, b = QColor(_PDG_COLORS.get(11, _TEXT)), QColor(_PDG_COLORS.get(-13, _TEXT))
    return QColor.fromRgbF(
        a.redF() * (1 - t) + b.redF() * t,
        a.greenF() * (1 - t) + b.greenF() * t,
        a.blueF() * (1 - t) + b.blueF() * t,
    )


def _distance_to_segment(point: QPointF, start: QPointF, end: QPointF) -> float:
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-12:
        return math.hypot(point.x() - start.x(), point.y() - start.y())
    t = max(
        0.0,
        min(1.0, ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length_squared),
    )
    return math.hypot(point.x() - (start.x() + t * dx), point.y() - (start.y() + t * dy))


def _nice_step(raw: float) -> float:
    if not math.isfinite(raw) or raw <= 0:
        return 1.0
    exponent = math.floor(math.log10(raw))
    scale = 10.0**exponent
    fraction = raw / scale
    multiplier = (
        1.0 if fraction <= 1.0 else 2.0 if fraction <= 2.0 else 5.0 if fraction <= 5.0 else 10.0
    )
    return multiplier * scale


def _fmt(value: float) -> str:
    if abs(value) >= 100 or (0 < abs(value) < 0.01):
        return f"{value:.1e}"
    return f"{value:.3g}"
