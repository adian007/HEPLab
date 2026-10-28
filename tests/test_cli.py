"""CLI tests: `heplab version` and `heplab catalog` work; roadmap verbs announce their phase."""

import heplab
from heplab.cli import main


def test_version(capsys):
    assert main(["version"]) == 0
    assert heplab.__version__ in capsys.readouterr().out


def test_catalog_list_finds_verified_run2016g_manifest(capsys):
    assert main(["catalog", "list"]) == 0
    out = capsys.readouterr().out
    assert "Run2016G_DoubleMuon" in out
    assert "30522" in out


def test_catalog_info_prints_manifest(capsys):
    assert main(["catalog", "info", "Run2016G_DoubleMuon"]) == 0
    out = capsys.readouterr().out
    assert "heplab-dataset-manifest/v0" in out
    assert "format" in out
    assert "10.7483/OPENDATA.CMS.ZQS3.LGLP" in out


def test_catalog_info_missing_dataset(capsys):
    assert main(["catalog", "info", "does-not-exist"]) == 1
    assert "not found" in capsys.readouterr().err


def test_implemented_command_help(capsys):
    import pytest

    for verb in ("fetch", "run", "sim", "closure", "plot", "serve"):
        with pytest.raises(SystemExit) as exc:
            main([verb, "--help"])
        assert exc.value.code == 0
        assert "usage:" in capsys.readouterr().out


def test_example_manifest_refuses_to_fetch(capsys, tmp_path, monkeypatch):
    from heplab.io import xrootd

    (tmp_path / "empty.yaml").write_text(
        "schema: heplab-dataset-manifest/v0\nname: empty-example\nrecord: 0\nfiles: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(xrootd, "_manifests_dir", lambda: tmp_path)
    assert main(["fetch", "empty-example"]) == 2
    assert "example manifest" in capsys.readouterr().err


def test_unknown_command_exits_cleanly():
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2
