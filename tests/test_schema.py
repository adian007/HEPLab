"""Schema v1 contract tests (ADR-0003).

The schema is the project's keystone: these tests pin the public contract so
readers (NanoAOD/AOD/DELPHES) and analyses cannot silently drift apart.
"""

from heplab.schema import (
    ALL,
    EVENT_INFO,
    GEN_PARTICLE,
    MET,
    MUON,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    TRIGGER,
    export,
)


def test_version_is_pinned():
    assert SCHEMA_NAME == "heplab-events"
    assert SCHEMA_VERSION == 1


def test_muon_fields_match_architecture_doc():
    assert MUON.name == "Muon"
    assert MUON.fields == ("pt", "eta", "phi", "mass", "charge", "iso", "quality_flags")
    assert MUON.sim_only is False


def test_sim_only_collections():
    assert GEN_PARTICLE.sim_only and TRIGGER.sim_only
    for name in ("Muon", "Electron", "Photon", "Jet", "MET", "EventInfo"):
        assert ALL[name].sim_only is False


def test_registry_is_complete_and_unique():
    assert set(ALL) == {
        "EventInfo",
        "Muon",
        "Electron",
        "Photon",
        "Jet",
        "MET",
        "GenParticle",
        "Trigger",
    }
    field_names = [f"{c.name}.{f}" for c in ALL.values() for f in c.fields]
    assert len(field_names) == len(set(field_names)), "duplicate schema fields"
    assert all(c.fields for c in ALL.values()), "empty collection spec"
    assert EVENT_INFO.fields == ("run", "luminosity_block", "event", "is_data", "weight")
    assert MET.fields == ("pt", "phi")


def test_export_is_stable_and_jsonable():
    payload = export()
    assert payload["name"] == SCHEMA_NAME
    assert payload["version"] == SCHEMA_VERSION
    assert {c["name"] for c in payload["collections"]} == set(ALL)
    # must be JSON-serializable for provenance stamps (ADR-0008)
    import json

    json.dumps(payload)
