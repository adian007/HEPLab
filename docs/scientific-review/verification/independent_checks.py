"""Small independent scale and invariant checks for the HEPLab review.

Run from the repository root with the project's environment:

    python docs/scientific-review/verification/independent_checks.py

This is a review aid, not a production test suite or external detector validation.
The expected values below are derived from the equations and constants cited in
the scientific-review documents. CMS checks compare a pinned field function with
an independent ODE integrator over momentum, direction, charge and domain edges;
they do not validate the field against measurements.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from heplab.physics.calibration import interpolate
from heplab.physics.cms_field import trace_tracker, tracker_field
from heplab.physics.constants import (
    CURVATURE_GEV_T_METRES,
    MUON_MASS_GEV,
    MUON_MEAN_LIFETIME_S,
    SPEED_OF_LIGHT_M_PER_NS,
    SPEED_OF_LIGHT_M_PER_S,
)
from heplab.physics.curvature import curvature_sweep
from heplab.physics.detector import surface_paths
from heplab.physics.lifetime import mean_decay_path_m, survival_probability
from heplab.physics.material import digitize, interact
from heplab.physics.reference import (
    FourVector,
    TrackState,
    addressed_uniform,
    propagate_uniform_bz,
)

ROOT = Path(__file__).resolve().parents[3]
MUON_MASS_PDG_GEV = MUON_MASS_GEV
MUON_MASS_CODE_GEV = MUON_MASS_GEV
MUON_MEAN_LIFE_S = MUON_MEAN_LIFETIME_S
C_M_S = SPEED_OF_LIGHT_M_PER_S
C_M_NS = SPEED_OF_LIGHT_M_PER_NS
CURVATURE = CURVATURE_GEV_T_METRES


def close(actual: float, expected: float, tolerance: float, label: str) -> None:
    if not math.isfinite(actual) or abs(actual - expected) > tolerance:
        raise AssertionError(
            f"{label}: actual={actual:.16g}, expected={expected:.16g}, tol={tolerance:g}"
        )


def field_rhs(_path: float, values: np.ndarray, charge: float = 1.0) -> list[float]:
    field = tracker_field([float(values[0]), float(values[1]), float(values[2])])
    magnitude = math.hypot(float(values[3]), float(values[4]), float(values[5]))
    ux, uy, uz = (float(values[i]) / magnitude for i in (3, 4, 5))
    return [
        ux,
        uy,
        uz,
        CURVATURE * charge * (uy * field[2] - uz * field[1]),
        CURVATURE * charge * (uz * field[0] - ux * field[2]),
        CURVATURE * charge * (ux * field[1] - uy * field[0]),
    ]


def main() -> None:
    checks: dict[str, object] = {}

    # A 45 GeV/c, back-to-back pair has M = 2 sqrt(p^2 + m_mu^2).
    p = 45.0
    mass = MUON_MASS_CODE_GEV
    particle = FourVector(math.hypot(p, mass), p, 0.0, 0.0)
    antiparticle = FourVector(math.hypot(p, mass), -p, 0.0, 0.0)
    pair_mass_independent = 2.0 * math.hypot(p, mass)
    pair_mass_engine = (particle + antiparticle).physical_mass
    close(pair_mass_engine, pair_mass_independent, 2e-12, "back-to-back invariant mass")
    checks["invariant_mass"] = {
        "engine_gev": pair_mass_engine,
        "independent_gev": pair_mass_independent,
        "absolute_difference_gev": abs(pair_mass_engine - pair_mass_independent),
        "pass_tolerance_gev": 2e-12,
    }

    # Exact uniform-solenoid solution: R=pT/(k |q| B), delta_phi=s/R.
    state = TrackState((0.0, 0.0, 0.0), particle, 1.0, 0.0)
    bz, path = 3.8, 1.0
    moved = propagate_uniform_bz(state, path, bz)
    radius = p / (CURVATURE * bz)
    angle = path / radius
    expected_position = (radius * math.sin(angle), radius * (math.cos(angle) - 1.0), 0.0)
    for axis, actual, expected in zip("xyz", moved.position, expected_position, strict=True):
        close(actual, expected, 2e-13, f"uniform-field {axis} coordinate")
    close(moved.momentum.energy, state.momentum.energy, 0.0, "magnetic energy conservation")
    close(moved.momentum.momentum, state.momentum.momentum, 2e-14, "magnetic |p| conservation")
    close(moved.time_ns, path * state.momentum.energy / (p * C_M_NS), 2e-13, "time of flight")
    checks["uniform_solenoid"] = {
        "radius_m": radius,
        "bend_angle_rad_over_1m": angle,
        "position_m": list(moved.position),
        "momentum_magnitude_change_gev": moved.momentum.momentum - p,
        "energy_change_gev": moved.momentum.energy - state.momentum.energy,
        "engine_vs_independent_position_tolerance_m": 2e-13,
    }

    # Curvature/sagitta sweep: compare exact software trajectories with a
    # separately evaluated circle formula, then report (without a pass gate)
    # how the pinned OAE field differs from a uniform 3.8 T helix.
    sweep = curvature_sweep()
    maximum_sagitta_residual = 0.0
    for row in sweep["ideal_uniform_field"]:
        field = row["field_t"]
        charge = row["charge_e"]
        if field == 0:
            expected_sagitta = 0.0
        else:
            row_radius = row["radius_m"]
            angle = (
                CURVATURE
                * charge
                * field
                * sweep["config"]["path_length_m"]
                / row["momentum_gev_c"]
            )
            expected_sagitta = math.copysign(
                row_radius * (1 - math.cos(abs(angle) / 2)), charge * field
            )
        residual = abs(row["signed_sagitta_m"] - expected_sagitta)
        close(residual, 0.0, 2e-12, "uniform-field independent sagitta formula")
        maximum_sagitta_residual = max(maximum_sagitta_residual, residual)
    oae_differences = [
        row["difference_from_uniform_3_8t_endpoint_m"] for row in sweep["tracker_oae_reference"]
    ]
    checks["curvature_sagitta_sweep"] = {
        "uniform_field_cases": len(sweep["ideal_uniform_field"]),
        "tracker_reference_cases": len(sweep["tracker_oae_reference"]),
        "momenta_gev_c": sweep["config"]["momenta_gev_c"],
        "uniform_fields_t": sweep["config"]["uniform_fields_t"],
        "charges_e": sweep["config"]["charges_e"],
        "maximum_independent_sagitta_formula_residual_m": maximum_sagitta_residual,
        "oae_vs_uniform_3_8t_endpoint_difference_m": {
            "minimum": min(oae_differences),
            "maximum": max(oae_differences),
        },
        "scope": (
            "exact uniform-field sagitta formula plus bounded pinned OAE comparison; "
            "OAE deltas have no field-measurement pass gate"
        ),
        "not_established": [
            "CMS field measurement agreement",
            "run-era conditions",
            "material transport",
            "detector calibration",
        ],
    }

    # A separate field-scale check for a 1 GeV/c muon over a CMS-sized 15 m path.
    mean_path = mean_decay_path_m(1.0)
    survival = survival_probability(1.0, 15.0)
    checks["muon_lifetime_survival_separate_experiment"] = {
        "momentum_gev_c": 1.0,
        "mean_decay_path_m": mean_path,
        "survival_over_15m_if_modelled": survival,
        "decay_probability_over_15m_if_modelled": 1.0 - survival,
        "muon_mass_code_minus_pdg_gev": MUON_MASS_CODE_GEV - MUON_MASS_PDG_GEV,
    }

    # Read the frozen PDG-derived table, independently interpolate in log(T).
    calibration_path = ROOT / "src/heplab/data/reference/silicon-calibration.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf8"))
    kinetic = math.hypot(45.0, MUON_MASS_CODE_GEV) - MUON_MASS_CODE_GEV
    stopping = interpolate(calibration["knots"], kinetic)
    thickness_m = 0.001
    deposit_gev = stopping * thickness_m
    close(deposit_gev, stopping * thickness_m, 1e-15, "continuous mean slab deposit")
    checks["silicon_mean_loss"] = {
        "kinetic_energy_gev": kinetic,
        "table_interpolated_stopping_power_gev_per_m": stopping,
        "default_slab_thickness_m": thickness_m,
        "mean_deposit_mev": deposit_gev * 1000.0,
        "table_heldout_max_abs_relative_error": calibration["max_abs_relative_error"],
        "scope": "PDG table interpolation only; not straggling or detector calibration",
    }

    # Table endpoints are exact knots; out-of-domain interpolation fails closed.
    low, high = calibration["knots"][0], calibration["knots"][-1]
    close(interpolate(calibration["knots"], low[0]), low[1], 0.0, "low table knot")
    close(interpolate(calibration["knots"], high[0]), high[1], 0.0, "high table knot")
    try:
        interpolate(calibration["knots"], low[0] / 2)
    except ValueError:
        table_rejects_low = True
    else:
        raise AssertionError("silicon interpolation accepted energy below its declared table")
    checks["silicon_table_domain"] = {
        "minimum_kinetic_energy_gev": low[0],
        "maximum_kinetic_energy_gev": high[0],
        "exact_endpoints_reproduced": True,
        "below_domain_rejected": table_rejects_low,
    }

    # Straight-line limits provide closed-form cylinder and annular-disk roots.
    straight = TrackState(
        (0.0, 0.0, 0.0),
        FourVector(math.hypot(10.0, mass), 6.0, 0.0, 8.0),
        1.0,
        0.0,
    )
    cylinder_paths = surface_paths(
        straight,
        {"kind": "cylinder", "radius_m": 1.0, "half_length_m": 2.0},
        0.0,
        4.0,
    )
    disk_paths = surface_paths(
        straight,
        {"kind": "disk", "z_m": 2.0, "inner_radius_m": 1.0, "outer_radius_m": 2.0},
        0.0,
        4.0,
    )
    close(cylinder_paths[0], 5.0 / 3.0, 2e-14, "straight finite-cylinder intersection")
    close(disk_paths[0], 2.5, 2e-14, "straight annular-disk intersection")
    checks["straight_geometry_intersections"] = {
        "cylinder_path_m": cylinder_paths,
        "independent_cylinder_path_m": 5.0 / 3.0,
        "disk_path_m": disk_paths,
        "independent_disk_path_m": 2.5,
        "scope": "closed-form zero-field roots inside finite surface bounds",
    }

    # Independently derive continuous slab energy transfer, mass shell and Highland width.
    material_address = {
        "master_seed": 731,
        "event_key": "independent-slab-check",
        "object_id": 0,
        "stage_id": "material-check",
        "counter": 0,
        "correlation_group": "nominal",
        "model_id": "independent-slab-check-v1",
    }
    slab_kinetic = math.hypot(10.0, mass) - mass
    slab_stopping = interpolate(calibration["knots"], slab_kinetic)
    slab = {
        "id": "independent-si-check",
        "thickness_m": 0.001,
        "radiation_length_m": 0.0937,
        "stopping_power_gev_per_m": slab_stopping,
        "min_beta_gamma": 1.0,
        "max_beta_gamma": 1000.0,
        "scatter": True,
    }
    scattered = interact(straight, slab, material_address)
    initial_energy = straight.momentum.energy
    expected_deposit = slab["thickness_m"] * slab_stopping
    expected_energy = initial_energy - expected_deposit
    expected_momentum = math.sqrt(expected_energy**2 - mass**2)
    close(scattered["deposit_gev"], expected_deposit, 0.0, "continuous slab energy transfer")
    close(scattered["state"]["momentum"]["energy"], expected_energy, 2e-15, "slab energy ledger")
    close(scattered["energy_residual_gev"], 0.0, 2e-15, "slab energy residual")
    output_p = math.sqrt(
        sum(scattered["state"]["momentum"][axis] ** 2 for axis in ("px", "py", "pz"))
    )
    close(output_p, expected_momentum, 3e-14, "slab outgoing on-shell momentum")
    fraction = slab["thickness_m"] / slab["radiation_length_m"]
    expected_theta = (
        0.0136
        / (straight.momentum.momentum**2 / initial_energy)
        * math.sqrt(fraction)
        * (1 + 0.038 * math.log(fraction))
    )
    close(scattered["theta0_rad"], expected_theta, 2e-16, "Highland projected core scale")
    electronics = {
        "gain_adc_per_gev": 1000.0,
        "pedestal_adc": 0.0,
        "noise_sigma_adc": 0.0,
        "threshold_adc": 0.0,
        "saturation_adc": 255.0,
    }
    digitized = digitize(expected_deposit, electronics, material_address)
    close(digitized["deposit_gev"], expected_deposit, 0.0, "electronics preserves deposit input")
    checks["thin_silicon_slab_bookkeeping"] = {
        "initial_energy_gev": initial_energy,
        "kinetic_energy_for_table_gev": slab_kinetic,
        "table_stopping_power_gev_per_m": slab_stopping,
        "mean_deposit_gev": expected_deposit,
        "outgoing_energy_gev": scattered["state"]["momentum"]["energy"],
        "independent_on_shell_momentum_gev": expected_momentum,
        "energy_residual_gev": scattered["energy_residual_gev"],
        "highland_theta0_rad": scattered["theta0_rad"],
        "digitizer_input_deposit_gev": digitized["deposit_gev"],
        "scope": (
            "continuous mean loss, Gaussian Highland core and separate "
            "illustrative electronics only"
        ),
        "not_established": ["straggling", "secondary production", "sensor calibration"],
    }

    # Same pinned CMS tracker field and RK4 algorithm, compared at halved steps.
    direction = (math.cos(0.4), math.sin(0.4), math.sinh(0.4))
    norm = math.sqrt(sum(x * x for x in direction))
    direction = tuple(x / norm for x in direction)
    momentum = 20.0
    vector = FourVector(math.hypot(momentum, mass), *(momentum * x for x in direction))
    cms_state = TrackState((0.0, 0.0, 0.0), vector, 1.0, 0.0)
    cms_results = {step: trace_tracker(cms_state, 1.0, step) for step in (0.01, 0.005, 0.0025)}
    endpoints = {step: result["state"]["position"] for step, result in cms_results.items()}
    errors = {
        f"{step:g}_vs_{step / 2:g}_m": math.dist(endpoints[step], endpoints[step / 2])
        for step in (0.01, 0.005)
    }
    if not errors["0.01_vs_0.005_m"] > errors["0.005_vs_0.0025_m"]:
        raise AssertionError(f"CMS-field step halving did not converge monotonically: {errors}")

    # Independently integrate the same sourced field ODE with SciPy DOP853.
    initial = np.array([0.0, 0.0, 0.0, *(momentum * x for x in direction)])
    independent = solve_ivp(
        field_rhs,
        (0.0, 1.0),
        initial,
        method="DOP853",
        rtol=1e-13,
        atol=1e-14,
        max_step=0.0025,
    )
    if not independent.success:
        raise AssertionError(f"independent SciPy DOP853 integration failed: {independent.message}")
    dop853_endpoint = independent.y[:3, -1].tolist()
    rk4_vs_dop853 = math.dist(endpoints[0.005], dop853_endpoint)
    close(rk4_vs_dop853, 0.0, 1e-10, "RK4 vs independent DOP853 endpoint")
    checks["cms_tracker_rk4_step_halving"] = {
        "path_m": 1.0,
        "steps_m": list(cms_results),
        "endpoint_m": endpoints[0.0025],
        "endpoint_differences_m": errors,
        "dop853_endpoint_m": dop853_endpoint,
        "rk4_5mm_vs_dop853_endpoint_difference_m": rk4_vs_dop853,
        "independent_integrator_tolerance_m": 1e-10,
        "momentum_drift_by_step": {
            f"{step:g}": result["max_relative_momentum_drift"]
            for step, result in cms_results.items()
        },
        "interpretation": (
            "within-integrator convergence only; field reference comparison is separate"
        ),
    }

    # Broader integration grid: momentum, direction and signed charge.
    field_grid = []
    phi = 0.37
    for grid_momentum in (1.0, 20.0, 100.0):
        for eta in (-2.2, 0.0, 2.2):
            for charge in (-1.0, 1.0):
                transverse_fraction = 1 / math.cosh(eta)
                unit = (
                    transverse_fraction * math.cos(phi),
                    transverse_fraction * math.sin(phi),
                    math.tanh(eta),
                )
                grid_state = TrackState(
                    (0.0, 0.0, 0.0),
                    FourVector(
                        math.hypot(grid_momentum, mass),
                        *(grid_momentum * component for component in unit),
                    ),
                    charge,
                )
                rk4 = trace_tracker(grid_state, 1.0, 0.005)
                initial_grid = np.array(
                    [0.0, 0.0, 0.0, *(grid_momentum * component for component in unit)]
                )
                dop853 = solve_ivp(
                    field_rhs,
                    (0.0, 1.0),
                    initial_grid,
                    method="DOP853",
                    rtol=1e-12,
                    atol=1e-13,
                    max_step=0.0025,
                    args=(charge,),
                )
                if not dop853.success:
                    raise AssertionError(f"domain-grid DOP853 integration failed: {dop853.message}")
                difference = math.dist(rk4["state"]["position"], dop853.y[:3, -1])
                close(difference, 0.0, 1e-10, "field domain-grid RK4/DOP853 endpoint")
                field_grid.append(
                    {
                        "momentum_gev_c": grid_momentum,
                        "eta": eta,
                        "charge_e": charge,
                        "endpoint_difference_m": difference,
                    }
                )

    edge_state = TrackState(
        (0.0, 0.0, 2.79),
        FourVector(
            math.hypot(20.0, mass),
            20.0 / math.cosh(1.0),
            0.0,
            20.0 * math.tanh(1.0),
        ),
        1.0,
    )
    edge_result = trace_tracker(edge_state, 1.0, 0.005)
    edge_position = edge_result["state"]["position"]
    close(edge_position[2], 2.8, 1e-6, "field validity-edge stopping point")
    tracker_field(edge_position)
    edge_momentum = edge_result["state"]["momentum"]
    edge_p = math.hypot(edge_momentum["px"], edge_momentum["py"], edge_momentum["pz"])
    next_probe = [
        edge_position[index] + 1e-5 * edge_momentum[axis] / edge_p
        for index, axis in enumerate(("px", "py", "pz"))
    ]
    try:
        tracker_field(next_probe)
    except ValueError:
        boundary_rejects_step = True
    else:
        raise AssertionError("field transport continued outside the pinned OAE domain")
    checks["cms_tracker_domain_grid"] = {
        "independent_integrator_cases": len(field_grid),
        "grid": field_grid,
        "boundary_termination": edge_result["termination"],
        "actual_path_m": edge_result["actual_path_m"],
        "final_position_m": edge_position,
        "next_outward_field_probe_rejected": boundary_rejects_step,
        "scope": "fixed OAE function; no field-measurement or run-era validation",
    }

    # Check addressed uniforms are stable and that the declared distribution is plausible.
    def uniform(i: int, stage: str) -> float:
        return addressed_uniform(
            20261030,
            "review-seed-check",
            i,
            stage,
            model_id="review-independent-check-v1",
        )

    repeat = uniform(17, "uniform")
    close(repeat, uniform(17, "uniform"), 0.0, "address repeatability")
    sample = [uniform(i, "uniform") for i in range(10_000)]
    mean = statistics.fmean(sample)
    variance = statistics.variance(sample)
    if abs(mean - 0.5) > 0.015 or abs(variance - 1.0 / 12.0) > 0.003:
        raise AssertionError(f"addressed uniform sample outside review bounds: {mean}, {variance}")
    checks["addressed_uniform"] = {
        "draws": len(sample),
        "mean": mean,
        "expected_mean": 0.5,
        "sample_variance": variance,
        "expected_variance": 1.0 / 12.0,
        "repeatable_same_address": True,
    }

    report = {
        "purpose": "independent review calculations; not production validation",
        "python": __import__("sys").version.split()[0],
        "results": checks,
        "all_checks_passed": True,
    }
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
