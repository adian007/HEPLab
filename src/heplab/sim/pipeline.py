"""Bounded, staged adapter to the official DelphesPythia8 executable.

Only the registered Drell--Yan process and CMS card are exposed. The runtime is
provisioned separately; outputs do not become visible as successful runs until
ROOT structure and event weights have been checked.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

from ..io.provenance import config_hash, file_hash, source_snapshot

VERSIONS = {"pythia8": "8.312", "delphes": "3.5.1", "root_base": "6.40.04"}


def _process_options() -> dict:
    # wsl.exe forwards standard input even for noninteractive commands. It must
    # never inherit the desktop worker's JSON request pipe and consume requests
    # intended for the IPC loop while a generation job runs in another thread.
    options = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return options


@lru_cache(maxsize=1)
def _discover_runtime() -> tuple[str, str]:
    """Find the conventional per-user install; never accept a command from the UI."""
    if os.name != "nt":
        prefix = Path.home() / ".cache/heplab/sim-runtime"
        if (prefix / "heplab-runtime.json").is_file():
            return str(prefix), ""
        raise RuntimeError(
            "No runtime in ~/.cache/heplab/sim-runtime. See the runtime setup guide."
        )
    return _discover_wsl_runtime()


def _discover_wsl_runtime() -> tuple[str, str]:
    try:
        listed = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=5,
            check=True,
            **_process_options(),
        ).stdout
        names = listed.decode("utf-16-le" if b"\x00" in listed else "utf-8-sig").splitlines()
        names = [
            n.strip().lstrip("\ufeff") for n in names if n.strip() and "docker" not in n.lower()
        ]
        names.sort(key=lambda name: ("ubuntu" not in name.lower(), name.lower()))
        probe = (
            "import json,os,pathlib; p=pathlib.Path.home()/'.cache/heplab/sim-runtime'; "
            "assert (p/'heplab-runtime.json').is_file() and (p/'bin/DelphesPythia8').is_file(); "
            "print(json.dumps({'prefix':str(p),'distro':os.environ['WSL_DISTRO_NAME']}))"
        )
        failures = []
        for name in names[:2]:
            try:
                found = subprocess.run(
                    ["wsl.exe", "-d", name, "--", "python3", "-c", probe],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                    **_process_options(),
                )
                value = json.loads(found.stdout)
                return value["prefix"], value["distro"]
            except subprocess.TimeoutExpired:
                failures.append(f"{name} did not respond within 30 seconds")
                continue
            except (OSError, ValueError, AssertionError, subprocess.SubprocessError):
                continue
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "WSL runtime discovery failed. Install/start WSL Ubuntu "
            "and the pinned simulation runtime."
        ) from exc
    if failures:
        raise RuntimeError(
            "WSL runtime check timed out: "
            + "; ".join(failures)
            + ". Wait for WSL to start, then restart HEPLab."
        )
    raise RuntimeError(
        "No PYTHIA8/DELPHES install found in WSL. Install the pinned runtime in "
        "~/.cache/heplab/sim-runtime and restart HEPLab."
    )


def normalization(log: str, expected: int) -> dict:
    pattern = r"\|\s*sum\s*\|\s*(\d+)\s+(\d+)\s+(\d+)\s*\|\s*([\d.eE+\-]+)\s+([\d.eE+\-]+)\s*\|"
    matches = re.findall(pattern, log)
    if len(matches) != 1:
        raise ValueError("missing or ambiguous generator normalization statistics")
    tried, selected, accepted = map(int, matches[0][:3])
    sigma, error = map(float, matches[0][3:])
    if (
        accepted != expected
        or not tried >= selected >= accepted
        or not all(math.isfinite(v) and v >= 0 for v in (sigma, error))
    ):
        raise ValueError("invalid generator normalization statistics")
    return {
        "trials": tried,
        "selected": selected,
        "accepted": accepted,
        "cross_section_pb": sigma * 1e9,
        "cross_section_error_pb": error * 1e9,
        "cross_section_source": "PYTHIA stat() sum row, rounded printed precision",
        "cross_section_convention": (
            "registered mass window and forced muon decay included; no extra decay factor"
        ),
        "independent_validation": "pending",
    }


def settings(*, events=100, seed=42, energy_gev=13000.0) -> str:
    if type(events) is not int or not 1 <= events <= 100_000:
        raise ValueError("events must be an integer in [1, 100000]")
    if type(seed) is not int or not 1 <= seed <= 900_000_000:
        raise ValueError("PYTHIA seed must be in [1, 900000000]")
    if not isinstance(energy_gev, int | float) or not math.isfinite(energy_gev):
        raise ValueError("invalid beam energy")
    if not 1000 <= energy_gev <= 14000:
        raise ValueError("registered pp process supports 1000--14000 GeV")
    return f"""! HEPLab registered DY mumu; serial generator stream; no pileup
Main:numberOfEvents = {events}
Main:timesAllowErrors = 10
Next:numberShowInfo = 0
Next:numberShowProcess = 0
Next:numberShowEvent = 0
Beams:idA = 2212
Beams:idB = 2212
Beams:eCM = {energy_gev:.12g}
Random:setSeed = on
Random:seed = {seed}
Tune:pp = 14
PDF:pSet = 13
WeakSingleBoson:ffbar2gmZ = on
PhaseSpace:mHatMin = 60.
PhaseSpace:mHatMax = 120.
23:onMode = off
23:onIfAny = 13
"""


def _linux(path: Path, distro: str) -> str:
    result = subprocess.run(
        ["wsl.exe", "-d", distro, "--", "wslpath", "-a", path.resolve().as_posix()],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
        **_process_options(),
    )
    return result.stdout.strip()


def _wsl_file(distro: str, path: str) -> str:
    # A cold WSL service can time out once even after discovery succeeds.
    # These reads are idempotent: retry once, then surface the real failure.
    for attempt in range(2):
        try:
            return subprocess.run(
                ["wsl.exe", "-d", distro, "--", "cat", path],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
                **_process_options(),
            ).stdout
        except subprocess.TimeoutExpired:
            if attempt:
                raise
    raise AssertionError("unreachable")


def runtime() -> dict:
    prefix = os.environ.get("HEPLAB_SIM_PREFIX")
    if not prefix:
        prefix, distro = _discover_runtime()
    else:
        distro = os.environ.get("HEPLAB_SIM_WSL_DISTRO", "")
    if any(importlib.util.find_spec(name) is None for name in ("numpy", "uproot", "awkward")):
        raise RuntimeError(
            "This build lacks ROOT readers (numpy/uproot/awkward). "
            "Use a collision-enabled HEPLab build."
        )
    # Read the pinned install inventory through the same runtime used to execute.
    inventory = f"{prefix}/heplab-runtime.json"
    if distro:
        record = json.loads(_wsl_file(distro, inventory))
    else:
        record = json.loads(Path(inventory).read_text(encoding="utf8"))
    if record.get("versions") != VERSIONS or not record.get("explicit_lock_sha256"):
        raise RuntimeError("simulation runtime inventory is absent or incompatible")
    return {"prefix": prefix, "distro": distro, "inventory": record}


def capabilities() -> dict:
    try:
        rt = runtime()
        return {
            "available": True,
            "versions": rt["inventory"]["versions"],
            "host": "WSL " + rt["distro"] if rt["distro"] else "Native runtime",
            "prefix": rt["prefix"],
        }
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc)}


def inspect_root(path: Path, expected: int) -> dict:
    import numpy as np
    import uproot

    with uproot.open(path) as root:
        tree = root["Delphes"]
        if tree.num_entries != expected:
            raise ValueError(f"incomplete generation: expected {expected}, got {tree.num_entries}")
        required = {
            "Particle.PID",
            "Particle.Status",
            "Particle.M1",
            "Particle.M2",
            "Particle.D1",
            "Particle.D2",
            "Particle.E",
            "Particle.Px",
            "Particle.Py",
            "Particle.Pz",
            "Event.Weight",
        }
        available = {name.rsplit("/", 1)[-1] for name in tree.keys()}
        if not required.issubset(available):
            raise ValueError(
                "DELPHES output lacks truth fields: " + ", ".join(sorted(required - available))
            )
        weights = np.asarray(tree["Event.Weight"].array(library="ak").to_list(), dtype=float)
        if weights.shape != (expected, 1) or not np.isfinite(weights).all():
            raise ValueError("invalid generator event weights")
        residual_max = 0.0
        # At the generator boundary all stable species, including neutrinos,
        # balance both incoming beam protons. ROOT stores rounded native values.
        for chunk in tree.iterate(
            ["Particle." + k for k in ("PID", "Status", "E", "Px", "Py", "Pz")],
            step_size=16,
            library="ak",
        ):
            for row in chunk:
                values = {
                    k: np.asarray(row["Particle." + k].to_list())
                    for k in ("PID", "Status", "E", "Px", "Py", "Pz")
                }
                if not all(np.isfinite(v).all() for v in values.values()):
                    raise ValueError("nonfinite truth graph")
                incoming = (values["Status"] == 4) & (values["PID"] == 2212)
                final = values["Status"] == 1
                if incoming.sum() != 2 or not final.any():
                    raise ValueError("invalid pp generator boundary")
                residual = max(
                    abs(float(values[k][incoming].sum() - values[k][final].sum()))
                    for k in ("E", "Px", "Py", "Pz")
                )
                energy = float(values["E"][incoming].sum())
                if residual > max(0.002, 2e-5 * energy):
                    raise ValueError("generator four-momentum conservation check failed")
                residual_max = max(residual_max, residual)
        return {
            "events": expected,
            "sumw": float(weights.sum()),
            "sumw2": float(np.square(weights).sum()),
            "positive_sumw": float(weights[weights > 0].sum()),
            "negative_sumw": float(weights[weights < 0].sum()),
            "max_truth_four_momentum_residual_gev": residual_max,
            "truth_conservation_tolerance": "max(0.002 GeV, 2e-5 * beam total energy)",
            "truth_graph": "native Particle mother/daughter indices preserved in ROOT",
            "normalization": "generator log retained; cross section not independently validated",
        }


def run_chain(
    *,
    output: str | Path,
    events=100,
    seed=42,
    energy_gev=13000.0,
    cancel: threading.Event | None = None,
    timeout_s=600,
) -> Path:
    card_text = settings(events=events, seed=seed, energy_gev=energy_gev)
    if not 1 <= timeout_s <= 3600:
        raise ValueError("timeout outside [1, 3600] seconds")
    rt = runtime()
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("run destination already exists; runs are immutable")
    stage = Path(tempfile.mkdtemp(prefix=".sim-", dir=target.parent))
    try:
        cmnd = stage / "generation.cmnd"
        cmnd.write_text(card_text, encoding="utf8")
        prefix, distro = rt["prefix"], rt["distro"]
        path = (lambda p: _linux(p, distro)) if distro else (lambda p: str(p))
        detector_card = f"{prefix}/share/delphes/cards/delphes_card_CMS.tcl"
        # Tcl list quoting: reject metacharacters in administrator-provided prefix.
        if any(c in prefix for c in "{}\n\r"):
            raise ValueError("runtime prefix contains unsupported Tcl path characters")
        if distro:
            native_card = _wsl_file(distro, detector_card)
        else:
            native_card = Path(detector_card).read_text(encoding="utf8")
        (stage / "response.tcl").write_text(
            f"set RandomSeed {seed}\n" + native_card, encoding="utf8"
        )
        worker = stage / "worker.py"
        shutil.copyfile(Path(__file__).with_name("worker.py"), worker)
        # The card and all relative dependencies stay in the frozen runtime tree.
        command = [
            f"{prefix}/bin/python",
            path(worker),
            prefix,
            path(stage),
            str(timeout_s),
        ]
        if distro:
            command = [
                "wsl.exe",
                "-d",
                distro,
                "--",
                "env",
                f"LD_LIBRARY_PATH={prefix}/lib",
                f"PYTHIA8DATA={prefix}/share/Pythia8/xmldoc",
                *command,
            ]
        env = os.environ.copy()
        if not distro:
            env["LD_LIBRARY_PATH"] = f"{prefix}/lib"
            env["PYTHIA8DATA"] = f"{prefix}/share/Pythia8/xmldoc"
        start = time.monotonic()
        with (stage / "generator.log").open("wb") as log:
            process = subprocess.Popen(
                command,
                cwd=target.parent,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                **_process_options(),
            )
            try:
                while process.poll() is None:
                    if cancel is not None and cancel.wait(0.1):
                        raise RuntimeError("simulation cancelled")
                    if cancel is None:
                        time.sleep(0.1)
                    if time.monotonic() - start > timeout_s + 30:
                        raise RuntimeError("simulation timeout")
                    if (stage / "generator.log").stat().st_size > 16 * 1024 * 1024:
                        raise RuntimeError("generator log budget exceeded")
                if process.returncode:
                    failure = stage / "worker-error.json"
                    if failure.is_file():
                        raise RuntimeError(json.loads(failure.read_text(encoding="utf8"))["error"])
                    tail = (stage / "generator.log").read_text(encoding="utf8", errors="replace")[
                        -4000:
                    ]
                    raise RuntimeError(
                        f"DelphesPythia8 exited {process.returncode}; no run committed\n{tail}"
                    )
            finally:
                if process.poll() is None:
                    (stage / ".cancel").touch()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=15)
        if cancel is not None and cancel.is_set():
            raise RuntimeError("simulation cancelled")
        if (stage / "generator.log").stat().st_size > 16 * 1024 * 1024:
            raise RuntimeError("generator log budget exceeded")
        if (stage / "events.root").stat().st_size > 2**30:
            raise RuntimeError("ROOT output exceeds 1 GiB run budget")
        summary = inspect_root(stage / "events.root", events)
        summary.update(
            normalization(
                (stage / "generator.log").read_text(encoding="utf8", errors="replace"), events
            )
        )
        from ..readers.delphes import read

        first = next(read(stage / "events.root", entry_stop=1))
        preview = {"event": 0, "muons": first["Muon"], "weight": first["EventInfo"]["weight"]}
        (stage / "preview.json").write_text(json.dumps(preview, allow_nan=False), encoding="utf8")
        record = {
            "schema_version": 1,
            "backend": "DelphesPythia8",
            "versions": VERSIONS,
            "validation": "unvalidated",
            "process": "pp_gammaZ_mumu_60_120_GeV",
            "beam_energy_total_gev": energy_gev,
            "runtime_host": "WSL " + distro if distro else "Native runtime",
            "seed": seed,
            "pileup": False,
            "source_snapshot_sha256": source_snapshot(),
            "units": {"energy": "GeV", "cross_section": "pb", "truth_position_native": "mm"},
            "runtime": rt["inventory"],
            "summary": summary,
            "config_sha256": config_hash({"cmnd": card_text}),
            "files": {p.name: file_hash(p) for p in stage.iterdir() if p.is_file()},
        }
        (stage / "run.json").write_text(
            json.dumps(record, indent=2, allow_nan=False), encoding="utf8"
        )
        # rename cannot replace a populated run directory; fail rather than merge.
        if target.exists():
            raise ValueError("run destination already exists")
        if cancel is not None and cancel.is_set():
            raise RuntimeError("simulation cancelled")
        # Publication starts the commit point. A later cancellation cannot undo
        # a completed immutable native run.
        stage.rename(target)
        return target
    finally:
        if stage.exists():
            # WSL can release DrvFS directory handles shortly after process exit.
            for attempt in range(30):
                try:
                    shutil.rmtree(stage)
                    break
                except PermissionError:
                    if attempt == 29:
                        raise
                    time.sleep(0.1)
