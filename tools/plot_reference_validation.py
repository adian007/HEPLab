"""Export the frozen reference checks as a scientific figure, without refitting."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--report", default="artifacts/reference-calibration.json")
parser.add_argument("--output", default="artifacts/reference-calibration.png")
args = parser.parse_args()
report = json.loads(Path(args.report).read_text())
silicon = report["silicon"]
raw = json.loads(Path("src/heplab/data/reference/silicon-muon.json").read_text())
figure, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
rows = raw["rows"]
knots = np.array(silicon["knots"])
axes[0, 0].plot(knots[:, 0], knots[:, 1], "-", label="Fit knots (25 PDG rows)")
held = [rows[i] for i in silicon["heldout_rows"]]
axes[0, 0].scatter(
    [r["kinetic_gev"] for r in held],
    [r["ionization_gev_per_m"] for r in held],
    s=20,
    label="Held-out PDG rows (24)",
)
axes[0, 0].set(
    xscale="log",
    xlabel="Muon kinetic energy [GeV]",
    ylabel="Mean ionization loss [GeV/m]",
    title="Silicon ionization: PDG reference table",
)
axes[0, 0].legend(fontsize=9)
axes[1, 0].scatter(
    [r["energy_gev"] for r in silicon["heldout_errors"]],
    [100 * r["relative_error"] for r in silicon["heldout_errors"]],
    s=20,
)
axes[1, 0].axhline(2, color="gray", linestyle="--")
axes[1, 0].axhline(-2, color="gray", linestyle="--")
axes[1, 0].set(
    xscale="log",
    xlabel="Muon kinetic energy [GeV]",
    ylabel="Held-out interpolation error [%]",
    title="Predeclared acceptance: max |error| ≤ 2%",
)
response = report["muon_response"]
x = np.arange(len(response["bins"]))
for population, offset, color, label in [
    ("training", -0.07, "#1f77b4", "Calibration shard"),
    ("heldout", 0.07, "#d97722", "Independent held-out shard"),
]:
    stats = [b[population] for b in response["bins"]]
    efficiencies = np.array([s["efficiency"] for s in stats])
    intervals = np.array([s["efficiency_wilson_95"] for s in stats])
    axes[0, 1].errorbar(
        x + offset,
        efficiencies,
        yerr=[efficiencies - intervals[:, 0], intervals[:, 1] - efficiencies],
        fmt="o",
        capsize=3,
        label=label,
        color=color,
    )
    axes[1, 1].plot(
        x + offset, [100 * s["log_width"] for s in stats], "o", label=label, color=color
    )
labels = [f"{b['eta_abs'][0]}–{b['eta_abs'][1]}" for b in response["bins"]]
for axis in axes[:, 1]:
    axis.set_xticks(x, labels)
    axis.set_xlabel("|η| bin")
axes[0, 1].set(
    ylabel="Matched / eligible truth muons",
    ylim=(0.7, 1),
    title="DY muon efficiency; Wilson 95% intervals",
)
axes[0, 1].legend(fontsize=9)
axes[1, 1].set(
    ylabel="Std. dev. of ln(pT reco / pT truth) [%]",
    title="DELPHES response width; pT integrated over 5–200 GeV",
)
for axis in axes.flat:
    axis.grid(alpha=0.2)
figure.suptitle("HEPLab reference calibration — no experimental CMS calibration claim", fontsize=14)
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
figure.savefig(args.output, dpi=170)
print(args.output)
