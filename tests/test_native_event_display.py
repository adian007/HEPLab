"""Display isolation, camera, selection and actual depth-buffer regressions."""

from __future__ import annotations

import copy
import math
import os
import sys

import pytest

pytest.importorskip("PySide6")
if sys.platform != "win32" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QSurfaceFormat  # noqa: E402
from PySide6.QtOpenGLWidgets import QOpenGLWidget  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from heplab.native_ui.cms_geometry import load_cms_geometry  # noqa: E402
from heplab.native_ui.event_display import EventDisplayWidget  # noqa: E402
from heplab.native_ui.gl_scene import LINES, _RPC_THICKNESS_LIMIT_M, GLScene, Triangle  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_display_geometry_never_mutates_event_and_hidden_chambers_are_not_pickable(app):
    event = {
        "tracks": [{"id": 1, "pdg_id": 13, "points": [[0, 0, 0], [0.1, 0, 1]]}],
        "geometry": {"surfaces": []},
    }
    original = copy.deepcopy(event)
    widget = EventDisplayWidget()
    widget.resize(1000, 700)
    widget.set_event(event)
    widget.set_projection("3d")
    c = widget._chambers[0]
    widget._selected_chamber = c
    widget.fit_to("selection")
    plot = widget._panel_specs()[0][1].adjusted(14, 34, -14, -38)
    frame = widget._camera_frame(widget._visible_world_points(), plot)
    center = tuple(sum(p[i] for p in c["vertices"]) / 8 for i in range(3))
    projected = widget._camera_project(center, frame)[0]
    assert widget._hit_test_chamber(projected) is not None
    widget.set_layers({"irpc_re3": False, "irpc_re4": False})
    assert widget._hit_test_chamber(projected) is None
    widget.set_thickness_exaggeration(100)
    widget._scene_geometry()
    assert event == original
    assert event["geometry"]["surfaces"] == []
    widget.close()


def test_camera_event_fit_excludes_large_display_geometry(app):
    widget = EventDisplayWidget()
    widget.resize(1000, 700)
    widget.set_event({"tracks": [{"points": [[0, 0, 0], [0.1, 0, 0.2]]}]})
    plot = QRectF(0, 0, 800, 600)
    detector_distance = widget._camera_frame(widget._visible_world_points(), plot)["distance"]
    widget.fit_to("event")
    event_distance = widget._camera_frame(widget._visible_world_points(), plot)["distance"]
    assert detector_distance > event_distance * 10
    widget.set_perspective(False)
    initial = widget._camera_frame(widget._visible_world_points(), plot)
    widget._zoom = 20
    zoomed = widget._camera_frame(widget._visible_world_points(), plot)
    assert zoomed["distance"] == initial["distance"]
    assert zoomed["focal"] == pytest.approx(initial["focal"] * 20)
    widget.select_track({"id": 7})
    assert widget._color_for_track({"id": 7, "pdg_id": 13}) != widget._color_for_track(
        {"id": 8, "pdg_id": 13}
    )
    widget.close()


def test_isometric_camera_frames_both_endcaps_and_reset_restores_detector(app):
    widget = EventDisplayWidget()
    widget.resize(1000, 700)
    widget.set_event({})
    widget.set_projection("3d")
    widget.set_view_preset("isometric")
    plot = QRectF(0, 0, 800, 600)
    frame = widget._camera_frame(widget._visible_world_points(), plot)
    assert frame["bounds"][0][2] < -10
    assert frame["bounds"][1][2] > 10
    assert widget._camera_pitch == pytest.approx(math.radians(35))

    widget._selected_chamber = widget._chambers[0]
    widget._revision += 1
    widget.fit_to("selection")
    selected = widget._camera_frame(widget._visible_world_points(), plot)
    assert selected["bounds"][1][2] - selected["bounds"][0][2] < 0.2

    widget._reset_view()
    assert widget._fit_mode == "detector"
    assert widget._camera_pitch == pytest.approx(math.radians(35))
    widget.close()


def test_full_cms_meshes_and_reference_envelopes_are_visible_by_default(app):
    widget = EventDisplayWidget()
    widget.resize(1000, 700)
    widget.set_event({})
    widget.set_projection("3d")

    styles = widget._visible_cms_styles()
    assert set(styles) == {
        "pixel",
        "strips",
        "ecal",
        "hcal",
        "dt",
        "csc",
        "rpc",
        "solenoid",
        "yoke",
    }
    assert len(widget._cms_envelopes["solenoid"]) % 6 == 0
    assert len(widget._cms_envelopes["yoke"]) % 6 == 0
    assert set(load_cms_geometry()) == {"pixel", "strips", "ecal", "hcal", "dt", "csc", "rpc"}

    points = widget._visible_world_points()
    assert min(point[2] for point in points) < -12.0
    assert max(point[2] for point in points) > 12.0
    assert max(abs(point[0]) for point in points) > 7.0

    widget.set_layers({"muon": False})
    assert not {"dt", "csc", "rpc"}.intersection(widget._visible_cms_styles())
    widget.set_layers({"yoke": False})
    assert "yoke" not in widget._visible_cms_styles()
    widget.close()


@pytest.mark.parametrize("perspective", [True, False], ids=["perspective", "orthographic"])
def test_rpc_outline_fade_keeps_perimeter_and_reverses_with_zoom(app, monkeypatch, perspective):
    unavailable = pytest.fail if os.environ.get("HEPLAB_REQUIRE_OPENGL") == "1" else pytest.skip
    if app.platformName() == "offscreen":
        unavailable("QOpenGLWidget is unsupported by Qt's offscreen platform")

    widget = EventDisplayWidget()
    try:
        widget.resize(800, 600)
        widget.set_projection("3d")
        widget.set_view_preset("front")
        widget.set_perspective(perspective)
        widget.show()
        app.processEvents()
        if not widget.isValid():
            unavailable("No usable OpenGL context on this machine")
        scene = widget._gl_scene
        assert scene is not None, widget._gl_error

        start, full_count = scene._static_outline_ranges["rpc"]
        perimeter_count = scene._rpc_perimeter_count
        assert 0 < perimeter_count < full_count
        draws = []
        draw_static = scene._draw_static

        def record_draw(index, first, count, mode, opacity):
            if mode == LINES and start <= first < start + full_count:
                draws.append((first, count, opacity))
            draw_static(index, first, count, mode, opacity)

        monkeypatch.setattr(scene, "_draw_static", record_draw)
        plot = widget._panel_specs()[0][1].adjusted(14, 34, -14, -38)
        frame = widget._camera_frame(widget._visible_world_points(), plot)
        thickness_at_unit_zoom = (
            _RPC_THICKNESS_LIMIT_M * frame["focal"] * widget.devicePixelRatioF()
            / frame["distance"]
        )
        opacity = min(0.20, 3 * widget._visible_cms_styles()["rpc"][1])
        assert opacity > 0
        perimeter_draw = (start, perimeter_count, opacity)
        # Include both sides of the transition and sample its smoothstep at quartiles.
        samples = (
            (0.1, 0.0),
            (0.249, 0.0),
            (0.2515, 0.000298),
            (0.2875, 0.15625),
            (0.325, 0.5),
            (0.3625, 0.84375),
            (0.3985, 0.999702),
            (0.401, 1.0),
        )
        for sweep in (samples, reversed(samples)):
            for thickness, fraction in sweep:
                widget._zoom = thickness / thickness_at_unit_zoom
                draws.clear()
                image = widget.grabFramebuffer()
                assert widget._gl_scene is scene, widget._gl_error
                assert not image.isNull()
                if fraction == 0:
                    assert draws == [perimeter_draw]
                elif fraction == 1:
                    assert draws == [(start, full_count, opacity)]
                else:
                    assert len(draws) == 2
                    assert draws[0] == perimeter_draw
                    extra_start, extra_count, extra_opacity = draws[1]
                    assert extra_start == start + perimeter_count
                    assert extra_count == full_count - perimeter_count
                    assert extra_opacity == pytest.approx(opacity * fraction)
    finally:
        widget.close()


def test_gpu_depth_buffer_occludes_back_geometry(app):
    if app.platformName() == "offscreen":
        pytest.skip("QOpenGLWidget is unsupported by Qt's offscreen platform")

    class DepthCheck(QOpenGLWidget):
        def __init__(self):
            super().__init__()
            fmt = QSurfaceFormat()
            fmt.setVersion(2, 1)
            fmt.setDepthBufferSize(24)
            self.setFormat(fmt)
            self.error = None

        def initializeGL(self):  # noqa: N802
            try:
                self.scene = GLScene(self.context())
            except Exception as exc:
                self.error = exc

        def paintGL(self):  # noqa: N802
            if self.error:
                return
            frame = dict(target=(0, 0, 0), forward=(0, 0, 1), up=(0, 1, 0), distance=4, focal=200)
            front = Triangle(((-2, -2, 1), (2, -2, 1), (0, 2, 1)), QColor("red"), (0, 0, 1))
            back = Triangle(((-2, -2, 0), (2, -2, 0), (0, 2, 0)), QColor("blue"), (0, 0, 1))
            # Submit the far triangle last: correct visibility must come from depth testing.
            self.scene.render(
                self, QRectF(self.rect()), frame, [front, back], [], 1, QColor("white")
            )

    widget = DepthCheck()
    widget.resize(240, 180)
    widget.show()
    app.processEvents()
    if widget.context() is None or not widget.isValid():
        widget.close()
        pytest.skip("No usable OpenGL context on this machine")
    assert widget.error is None
    image = widget.grabFramebuffer()
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    assert color.red() > color.blue() + 100
    widget.makeCurrent()
    widget.scene.destroy()
    widget.doneCurrent()
    widget.close()
