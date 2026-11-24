"""Tests for the versioned HEPLab operator training catalogue."""

import json
from pathlib import Path

import heplab
from heplab.training import catalogue, get, modules, resume, start


ROOT = Path(__file__).resolve().parents[1]


def test_training_catalogue_contains_verified_eight_module_sequence():
    value = catalogue()
    assert value["schema"] == "heplab-training-catalog-v1"
    assert value["revision"] == 1
    assert len(modules()) == 8
    assert [item["id"] for item in modules()] == [
        "module-1-getting-started",
        "module-2-first-simulation",
        "module-3-event-inspector",
        "module-4-results",
        "module-5-python-jupyter",
        "module-6-cern-open-data",
        "module-7-advanced-workflows",
        "module-8-independent-project",
    ]


def test_training_progress_requires_matching_evidence_and_resumes(tmp_path):
    session = start("module-1-getting-started")
    assert not session.complete(
        "verify-environment", {"kind": "cli_output", "command": "python --version"}
    )["passed"]
    assert session.complete(
        "verify-environment",
        {"kind": "cli_output", "command": "heplab --version"},
    )["passed"]
    assert session.complete(
        "create-project", {"kind": "project_state", "opened": True}
    )["passed"]

    saved = session.save(tmp_path / "progress.json")
    reopened = resume(saved)
    assert reopened.progress()["completed"] == 2


def test_z_lab_remains_the_only_preserved_verified_beginner_workflow():
    assert [item["id"] for item in heplab.labs.available()] == ["z-boson"]
    z = get("module-2-first-simulation")
    evidence = z["steps"][0]["completion_evidence"]
    assert evidence["kind"] == "lab_artifact"
    assert evidence["required"]["schema"] == "heplab-z-boson-result-v1"


def test_training_gallery_manifest_matches_existing_notebooks():
    manifest = json.loads(
        (ROOT / "notebooks" / "gallery" / "gallery.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "heplab-notebook-gallery-v1"
    for entry in manifest["entries"]:
        if entry["runnable"]:
            notebook = ROOT / "notebooks" / "gallery" / entry["path"]
            assert notebook.is_file()
            value = json.loads(notebook.read_text(encoding="utf-8"))
            assert value["nbformat"] == 4


def test_desktop_worker_exposes_the_same_training_catalog(tmp_path):
    from heplab.desktop import worker

    handlers = worker.operations(tmp_path)
    assert "training.catalog" in worker.SPEC["operations"]
    result = handlers["training.catalog"]()
    assert result["schema"] == "heplab-training-catalog-v1"
    assert len(result["modules"]) == 8
