"""Independent analytic oracles for the scoped numerical reference.

These tests validate neither material transport nor a calibrated CMS detector.
"""

import hashlib
import math

import pytest

from heplab.physics import (
    FourVector,
    NumericalDomainError,
    TrackState,
    WeightedHistogram,
    addressed_normal,
    addressed_uniform,
    propagate_uniform_bz,
    wrap_phi,
)


def test_back_to_back_pair_agrees_with_closed_form_energy():
    momentum, mass = 45.6, 0.105658
    one = FourVector.from_pt_eta_phi_mass(momentum, 0, 0, mass)
    two = FourVector.from_pt_eta_phi_mass(momentum, 0, math.pi, mass)
    assert (one + two).physical_mass == pytest.approx(2 * math.hypot(momentum, mass))


def test_passive_rest_boost_has_known_sign_energy_and_inverse():
    rest = FourVector(5, 0, 0, 0)
    moved = rest.boost((0.6, 0, 0))
    assert moved.energy == pytest.approx(6.25)
    assert moved.px == pytest.approx(-3.75)
    assert moved.physical_mass == pytest.approx(5)
    recovered = moved.boost((-0.6, 0, 0))
    assert recovered.energy == pytest.approx(5)
    assert recovered.px == pytest.approx(0, abs=1e-14)
    assert rest.boost((0, 0, 0)) == rest


@pytest.mark.parametrize("beta", [(1, 0, 0), (2, 0, 0), (math.nan, 0, 0)])
def test_invalid_boost_rejected(beta):
    with pytest.raises(NumericalDomainError):
        FourVector(1, 0, 0, 0).boost(beta)


@pytest.mark.parametrize("values", [(-1, 0, 0, 1), (1, 0, 0, -1), (1, math.inf, 0, 0)])
def test_invalid_cylindrical_coordinates_rejected(values):
    with pytest.raises(NumericalDomainError):
        FourVector.from_pt_eta_phi_mass(*values)


def test_materially_spacelike_vector_rejected_for_physical_mass():
    with pytest.raises(NumericalDomainError):
        _ = FourVector(1, 2, 0, 0).physical_mass


def test_phi_branch_cut_and_periodic_angles():
    assert wrap_phi(math.pi) == -math.pi
    assert wrap_phi(-math.pi) == -math.pi
    assert wrap_phi(0.5 + 2 * math.pi) == pytest.approx(0.5)
    with pytest.raises(NumericalDomainError):
        wrap_phi(math.nan)


def test_hash_address_has_an_independently_fixed_canonical_encoding():
    # Literal byte vector fixes the wire encoding independently of implementation assembly.
    raw = (
        b'{"algorithm":"heplab-sha256-address-v1","correlation_group":"nominal",'
        b'"counter":0,"event_key":"event-1","master_seed":42,"model_id":"reference",'
        b'"object_id":3,"stage_id":"tracking"}'
    )
    bits = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") >> 11
    expected = min(math.nextafter(1, 0), (bits + 0.5) / 2**53)
    assert addressed_uniform(42, "event-1", 3, "tracking") == expected


def test_random_streams_are_invariant_under_schedule_and_unrelated_draws():
    keys = [f"source:entry:{index}" for index in range(30)]
    nominal = {key: addressed_uniform(7, key, 0, "efficiency") for key in keys}
    for key in reversed(keys):
        _ = addressed_uniform(7, key, 0, "unrelated-diagnostic", counter=100)
    reordered = {key: addressed_uniform(7, key, 0, "efficiency") for key in reversed(keys)}
    assert nominal == reordered
    assert all(0 < value < 1 for value in nominal.values())
    assert addressed_normal(7, "event", 0, "resolution") == addressed_normal(
        7, "event", 0, "resolution"
    )
    with pytest.raises(NumericalDomainError):
        addressed_uniform(-1, "event", 0, "stage")


def test_uniform_and_normal_reference_distribution_moments():
    # Fixed independent addresses; broad predeclared ~5-sigma-scale moment checks.
    count = 10_000
    uniforms = [addressed_uniform(42, str(i), 0, "u") for i in range(count)]
    normals = [addressed_normal(42, str(i), 0, "z") for i in range(count)]
    assert abs(math.fsum(uniforms) / count - 0.5) < 0.015
    assert abs(math.fsum(normals) / count) < 0.05
    assert abs(math.fsum(value * value for value in normals) / count - 1) < 0.08


def test_uniform_field_quarter_turn_has_independent_radius_and_charge_sign():
    p, field = 3.0, 2.0
    radius = p / (0.299792458 * field)
    start = TrackState((0, 0, 0), FourVector(math.hypot(p, 0.105658), p, 0, 0), 1)
    moved = propagate_uniform_bz(start, radius * math.pi / 2, field)
    assert moved.position == pytest.approx((radius, -radius, 0), abs=1e-12)
    assert moved.momentum.px == pytest.approx(0, abs=1e-12)
    assert moved.momentum.py == pytest.approx(-p)
    assert moved.momentum.energy == start.momentum.energy
    assert moved.momentum.physical_mass == pytest.approx(start.momentum.physical_mass)
    reverse = propagate_uniform_bz(start, radius * math.pi / 2, -field)
    assert reverse.position == pytest.approx((radius, radius, 0), abs=1e-12)


def test_zero_field_and_tiny_field_have_line_limit_and_correct_time():
    start = TrackState((1, 2, 3), FourVector(5, 3, 0, 0), 1)
    zero = propagate_uniform_bz(start, 6, 0)
    assert zero.position == pytest.approx((7, 2, 3))
    assert zero.time_ns == pytest.approx(6 / (0.6 * 0.299792458))
    tiny = propagate_uniform_bz(start, 6, 1e-15)
    assert tiny.position == pytest.approx(zero.position, abs=1e-12)
    neutral = propagate_uniform_bz(TrackState((1, 2, 3), start.momentum, 0), 6, 100)
    assert neutral.position == zero.position


def test_transport_step_composition_and_longitudinal_pitch():
    initial = TrackState((0, 0, 0), FourVector(math.sqrt(26), 3, 0, 4), 1)
    whole = propagate_uniform_bz(initial, 10, 2)
    composed = propagate_uniform_bz(propagate_uniform_bz(initial, 3, 2), 7, 2)
    assert whole.position == pytest.approx(composed.position, abs=1e-12)
    assert whole.position[2] == pytest.approx(8)
    assert whole.time_ns == pytest.approx(composed.time_ns)
    assert whole.momentum.momentum == pytest.approx(5)
    with pytest.raises(NumericalDomainError):
        propagate_uniform_bz(initial, -1, 2)
    with pytest.raises(NumericalDomainError):
        propagate_uniform_bz(TrackState((0, 0, 0), FourVector(1, 0, 0, 0), 1), 1, 0)


def test_histogram_negative_weights_boundaries_and_flow_variance():
    hist = WeightedHistogram((0, 1, 2))
    for value, weight in [(-1, 1), (0, 2), (0.5, -2), (1, 3), (2, 4)]:
        hist.fill(value, weight)
    snapshot = hist.snapshot()
    assert snapshot["entries_with_flow"] == [1, 2, 1, 1]
    assert snapshot["sumw_with_flow"] == [1, 0, 3, 4]
    assert snapshot["sumw2_with_flow"] == [1, 8, 9, 16]


def test_histogram_compensated_cancellation_and_merge_validation():
    hist = WeightedHistogram((0, 1))
    for weight in (1e16, 1, -1e16):
        hist.fill(0.5, weight)
    assert hist.snapshot()["sumw_with_flow"][1] == 1
    other = WeightedHistogram((0, 1))
    other.fill(0.5, 2)
    hist.merge(other)
    assert hist.snapshot()["sumw_with_flow"][1] == 3
    before = hist.snapshot()
    with pytest.raises(NumericalDomainError):
        hist.merge(WeightedHistogram((0, 2)))
    with pytest.raises(NumericalDomainError):
        hist.fill(math.nan)
    assert hist.snapshot() == before


@pytest.mark.parametrize("edges", [(1,), (0, 0), (1, 0), (0, math.inf)])
def test_invalid_histogram_edges_reject(edges):
    with pytest.raises(NumericalDomainError):
        WeightedHistogram(edges)
