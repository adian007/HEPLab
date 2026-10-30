"""Interactive checkpoint widget for guided labs in Jupyter."""

from __future__ import annotations

import html
import json
from typing import Any


class LabNotebook:
    """A compact ipywidgets controller for a :class:`heplab.labs.Lab` session."""

    def __init__(self, lab, events=None):
        try:
            import ipywidgets as widgets
        except ImportError as exc:
            raise RuntimeError(
                "Install notebook support with `pip install heplab[notebook]`."
            ) from exc
        self.widgets = widgets
        self.lab = lab
        self.events = list(events) if events is not None else lab._events
        self.result: dict | None = None
        self._hint_count = 0
        self.container = widgets.VBox()
        self._render()

    def _render(self) -> None:
        w = self.widgets
        step = self.lab.current
        title = w.HTML(
            value=(
                f"<h3 style='margin:0'>{html.escape(self.lab.title)}</h3>"
                f"<p style='color:#64748b;margin:4px 0 14px'>"
                f"{sum(item.passed for item in self.lab.results.values())} / "
                f"{len(self.lab.steps)} checkpoints</p>"
            )
        )
        if step is None:
            self.container.children = (
                title,
                w.HTML(
                    "<div style='padding:14px;border-left:4px solid #27835b'>"
                    "<strong>Lab complete.</strong> Your checkpoint feedback is saved "
                    "in this session.</div>"
                ),
            )
            return

        task = w.HTML(
            f"<p style='font-size:1.05em'><strong>{html.escape(step['title'])}</strong></p>"
            f"<p>{html.escape(step['task'])}</p>"
        )
        answer: Any
        if step["id"] == "load":
            answer = w.Button(
                description="Load deterministic practice sample", button_style="primary"
            )
        elif step["id"] == "select":
            answer = w.Textarea(
                value=json.dumps(
                    self.lab.context.get(
                        "config",
                        {
                            "selection": {
                                "muons": {"min_pt": 20, "max_rel_iso": 0.15},
                                "pairs": {"require_opposite_charge": True},
                            },
                            "binning": {"dimuon_mass": {"range": [40, 140], "bins": 100}},
                        },
                    ),
                    indent=2,
                ),
                description="Config",
                layout=w.Layout(width="100%", height="155px"),
            )
        elif step["id"] == "mass":
            event = next((e for e in (self.events or []) if len(e.get("Muon") or []) >= 2), None)
            if event:
                muons = event["Muon"][:2]
                facts = "<br>".join(
                    f"μ{index + 1}: pT={m['pt']:.2f} GeV, η={m['eta']:.3f}, "
                    f"φ={m['phi']:.3f}, q={m['charge']:+d}"
                    for index, m in enumerate(muons)
                )
                task.value += f"<p>{facts}</p>"
            answer = w.FloatText(description="Mass (GeV)", value=0.0)
        elif step["id"] == "histogram":
            answer = w.HTML(value="Run the selected analysis and check its peak.")
        elif step["id"] == "fit":
            task.value += (
                "<p>Fit the selected masses with <code>heplab.fit_peak(result)</code>, "
                "then enter mean, uncertainty.</p>"
            )
            answer = w.Text(description="Fit", placeholder="mass, uncertainty")
        else:
            answer = w.Dropdown(
                options=[
                    (f"{key.upper()} · {value}", key)
                    for key, value in step.get("choices", {}).items()
                ],
                description="Answer",
            )

        feedback = w.HTML()
        hint = w.HTML()
        check = w.Button(description="Check answer", button_style="success")
        hint_button = w.Button(description="Show a hint")

        def submit(_button) -> None:
            try:
                if step["id"] == "load":
                    if self.events is None:
                        from . import practice_events

                        self.events = practice_events()
                    value = self.events
                elif step["id"] == "select":
                    value = json.loads(answer.value)
                elif step["id"] == "histogram":
                    if self.events is None:
                        raise ValueError("Load the practice or your own event list first.")
                    from .. import run

                    self.result = self.result or run(
                        self.events, config=self.lab.context.get("config")
                    )
                    value = self.result
                elif step["id"] == "fit":
                    if len(answer.value.split(",")) != 2:
                        raise ValueError("Enter the fitted mass and uncertainty as `91.2, 0.2`.")
                    value = tuple(float(part.strip()) for part in answer.value.split(","))
                elif step["id"] == "mass":
                    value = answer.value
                else:
                    value = answer.value
                outcome = self.lab.check(step["id"], value)
            except (
                Exception
            ) as exc:  # Display optional dependency and input errors in the notebook.
                feedback.value = (
                    "<div style='color:#a34026'><strong>Could not check:</strong> "
                    f"{html.escape(str(exc))}</div>"
                )
                return
            feedback.value = outcome._repr_html_()
            if outcome.passed:
                next_button = self.widgets.Button(
                    description=(
                        "Finish lab" if self.lab.current is None else "Continue to next checkpoint"
                    ),
                    button_style="primary",
                )
                next_button.on_click(lambda _event: self._render())
                buttons.children = (next_button,)

        def show_hint(_button) -> None:
            hint.value = f"<blockquote>{html.escape(self.lab.hint(step['id']))}</blockquote>"

        check.on_click(submit)
        if step["id"] == "load":
            answer.on_click(submit)
        hint_button.on_click(show_hint)
        buttons = w.HBox((hint_button,)) if step["id"] == "load" else w.HBox((check, hint_button))
        self.container.children = (title, task, answer, buttons, feedback, hint)

    def _repr_mimebundle_(self, **_kwargs):
        return self.container._repr_mimebundle_()


def display(lab, events=None) -> LabNotebook:
    """Create an interactive widget for a guided lab."""
    return LabNotebook(lab, events=events)
