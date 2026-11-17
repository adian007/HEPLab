"""OpenGL regression for the RPC chamber outline fade."""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("PySide6")
if sys.platform != "win32" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from heplab.native_ui.event_display import EventDisplayWidget  # noqa: E402
from heplab.native_ui.gl_scene import _RPC_THICKNESS_LIMIT_M, LINES  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


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
            _RPC_THICKNESS_LIMIT_M * frame["focal"] * widget.devicePixelRatioF() / frame["distance"]
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
