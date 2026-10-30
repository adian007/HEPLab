"""Public API additions, HTML export and gallery, notebook display, and guided labs."""

import json
import math
import re
import threading
from importlib.util import find_spec

import pytest

import heplab
from heplab import labs
from heplab.analyses.dimuon.run import invariant_mass
from heplab.export.web_page import build_gallery, read_metadata, render

CONFIG = {
    "selection": {
        "muons": {"min_pt": 20, "max_rel_iso": 0.15},
        "pairs": {"require_opposite_charge": True},
    },
    "binning": {"dimuon_mass": {"range": [40, 140], "bins": 100}},
}


@pytest.fixture(scope="module")
def events():
    return labs.practice_events(3000, seed=7)


@pytest.fixture(scope="module")
def result(events):
    return heplab.run(events, config=CONFIG)


def test_practice_sample_is_deterministic_labelled_and_physical(events):
    assert labs.practice_events(50, seed=7) == events[:50]
    assert labs.practice_events(50, seed=8) != events[:50]
    assert all(e["EventInfo"]["generator"] == labs.PRACTICE_SOURCE for e in events)
    assert all(e["EventInfo"]["is_data"] is False for e in events)
    z = [e for e in events if e["EventInfo"]["truth_process"] == "z"]
    masses = sorted(invariant_mass(*e["Muon"][:2]) for e in z)
    median = masses[len(masses) // 2]
    assert 90 < median < 92.5  # resonance survives boost and smearing
    assert all(
        m["pt"] > 0 and m["mass"] == pytest.approx(0.10566, 1e-4) for e in z for m in e["Muon"]
    )


def test_run_provenance_is_stable_and_records_streamed_inputs(events):
    first = heplab.run(iter(events[:20]), config=CONFIG)
    again = heplab.run(iter(events[:20]), config=CONFIG)
    changed = heplab.run(iter(events[1:21]), config=CONFIG)
    assert first["provenance"]["event_count"] == 20
    assert first["provenance"]["input_events_sha256"] == again["provenance"]["input_events_sha256"]
    assert first["result_sha256"] == again["result_sha256"]
    assert first["result_sha256"] != changed["result_sha256"]
    assert first["provenance"]["api_version"] == heplab.API_VERSION == "1"


def test_public_run_result_digest_loads(tmp_path, events):
    result = heplab.run(events[:5], config=CONFIG)
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert heplab.load(path)["result_sha256"] == result["result_sha256"]


def test_full_z_lab_passes_with_correct_answers_and_explains_mistakes(events, result, tmp_path):
    lab = labs.start("z-boson")
    assert lab.current["id"] == "load"
    assert not lab.check("load", events[:10]).passed
    assert lab.check("load", events).passed
    loose = lab.check("select", {"selection": {"pairs": {"require_opposite_charge": False}}})
    assert not loose.passed and "opposite charge" in loose.message
    assert lab.check("select", CONFIG).passed
    first = next(e for e in events if len(e["Muon"]) >= 2)
    assert not lab.check("mass", 12.0).passed
    assert lab.check("mass", invariant_mass(*first["Muon"][:2])).passed
    histogram = lab.check("histogram", result)
    assert histogram.passed and 86 <= histogram.details["peak_gev"] <= 96
    pytest.importorskip("iminuit")
    fit = heplab.fit_peak(result)
    assert fit["success"]
    graded = lab.check("fit", fit)
    assert graded.passed and abs(graded.details["mass_gev"] - 91.1876) < 1.0
    assert not lab.check("fit", (80.0, 0.1)).passed
    assert lab.check("fit", fit).passed
    assert not lab.check("width", "a").passed and lab.check("width", "B").passed
    assert lab.current is None and "complete" in repr(lab)

    saved = lab.save(tmp_path / "progress.json")
    resumed = labs.resume(saved, events=events)
    assert resumed.progress()["completed"] == 6
    assert resumed.check("mass", invariant_mass(*first["Muon"][:2])).passed
    reopened = labs.resume(saved)
    assert reopened.progress()["completed"] == 2
    assert not reopened.check("mass", 91.2).passed
    with pytest.raises(ValueError, match="do not match"):
        labs.resume(saved, events=events[:-1])
    page = lab.export_html(tmp_path / "worksheet.html", student="<b>Ada</b>")
    text = page.read_text(encoding="utf-8")
    assert "&lt;b&gt;Ada&lt;/b&gt;" in text and "6/6 steps" in text


def test_hints_are_progressive_and_bad_answers_never_raise():
    lab = labs.start("z-boson")
    first, second = lab.hint("select"), lab.hint("select")
    assert first != second
    for _ in range(10):
        last = lab.hint("select")
    assert last == lab.step("select")["hints"][-1]
    assert not lab.check("mass", "not a number").passed  # mass needs a prior load too
    assert not lab.check("histogram", {"histogram": {}}).passed
    with pytest.raises(ValueError, match="unknown lab"):
        labs.start("../secret")
    assert [lab["id"] for lab in labs.available()] == ["z-boson"]


def test_read_applies_declared_kind_and_bounds(tmp_path, events):
    path = tmp_path / "events.json"
    unflagged = [{"EventInfo": {"event": 1}, "Muon": []}, {"EventInfo": {"event": 2}, "Muon": []}]
    path.write_text(json.dumps({"events": unflagged}))
    assert [e["EventInfo"]["is_data"] for e in heplab.read(path)] == [True, True]
    assert [e["EventInfo"]["is_data"] for e in heplab.read(path, simulation=True)] == [False] * 2
    assert len(heplab.read(path, max_events=1)) == 1
    path.write_text(json.dumps(events[:3]))
    assert heplab.read(path)[0]["EventInfo"]["is_data"] is False  # own flag wins
    with pytest.raises(ValueError):
        heplab.read(tmp_path / "events.csv")


def embedded(page: str, element: str) -> dict:
    match = re.search(rf'<script type="application/json" id="{element}">(.*?)</script>', page, re.S)
    return json.loads(match.group(1))


def test_export_page_is_offline_safe_and_round_trips_the_result(result, tmp_path):
    hostile = {**result, "analysis": "</script><script>alert(1)</script>", "nan": math.nan}
    page = render(hostile)
    assert "<script>alert(1)" not in page
    assert not re.search(r'(src|href)="https?:', page)  # nothing loaded from the network
    data = embedded(page, "heplab-data")
    assert data["analysis"] == hostile["analysis"] and data["nan"] is None
    assert data["histogram"]["counts"] == result["histogram"]["counts"]
    assert "masses" not in data  # raw arrays are dropped by default
    assert "masses" in embedded(render(result, include_raw=True), "heplab-data")
    assert 'href="#main"' in page and "setAttribute('role','img')" in page
    assert "Accessible histogram data" in page and "Zoom in" in page

    out = heplab.export_html(result, tmp_path / "z.html", title="Z <peak>")
    meta = read_metadata(out)
    assert meta["kind"] == "analysis" and meta["title"] == "Z <peak>"
    assert "<title>Z &lt;peak&gt;</title>" in out.read_text(encoding="utf-8")


def test_workbench_event_exports_and_gallery_indexes_pages(tmp_path, result):
    from heplab.server.workbench import RunConfig, bench

    event = bench(RunConfig(seed=4), threading.Event())
    heplab.export_html(event, tmp_path / "event.html")
    heplab.export_html(result, tmp_path / "peak.html")
    (tmp_path / "notes.html").write_text("<p>not an export</p>")
    index = build_gallery(tmp_path).read_text(encoding="utf-8")
    assert 'href="event.html"' in index and 'href="peak.html"' in index
    assert "notes.html" not in index and "2 examples" in index
    with pytest.raises(ValueError):
        render({"something": "else"})


def test_export_manifest_distinguishes_run_and_event_scope_and_privacy(tmp_path):
    from heplab.server.workbench import RunConfig, bench, lifetime_experiment

    run = bench(RunConfig(seed=5), threading.Event())
    run["artifact"] = {
        "schema": "heplab-run-artifact-v1",
        "scope": "full_run",
        "run_id": "run-5",
        "result_sha256": "a" * 64,
        "parent_run_sha256": None,
    }
    event = {
        **run,
        "artifact": {
            **run["artifact"],
            "schema": "heplab-event-view-v1",
            "scope": "selected_event_view",
            "event_index": 3,
            "parent_run_sha256": "a" * 64,
            "result_sha256": "b" * 64,
        },
        "output_directory": r"C:\\private\\local-run",
        "raw_events": [{"secret": "excluded by default"}],
    }
    default_page = render(event)
    default_meta = embedded(default_page, "heplab-meta")["manifest"]
    default_data = embedded(default_page, "heplab-data")
    assert default_meta["scope"] == "selected_event_view"
    assert default_meta["event_index"] == 3
    assert default_meta["parent_run_sha256"] == "a" * 64
    assert default_meta["privacy"]["contains_local_paths"] is False
    assert default_meta["privacy"]["raw_events_included"] is False
    assert "raw_events" not in default_data and "output_directory" not in default_data

    explicit_page = render(event, include_raw=True)
    explicit_meta = embedded(explicit_page, "heplab-meta")["manifest"]
    assert explicit_meta["privacy"]["contains_local_paths"] is True
    assert explicit_meta["privacy"]["raw_events_included"] is True
    assert "raw_events" in embedded(explicit_page, "heplab-data")

    lifetime = lifetime_experiment(
        {"momentum_gev_c": 1.0, "path_length_m": 20.0, "seed": 7, "sample_size": 100}
    )
    life_meta = embedded(render(lifetime), "heplab-meta")
    assert life_meta["kind"] == "lifetime"
    assert life_meta["manifest"]["scope"] == "full_run"
    assert life_meta["manifest"]["result_sha256"] == lifetime["result_sha256"]


def test_published_artifact_exports_after_digest_check(tmp_path, events):
    from heplab.cli import main

    source = tmp_path / "events.json"
    source.write_text(json.dumps({"events": events[:500]}))
    config = tmp_path / "config.json"
    config.write_text(json.dumps(CONFIG))
    artifact = tmp_path / "z.json"
    assert (
        main(
            [
                "run",
                "dimuon",
                "--simulation",
                "--input",
                str(source),
                "--config",
                str(config),
                "--output",
                str(artifact),
            ]
        )
        == 0
    )
    assert main(["export-html", str(artifact)]) == 0
    assert read_metadata(artifact.with_suffix(".html"))["kind"] == "analysis"
    assert main(["export-html", str(artifact), "--include-raw"]) == 0
    assert "masses" in embedded(artifact.with_suffix(".html").read_text(), "heplab-data")
    tampered = json.loads(artifact.read_text())
    tampered["histogram"]["counts"][0] += 1
    artifact.write_text(json.dumps(tampered))
    assert main(["export-html", str(artifact)]) == 2  # digest mismatch is refused


def test_learn_cli_grades_an_artifact(tmp_path, capsys):
    pytest.importorskip("iminuit")
    from heplab.cli import main

    events = tmp_path / "practice.json"
    assert main(["learn", "practice-data", "--output", str(events), "--events", "3000"]) == 0
    config = tmp_path / "config.json"
    config.write_text(json.dumps(CONFIG))
    artifact = tmp_path / "z.json"
    assert (
        main(
            [
                "run",
                "dimuon",
                "--simulation",
                "--input",
                str(events),
                "--config",
                str(config),
                "--output",
                str(artifact),
            ]
        )
        == 0
    )
    assert main(["learn", "check", "--artifact", str(artifact)]) == 0
    assert main(["learn", "list"]) == 0
    assert "z-boson" in capsys.readouterr().out


def test_notebook_view_and_live_histogram(result, events):
    view = heplab.notebook.show(result, height=500)
    if find_spec("ipywidgets"):
        assert view.value.startswith('<iframe srcdoc="') and 'sandbox="allow-scripts"' in view.value
        assert view.layout.height == "500px"
    else:
        assert view.__class__.__name__ == "View"
        assert view._repr_html_().startswith("<iframe srcdoc=")
    live = heplab.notebook.LiveHistogram(60, 120, bins=30)
    live.fill([59.0, 60.0, 91.2, 119.99, 120.0, math.nan])
    assert (live.underflow, live.entries, live.overflow) == (1, 3, 1)
    live.fill_events(events[:200], CONFIG)
    assert live.entries > 50
    assert "<svg" in live._repr_html_()
    page = render(live.to_result())
    assert embedded(page, "heplab-meta")["kind"] == "analysis"
    with pytest.raises(ValueError):
        heplab.notebook.LiveHistogram(5, 1)


def test_guided_lab_notebook_widget_moves_through_checkpoints(events):
    pytest.importorskip("ipywidgets")
    lab = labs.start("z-boson")
    view = lab.display(events=events)
    load_button = view.container.children[2]
    load_button.click()
    assert lab.results["load"].passed
    view.container.children[3].children[0].click()
    assert lab.current["id"] == "select"
    config_input = view.container.children[2]
    config_input.value = json.dumps(CONFIG)
    view.container.children[3].children[0].click()
    assert lab.results["select"].passed


def test_public_api_surface():
    names = ("API_VERSION", "run", "load", "read", "fit_peak", "export_html", "labs", "notebook")
    for name in names:
        assert name in heplab.__all__ and getattr(heplab, name)
    with pytest.raises(AttributeError):
        heplab.not_a_feature  # noqa: B018
