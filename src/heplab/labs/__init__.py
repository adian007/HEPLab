"""Guided physics labs with step-by-step automatic checks (education mode).

A lab is a sequence of steps described in a JSON file next to this module.
Each step has a task, progressive hints and a check that turns a student's
answer into specific feedback::

    import heplab
    lab = heplab.labs.start("z-boson")
    events = heplab.labs.practice_events()
    print(lab.check("load", events))

Progress is plain data (``lab.progress()``), so it can be saved with
``lab.save(path)``, resumed with ``heplab.labs.resume(path)`` and exported as
a worksheet with ``lab.export_html(path)``.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MUON_MASS = 0.1056583755
PRACTICE_SOURCE = "heplab-practice-z-mumu-v1"


@dataclass(frozen=True)
class Feedback:
    step: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return ("PASS: " if self.passed else "TRY AGAIN: ") + self.message

    def _repr_html_(self) -> str:
        import html

        colour = "#2e7d32" if self.passed else "#b23c17"
        return (
            f'<div style="border-left:4px solid {colour};padding:6px 10px">'
            f"<strong>{'Passed' if self.passed else 'Not yet'}</strong> · "
            f"{html.escape(self.message)}</div>"
        )


def available() -> list[dict]:
    """Every installed lab as ``{id, title, audience, duration_minutes, summary}``."""
    labs = []
    for path in sorted(HERE.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        labs.append(
            {key: spec[key] for key in ("id", "title", "audience", "duration_minutes", "summary")}
        )
    return labs


def _spec(lab_id: str) -> dict:
    path = HERE / f"{lab_id}.json"
    if not lab_id.replace("-", "").isalnum() or not path.is_file():
        names = ", ".join(lab["id"] for lab in available())
        raise ValueError(f"unknown lab {lab_id!r}; available: {names}")
    return json.loads(path.read_text(encoding="utf-8"))


def start(lab_id: str = "z-boson") -> Lab:
    return Lab(_spec(lab_id))


def resume(path: str | Path, *, events: Iterable[dict] | None = None) -> Lab:
    """Resume progress; pass the original events to restore event-dependent checks."""
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    lab = start(saved["lab"])
    lab.results = {step: Feedback(**value) for step, value in saved.get("results", {}).items()}
    lab.context = saved.get("context", {})
    saved_digest = saved.get("events_sha256")
    if events is not None:
        rows = list(events)
        from ..io.provenance import config_hash

        if saved_digest and config_hash(rows) != saved_digest:
            raise ValueError("events do not match the saved lab progress")
        lab._events = rows
        if not saved_digest:
            # Migrate older progress that predates event fingerprints.
            _clear_event_dependent_progress(lab)
            if saved.get("results", {}).get("load", {}).get("passed"):
                lab.check("load", rows)
    elif saved_digest or saved.get("results", {}).get("load", {}).get("passed"):
        # Do not report event-dependent work as complete when its input is gone.
        _clear_event_dependent_progress(lab)
    return lab


def _clear_event_dependent_progress(lab: Lab) -> None:
    for step in ("load", "mass", "histogram", "fit"):
        lab.results.pop(step, None)
    lab.context.pop("events", None)
    for key in ("peak_gev", "fit"):
        lab.context.pop(key, None)


class Lab:
    def __init__(self, spec: dict):
        self.spec = spec
        self.id: str = spec["id"]
        self.title: str = spec["title"]
        self.steps: list[dict] = spec["steps"]
        self.results: dict[str, Feedback] = {}
        # Values carried between steps (e.g. the events a student loaded).
        self.context: dict[str, Any] = {}
        self._events: list[dict] | None = None
        self._hints: dict[str, int] = {}

    def step(self, step_id: str) -> dict:
        for step in self.steps:
            if step["id"] == step_id:
                return step
        raise ValueError(f"lab {self.id!r} has no step {step_id!r}")

    @property
    def current(self) -> dict | None:
        """The first step not yet passed."""
        return next(
            (s for s in self.steps if not getattr(self.results.get(s["id"]), "passed", False)),
            None,
        )

    def hint(self, step_id: str | None = None) -> str:
        """Reveal the next hint for a step; repeated calls go deeper."""
        step = self.step(step_id) if step_id else self.current
        if step is None:
            return "All steps are complete."
        shown = self._hints.get(step["id"], 0)
        hints = step.get("hints", [])
        if not hints:
            return "No hints for this step."
        self._hints[step["id"]] = min(shown + 1, len(hints))
        return hints[min(shown, len(hints) - 1)]

    def check(self, step_id: str, answer: Any) -> Feedback:
        self.step(step_id)
        checker = CHECKS[self.id][step_id]
        try:
            feedback = checker(self, answer)
        except (TypeError, ValueError, KeyError) as exc:
            feedback = Feedback(step_id, False, f"Could not read that answer: {exc}")
        self.results[step_id] = feedback
        return feedback

    def progress(self) -> dict:
        progress = {
            "schema": "heplab-lab-progress-v1",
            "lab": self.id,
            "title": self.title,
            "completed": sum(1 for f in self.results.values() if f.passed),
            "steps": len(self.steps),
            "results": {step: asdict(feedback) for step, feedback in self.results.items()},
            "context": self.context,
        }
        if self._events is not None:
            from ..io.provenance import config_hash

            progress["events_sha256"] = config_hash(self._events)
        return progress

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_text(json.dumps(self.progress(), indent=2), encoding="utf-8")
        return target

    def export_html(self, path: str | Path, *, student: str = "") -> Path:
        """A self-contained worksheet: tasks, the student's outcomes and the reference value."""
        import html

        rows = []
        for index, step in enumerate(self.steps, 1):
            result = self.results.get(step["id"])
            state = "passed" if result and result.passed else ("attempted" if result else "open")
            rows.append(
                f"<tr><td>{index}</td><td><strong>{html.escape(step['title'])}</strong>"
                f"<br><span class=muted>{html.escape(step['task'])}</span></td>"
                f"<td class={state}>{state}</td>"
                f"<td>{html.escape(result.message) if result else ''}</td></tr>"
            )
        reference = self.spec.get("reference", {})
        page = WORKSHEET.format(
            title=html.escape(self.title),
            student=html.escape(student) or "—",
            when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            done=sum(1 for f in self.results.values() if f.passed),
            total=len(self.steps),
            rows="".join(rows),
            reference=html.escape(
                f"{reference.get('quantity', '')}: {reference.get('value_gev', '')} ± "
                f"{reference.get('uncertainty_gev', '')} GeV ({reference.get('source', '')})"
            ),
        )
        target = Path(path)
        target.write_text(page, encoding="utf-8")
        return target

    def display(self, events: Iterable[dict] | None = None):
        """Create the interactive Jupyter checkpoint view (requires ``heplab[notebook]``)."""
        from .notebook import display

        return display(self, events=events)

    def __repr__(self) -> str:
        done = sum(1 for f in self.results.values() if f.passed)
        step = self.current
        nxt = f"next: {step['id']} ({step['title']})" if step else "complete"
        return f"<Lab {self.id}: {done}/{len(self.steps)} steps, {nxt}>"

    def _repr_html_(self) -> str:
        import html

        items = []
        for step in self.steps:
            result = self.results.get(step["id"])
            mark = "✔" if result and result.passed else ("✘" if result else "○")
            items.append(
                f"<li>{mark} <strong>{html.escape(step['title'])}</strong> "
                f"<code>lab.check({step['id']!r}, …)</code><br>"
                f"<span style='opacity:.75'>{html.escape(step['task'])}</span></li>"
            )
        return (
            f"<div><h3 style='margin:0'>{html.escape(self.title)}</h3>"
            f"<p style='opacity:.75'>{html.escape(self.spec.get('summary', ''))}</p>"
            f"<ol style='list-style:none;padding-left:0'>{''.join(items)}</ol></div>"
        )


# --- Practice data -------------------------------------------------------------


def _decay(mass: float, rng: random.Random) -> list[dict]:
    """Two muons from a resonance of ``mass``, boosted to LHC-like kinematics."""
    p = math.sqrt(max(mass * mass / 4 - MUON_MASS * MUON_MASS, 0.0))
    cos_theta, phi = rng.uniform(-1, 1), rng.uniform(-math.pi, math.pi)
    sin_theta = math.sqrt(1 - cos_theta * cos_theta)
    rest = [
        (p * sin_theta * math.cos(phi), p * sin_theta * math.sin(phi), p * cos_theta),
        (-p * sin_theta * math.cos(phi), -p * sin_theta * math.sin(phi), -p * cos_theta),
    ]
    energy = mass / 2
    # Boost: small transverse recoil, longitudinal rapidity spread.
    qt, qphi, rapidity = rng.expovariate(1 / 6.0), rng.uniform(-math.pi, math.pi), rng.gauss(0, 1.3)
    mt = math.sqrt(mass * mass + qt * qt)
    total = (qt * math.cos(qphi), qt * math.sin(qphi), mt * math.sinh(rapidity))
    big_e = mt * math.cosh(rapidity)
    beta = [component / big_e for component in total]
    b2 = sum(b * b for b in beta)
    gamma = 1 / math.sqrt(1 - b2)
    muons = []
    for charge, (px, py, pz) in zip((1, -1), rest, strict=True):
        bp = beta[0] * px + beta[1] * py + beta[2] * pz
        factor = (gamma - 1) * bp / b2 + gamma * energy if b2 > 0 else 0.0
        lab = [component + factor * b for component, b in zip((px, py, pz), beta, strict=True)]
        pt = math.hypot(lab[0], lab[1])
        muons.append(
            {
                "pt": pt,
                "eta": math.asinh(lab[2] / pt) if pt > 0 else 0.0,
                "phi": math.atan2(lab[1], lab[0]),
                "mass": MUON_MASS,
                "charge": charge,
            }
        )
    return muons


def practice_events(n: int = 4000, *, seed: int = 2026) -> list[dict]:
    """Synthetic Z→μμ practice sample for offline teaching. Not CMS data.

    About 70 % resonant decays (relativistic Breit–Wigner at the PDG mass and
    width, with 1.5 % muon pT resolution), the rest a falling Drell–Yan-like
    continuum plus non-isolated and same-sign pairs that a good selection
    removes. Deterministic for a given ``seed``.
    """
    if not 1 <= n <= 1_000_000:
        raise ValueError("n must be between 1 and 1,000,000")
    rng = random.Random(seed)
    m_z, width = 91.1876, 2.4952
    events = []
    for index in range(n):
        roll = rng.random()
        if roll < 0.70:
            while True:  # Breit-Wigner via Cauchy sampling, kept to a physical window
                mass = m_z + width / 2 * math.tan(math.pi * (rng.random() - 0.5))
                if 40 < mass < 200:
                    break
            kind = "z"
        else:
            mass = 12 + rng.expovariate(1 / 25.0)
            kind = "continuum"
        muons = _decay(mass, rng)
        for muon in muons:
            muon["pt"] *= max(0.5, rng.gauss(1.0, 0.015))
            muon["iso"] = abs(rng.gauss(0, 0.03))
        if 0.70 <= roll < 0.82:  # muons inside jets: poorly isolated
            for muon in muons:
                muon["iso"] = rng.uniform(0.2, 1.5)
        elif 0.82 <= roll < 0.88:  # misidentified pair: same charge
            muons[1]["charge"] = muons[0]["charge"]
        if rng.random() < 0.15:  # a soft extra muon from the underlying event
            soft = _decay(rng.uniform(2, 8), rng)[0]
            soft.update(iso=rng.uniform(0.1, 0.8), charge=rng.choice((-1, 1)))
            muons.append(soft)
        events.append(
            {
                "EventInfo": {
                    "run": 1,
                    "luminosity_block": 1 + index // 1000,
                    "event": index + 1,
                    "weight": 1.0,
                    "is_data": False,
                    "kind": "simulation",
                    "generator": PRACTICE_SOURCE,
                    "truth_process": kind,
                },
                "Muon": muons,
            }
        )
    return events


# --- Checks ------------------------------------------------------------------


def _check_load(lab: Lab, events: Any) -> Feedback:
    if not isinstance(events, Iterable) or isinstance(events, str | bytes | dict):
        return Feedback("load", False, "Pass the list of events, not a single event or a path.")
    events = list(events)
    with_muons = [e for e in events if isinstance(e, dict) and len(e.get("Muon") or []) >= 2]
    if len(events) < 1000:
        return Feedback("load", False, f"Only {len(events)} events; load at least 1000.")
    if not with_muons:
        return Feedback("load", False, "None of these events has two muons.")
    lab._events = events
    lab.context["events"] = len(events)
    return Feedback(
        "load",
        True,
        f"Loaded {len(events)} events; {len(with_muons)} have at least two muons.",
        {"events": len(events), "with_two_muons": len(with_muons)},
    )


def _check_select(lab: Lab, config: Any) -> Feedback:
    if not isinstance(config, dict):
        return Feedback("select", False, "The selection must be an analysis configuration dict.")
    from ..analyses.dimuon.run import _settings

    pt, _eta, iso, _minimum, _window, opposite, *_ = _settings(config)
    problems = []
    if not opposite:
        problems.append("a neutral Z decays to one μ⁺ and one μ⁻: require opposite charge")
    if pt < 15:
        problems.append(f"min_pt {pt:g} GeV keeps many soft muons; Z muons are much harder")
    if iso > 0.3:
        problems.append(f"max_rel_iso {iso:g} keeps muons from jets; tighten isolation")
    if problems:
        return Feedback("select", False, "Almost: " + "; ".join(problems) + ".")
    lab.context["config"] = config
    return Feedback(
        "select", True, f"Good selection: pT ≥ {pt:g} GeV, isolation ≤ {iso:g}, opposite charge."
    )


def _check_mass(lab: Lab, value: Any) -> Feedback:
    from ..analyses.dimuon.run import invariant_mass

    if lab._events is None:
        return Feedback("mass", False, "Complete the 'load' step first so the event is known.")
    event = next(e for e in lab._events if len(e.get("Muon") or []) >= 2)
    expected = invariant_mass(*event["Muon"][:2])
    value = float(value)
    if not math.isfinite(value):
        return Feedback("mass", False, "The mass must be a finite number of GeV.")
    error = abs(value - expected) / expected
    if error <= 1e-3:
        return Feedback("mass", True, f"Correct: {expected:.3f} GeV.", {"expected": expected})
    if abs(value - expected) / expected <= 0.05:
        return Feedback(
            "mass", False, "Close: check pz = pT·sinh(η) and that E includes the muon mass."
        )
    return Feedback(
        "mass",
        False,
        f"{value:.3f} GeV is not right for event {event['EventInfo'].get('event')}. "
        "Rebuild both four-vectors before adding them.",
    )


def _peak(result: dict) -> tuple[float, int]:
    histogram = result["histogram"]
    edges, counts = histogram["edges"], histogram["counts"]
    # Ignore the low-mass continuum: the Z is the highest bin above 50 GeV.
    candidates = [i for i in range(len(counts)) if edges[i] >= 50]
    best = max(candidates, key=lambda i: counts[i])
    return (edges[best] + edges[best + 1]) / 2, histogram.get("entries", 0)


def _check_histogram(lab: Lab, result: Any) -> Feedback:
    if not isinstance(result, dict) or "histogram" not in result:
        return Feedback("histogram", False, "Pass the result of heplab.run(events, config=...).")
    centre, entries = _peak(result)
    if entries < 200:
        return Feedback("histogram", False, f"Only {entries} pairs selected; loosen the selection.")
    lab.context["peak_gev"] = centre
    if 86 <= centre <= 96:
        return Feedback(
            "histogram",
            True,
            f"Peak near {centre:.1f} GeV from {entries} pairs: that is the Z boson.",
            {"peak_gev": centre, "entries": entries},
        )
    return Feedback(
        "histogram",
        False,
        f"The tallest bin above 50 GeV is at {centre:.1f} GeV. Is your selection keeping the Z?",
    )


def _check_fit(lab: Lab, answer: Any) -> Feedback:
    if isinstance(answer, dict):
        if not answer.get("success", True):
            return Feedback("fit", False, "The fit did not converge; narrow the fit window.")
        mass, error = answer["values"]["mean"], answer["errors"]["mean"]
    else:
        mass, error = (float(x) for x in answer)
    reference = lab.spec["reference"]["value_gev"]
    if not (math.isfinite(mass) and math.isfinite(error) and error > 0):
        return Feedback("fit", False, "Report a finite mass and a positive uncertainty.")
    pull = (mass - reference) / error
    lab.context["fit"] = {"mass_gev": mass, "uncertainty_gev": error}
    if abs(mass - reference) <= 1.0 and error < 1.0:
        return Feedback(
            "fit",
            True,
            f"m = {mass:.2f} ± {error:.2f} GeV, {abs(pull):.1f}σ from the PDG value "
            f"{reference} GeV.",
            {"mass_gev": mass, "uncertainty_gev": error, "pull": pull},
        )
    if error >= 1.0:
        return Feedback("fit", False, f"±{error:.2f} GeV is too uncertain; use more events.")
    return Feedback(
        "fit", False, f"{mass:.2f} GeV is far from the peak; fit a window around 70–110 GeV."
    )


def _check_width(lab: Lab, answer: Any) -> Feedback:
    choice = str(answer).strip().lower()[:1]
    if choice == "b":
        return Feedback(
            "width",
            True,
            "Right: the measured width combines the natural width (2.5 GeV) with the muon "
            "momentum resolution of the detector.",
        )
    return Feedback("width", False, "Not quite. Think about how precisely each muon is measured.")


CHECKS: dict[str, dict[str, Callable[[Lab, Any], Feedback]]] = {
    "z-boson": {
        "load": _check_load,
        "select": _check_select,
        "mass": _check_mass,
        "histogram": _check_histogram,
        "fit": _check_fit,
        "width": _check_width,
    }
}

WORKSHEET = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>:root{{--bg:#fff;--ink:#1d1f23;--muted:#62666d;--line:#ddd}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181b;--ink:#e7e8ea;
--muted:#9aa0a8;--line:#33373c}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:24px 16px}}.muted{{color:var(--muted);font-size:.85rem}}
table{{border-collapse:collapse;width:100%}}
td{{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}}
.passed{{color:#2e7d32;font-weight:600}}.attempted{{color:#b23c17}}.open{{color:var(--muted)}}</style></head>
<body><main><h1>{title}</h1>
<p class="muted">Student: {student} · {when} · {done}/{total} steps complete</p>
<table>{rows}</table><p class="muted">Reference: {reference}</p></main></body></html>
"""
