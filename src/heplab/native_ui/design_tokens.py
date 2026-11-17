"""Shared visual tokens for the light native scientific workbench."""

from __future__ import annotations

LIGHT = {
    "canvas": "#f4f6f8",
    "panel": "#ffffff",
    "border": "#cbd3dc",
    "text": "#24313d",
    "muted": "#627181",
    "grid": "#e5eaf0",
    "axis": "#718091",
    "axis_x": "#a44145",
    "axis_y": "#247a56",
    "axis_z": "#286da2",
    "selection": "#167b86",
    "accent": "#197b73",
    "accent_soft": "#e7f2f1",
    "warning": "#a86c16",
    "error": "#a33c32",
    "crossing": "#a05a00",
    "crossing_fill": "#fff0d2",
    "ideal": "#497aab",
    "unknown_track": "#65727d",
}

PDG_COLORS = {
    11: "#0072b2",
    -11: "#a64d83",
    13: "#00835f",
    -13: "#9a5d00",
    22: "#755500",
    211: "#5b5f97",
    -211: "#963f73",
}

SURFACE_COLORS = {
    "pixel": "#9a5265",
    "strips": "#5b7f9d",
    "ecal": "#d49a3a",
    "hcal": "#bd6944",
    "muon": "#6d8791",
    "tracker-envelope": "#658469",
    "solenoid": "#8d7845",
    "yoke": "#536372",
    "irpc_re3": "#3677a8",
    "irpc_re4": "#c26d34",
    "gas": "#45957c",
    "hpl": "#a56c91",
    "readout": "#c39d42",
}

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"
FONT_SIZE_PT = 9
FONT_SMALL_PT = 8
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16}
RADIUS_PX = 5

__all__ = [
    "FONT_FAMILY",
    "FONT_MONO",
    "FONT_SIZE_PT",
    "FONT_SMALL_PT",
    "LIGHT",
    "PDG_COLORS",
    "RADIUS_PX",
    "SPACING",
    "SURFACE_COLORS",
]
