import json

from heplab.analyses.dimuon.run import invariant_mass, process
from heplab.cli import main


def _event(number, charge, phi):
    return {
        "EventInfo": {"event": number, "is_data": True, "weight": 1.0},
        "Muon": [
            {
                "pt": 45.6,
                "eta": 0.0,
                "phi": phi,
                "mass": 0.105658,
                "charge": charge,
                "iso": 0.01,
                "quality_flags": 1,
            },
            {
                "pt": 45.6,
                "eta": 0.0,
                "phi": phi + 3.141592653589793,
                "mass": 0.105658,
                "charge": -charge,
                "iso": 0.01,
                "quality_flags": 1,
            },
        ],
        "MET": {"pt": 0, "phi": 0},
    }


def test_invariant_mass_z_pair():
    first = {"pt": 45.6, "eta": 0, "phi": 0, "mass": 0.105658}
    second = {"pt": 45.6, "eta": 0, "phi": 3.141592653589793, "mass": 0.105658}
    assert abs(invariant_mass(first, second) - 91.2) < 0.1


def test_dimuon_selection_and_cutflow():
    config = {
        "selection": {
            "muons": {"min_pt": 25, "max_abs_eta": 2.4, "max_rel_iso": 0.15, "min_n": 2},
            "pairs": {"require_opposite_charge": True, "mass_window": [60, 120]},
        },
        "binning": {"dimuon_mass": {"range": [0, 200], "bins": 20}},
    }
    result = process([_event(1, 1, 0)], config)
    assert result["cutflow"]["all"] == 1
    assert result["cutflow"]["mass_window"] == 1
    assert result["histogram"]["entries"] == 1


def test_cli_json_to_artifact(tmp_path, capsys):
    source = tmp_path / "events.json"
    source.write_text(json.dumps([_event(1, 1, 0)]), encoding="utf-8")
    output = tmp_path / "result.json"
    assert main(["run", "dimuon", "--input", str(source), "--output", str(output)]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["histogram"]["entries"] == 1
    assert result["provenance"]["schema_version"] == 1
    assert "Artifact:" in capsys.readouterr().out
