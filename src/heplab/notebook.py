"""Jupyter display for HEPLab results: event display, histograms and live filling.

Uses ipywidgets when installed, with plain HTML as a fallback::

    import heplab
    heplab.notebook.show(result)            # interactive histogram, cutflow, provenance

    live = heplab.notebook.LiveHistogram(60, 120, bins=60)
    live.display()
    for event in events:
        live.fill_event(event)              # redraws in place, throttled
"""

from __future__ import annotations

import html
import math
import time
from collections.abc import Iterable
from typing import Any

from .export.web_page import render


class View:
    """Inline, sandboxed rendering of the self-contained export page."""

    def __init__(self, result: dict, *, height: int = 720, title: str | None = None):
        self.result = result
        self.height = height
        self.title = title

    def _repr_html_(self) -> str:
        page = render(self.result, title=self.title)
        # srcdoc keeps the page's script and styles isolated from the notebook.
        return (
            f'<iframe srcdoc="{html.escape(page, quote=True)}" '
            f'style="width:100%;height:{int(self.height)}px;border:0" '
            'sandbox="allow-scripts"></iframe>'
        )

    def save(self, path) -> Any:
        from .export.web_page import export_html

        return export_html(self.result, path, title=self.title)


def show(result: dict | str, *, height: int = 720, title: str | None = None) -> Any:
    """Display a run result, workbench event or artifact path inline.

    Returns a real ``ipywidgets.HTML`` widget when ``heplab[notebook]`` is
    installed; otherwise returns a rich HTML display object.
    """
    from . import load

    view = View(result if isinstance(result, dict) else load(result), height=height, title=title)
    try:
        import ipywidgets as widgets
    except ImportError:
        return view
    return widgets.HTML(value=view._repr_html_(), layout=widgets.Layout(height=f"{height}px"))


class LiveHistogram:
    """A histogram that redraws in the notebook while it is being filled."""

    def __init__(
        self,
        low: float = 60.0,
        high: float = 120.0,
        *,
        bins: int = 60,
        label: str = "dimuon mass",
        units: str = "GeV",
        interval_s: float = 0.25,
    ):
        if not (math.isfinite(low) and math.isfinite(high) and low < high) or bins < 1:
            raise ValueError("histogram needs finite low < high and at least one bin")
        self.low, self.high, self.bins = float(low), float(high), int(bins)
        self.label, self.units = label, units
        self.counts = [0] * self.bins
        self.underflow = self.overflow = 0
        self.interval_s = interval_s
        self._handle: Any = None
        self._widget: Any = None
        self._drawn = 0.0

    @property
    def entries(self) -> int:
        return sum(self.counts)

    @property
    def edges(self) -> list[float]:
        step = (self.high - self.low) / self.bins
        return [self.low + i * step for i in range(self.bins + 1)]

    def fill(self, values: float | Iterable[float]) -> LiveHistogram:
        for value in [values] if isinstance(values, int | float) else values:
            if not math.isfinite(value):
                continue
            if value < self.low:
                self.underflow += 1
            elif value >= self.high:
                self.overflow += 1
            else:
                self.counts[int((value - self.low) / (self.high - self.low) * self.bins)] += 1
        self._refresh()
        return self

    def fill_event(self, event: dict, config: dict | None = None) -> LiveHistogram:
        """Run the dimuon selection on one event and fill its candidate masses."""
        from . import run

        result = run([event], config=config)
        return self.fill(result.get("masses", []))

    def fill_events(self, events: Iterable[dict], config: dict | None = None) -> LiveHistogram:
        """Analyze a batch once, then fill all selected masses efficiently."""
        from . import run

        result = run(events, config=config)
        return self.fill(result.get("masses", []))

    def display(self) -> LiveHistogram:
        try:
            from IPython.display import display
        except ImportError:  # outside IPython: nothing to draw into
            return self
        try:
            import ipywidgets as widgets

            self._widget = widgets.HTML(value=self._svg())
            display(self._widget)
        except ImportError:
            from IPython.display import HTML

            self._handle = display(HTML(self._svg()), display_id=True)
        self._drawn = time.monotonic()
        return self

    def _refresh(self, force: bool = False) -> None:
        if self._handle is None:
            return
        now = time.monotonic()
        if force or now - self._drawn >= self.interval_s:
            if self._widget is not None:
                self._widget.value = self._svg()
            elif self._handle is not None:
                from IPython.display import HTML

                self._handle.update(HTML(self._svg()))
            self._drawn = now

    def done(self) -> LiveHistogram:
        """Draw the final state regardless of the redraw throttle."""
        self._refresh(force=True)
        return self

    def _svg(self, width: int = 640, height: int = 280) -> str:
        left, right, top, bottom = 48, 12, 12, 36
        plot_w, plot_h = width - left - right, height - top - bottom
        peak = max(max(self.counts), 1) * 1.1
        bar = plot_w / self.bins
        rects = "".join(
            f'<rect x="{left + i * bar:.1f}" y="{top + plot_h * (1 - c / peak):.1f}" '
            f'width="{max(bar - 1, 1):.1f}" height="{plot_h * c / peak:.1f}"/>'
            for i, c in enumerate(self.counts)
            if c
        )
        ticks = "".join(
            f'<text x="{left + plot_w * k / 5:.1f}" y="{height - bottom + 16}" '
            f'text-anchor="middle">{self.low + (self.high - self.low) * k / 5:g}</text>'
            for k in range(6)
        )
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px;'
            'font:11px system-ui;color:inherit" role="img" '
            f'aria-label="{html.escape(self.label)} histogram">'
            f'<g fill="#2f6fb0" fill-opacity=".85">{rects}</g>'
            f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" '
            'stroke="currentColor" stroke-opacity=".4"/>'
            f'<g fill="currentColor" fill-opacity=".7">{ticks}'
            f'<text x="{left + plot_w / 2}" y="{height - 4}" text-anchor="middle">'
            f"{html.escape(self.label)} [{html.escape(self.units)}]</text>"
            f'<text x="{left}" y="{top + 10}">{self.entries} entries · '
            f"{self.underflow} under · {self.overflow} over</text></g></svg>"
        )

    def _repr_html_(self) -> str:
        return self._svg()

    def to_result(self) -> dict:
        """The histogram as a result mapping, ready for :func:`show` or export."""
        return {
            "analysis": "live-histogram",
            "histogram": {
                "observable": self.label,
                "units": self.units,
                "bins": self.bins,
                "range": [self.low, self.high],
                "edges": self.edges,
                "counts": list(self.counts),
                "sumw2": list(self.counts),
                "entries": self.entries,
            },
            "cutflow": {"filled": self.entries + self.underflow + self.overflow},
        }
