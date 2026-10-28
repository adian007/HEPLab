//! CMS OAE tracker parametrization, nominal 3.8 T only.
//! Port: CMSSW_10_6_30 BCyl.h/TkBfield.cc, V. Karimaki; Apache-2.0.
//! c04fa510bb587b8ee3fa171888468f80de714fa8. No extrapolation outside validity.
use crate::{finite, require, FourVector, Result, TrackState};
use serde_json::{json, Value};

fn inside(p: [f64; 3]) -> bool {
    p[0].hypot(p[1]) < 1.15 && p[2].abs() < 2.8
}

/// Bounded RK4 vacuum transport. Stop at validity edge; never substitute zero field.
pub fn trace_tracker(state: TrackState, path_length_m: f64, step_m: f64) -> Result<Value> {
    finite(&state.position)?;
    finite(&[state.charge, state.time_ns, path_length_m, step_m])?;
    state.momentum.physical_mass()?;
    let p = state.momentum.momentum();
    require(
        p >= 0.1 && state.charge.abs() <= 1.0 && state.time_ns >= 0.0,
        "tracker transport requires p>=0.1 GeV, |q|<=1 and nonnegative time",
    )?;
    require(
        (0.0..=20.0).contains(&path_length_m) && (0.001..=0.01).contains(&step_m),
        "tracker transport path/step budget exceeded",
    )?;
    require(
        inside(state.position),
        "starting state outside CMS tracker field validity",
    )?;
    let mut y = [
        state.position[0],
        state.position[1],
        state.position[2],
        state.momentum.px,
        state.momentum.py,
        state.momentum.pz,
    ];
    let mut points = vec![state.position];
    let mut paths = vec![0.0];
    let mut path = 0.0;
    let mut max_drift: f64 = 0.0;
    let mut stopped = false;
    fn derivative(y: [f64; 6], charge: f64) -> Result<[f64; 6]> {
        let b = tracker_field([y[0], y[1], y[2]])?;
        let p = y[3].hypot(y[4]).hypot(y[5]);
        let u = [y[3] / p, y[4] / p, y[5] / p];
        let k = 0.299_792_458 * charge;
        Ok([
            u[0],
            u[1],
            u[2],
            k * (u[1] * b[2] - u[2] * b[1]),
            k * (u[2] * b[0] - u[0] * b[2]),
            k * (u[0] * b[1] - u[1] * b[0]),
        ])
    }
    fn advance(y: [f64; 6], h: f64, q: f64) -> Result<[f64; 6]> {
        let k1 = derivative(y, q)?;
        let k2 = derivative(std::array::from_fn(|i| y[i] + h * 0.5 * k1[i]), q)?;
        let k3 = derivative(std::array::from_fn(|i| y[i] + h * 0.5 * k2[i]), q)?;
        let k4 = derivative(std::array::from_fn(|i| y[i] + h * k3[i]), q)?;
        let result =
            std::array::from_fn(|i| y[i] + h * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) / 6.0);
        require(
            inside([result[0], result[1], result[2]]),
            "step leaves field validity",
        )?;
        Ok(result)
    }
    for _ in 0..20_100 {
        let remaining = path_length_m - path;
        if remaining <= 1e-12 {
            break;
        }
        let mut h = step_m.min(remaining).min(0.05 * p / (0.299_792_458 * 4.0));
        let candidate = loop {
            match advance(y, h, state.charge) {
                Ok(candidate) => break Some(candidate),
                Err(_) if h > 1e-7 => h *= 0.5,
                Err(_) => break None,
            }
        };
        let Some(mut next) = candidate else {
            stopped = true;
            break;
        };
        let magnitude = next[3].hypot(next[4]).hypot(next[5]);
        let drift = (magnitude / p - 1.0).abs();
        require(drift < 1e-7, "RK4 momentum drift exceeds numerical gate")?;
        max_drift = max_drift.max(drift);
        for component in &mut next[3..] {
            *component *= p / magnitude;
        }
        y = next;
        path += h;
        points.push([y[0], y[1], y[2]]);
        paths.push(path);
    }
    require(
        stopped || path_length_m - path <= 1e-12,
        "tracker step budget exhausted",
    )?;
    let final_state = TrackState {
        position: [y[0], y[1], y[2]],
        momentum: FourVector::new(state.momentum.energy, y[3], y[4], y[5])?,
        charge: state.charge,
        time_ns: state.time_ns + path * state.momentum.energy / (p * 0.299_792_458),
    };
    Ok(
        json!({"state":final_state,"points":points,"path_m":paths,"actual_path_m":path,
        "termination":if stopped {"field_validity_boundary"} else {"path_budget"},
        "max_relative_momentum_drift":max_drift,"step_m":step_m,
        "field_model":"cms-oae-1103l-3.8T-tracker-v1"}),
    )
}

pub fn tracker_field([x, y, mut z]: [f64; 3]) -> Result<[f64; 3]> {
    finite(&[x, y, z])?;
    let r2 = x * x + y * y;
    require(
        r2 < 1.15 * 1.15 && z.abs() < 2.8,
        "CMS OAE field requires r<1.15 m and |z|<2.8 m",
    )?;
    let a: f64 = 4.24326;
    let length: f64 = 15.0201;
    let ap2 = 4.0 * a * a / (length * length);
    let half_b = 0.5 * 3.81492 * (1.0 + ap2).sqrt();
    let hlova = 1.0 / ap2.sqrt();
    let inverse_a = 2.0 * hlova / length;
    z -= 0.0178712;
    fn derivatives(u: f64) -> [f64; 4] {
        let base = 1.0 / (1.0 + u * u);
        let root = base.sqrt();
        [
            u * root,
            base * root,
            -3.0 * base * base * u * root,
            -3.0 * base.powi(3) * root * (1.0 - 4.0 * u * u),
        ]
    }
    let fu = derivatives(hlova - z * inverse_a);
    let gv = derivatives(hlova + z * inverse_a);
    let rat = 0.5 * inverse_a;
    let rat2 = rat * rat * r2;
    let br = half_b * rat * (fu[1] - gv[1] - (fu[3] - gv[3]) * rat2 * 0.5)
        + 0.000656527 * z * (z.abs() - 2.45818).powi(2);
    let bz = half_b * (fu[0] + gv[0] - (fu[2] + gv[2]) * rat2)
        - 0.00778695
            * ((-(z - 2.125).powi(2) / 1.77436_f64.powi(2)).exp()
                + (-(z + 2.125).powi(2) / 1.77436_f64.powi(2)).exp());
    Ok([br * x, br * y, bz])
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn transport_boundary_energy_and_domain() {
        let state = TrackState {
            position: [0.0; 3],
            momentum: FourVector::from_pt_eta_phi_mass(1.0, 0.0, 0.0, 0.105).unwrap(),
            charge: 1.0,
            time_ns: 0.0,
        };
        let result = trace_tracker(state, 16.0, 0.005).unwrap();
        assert_eq!(result["termination"], "field_validity_boundary");
        let final_state: TrackState = serde_json::from_value(result["state"].clone()).unwrap();
        assert!((final_state.position[0].hypot(final_state.position[1]) - 1.15).abs() < 2e-7);
        assert_eq!(final_state.momentum.energy, state.momentum.energy);
        assert!((final_state.momentum.momentum() - 1.0).abs() < 1e-14);
        let neutral = TrackState {
            charge: 0.0,
            ..state
        };
        let line = trace_tracker(neutral, 0.6, 0.005).unwrap();
        let final_line: TrackState = serde_json::from_value(line["state"].clone()).unwrap();
        assert!((final_line.position[0] - 0.6).abs() < 1e-13);
        assert!(trace_tracker(state, 21.0, 0.005).is_err());
        assert!(trace_tracker(state, 1.0, 0.0001).is_err());
        assert!(trace_tracker(state, f64::NAN, 0.005).is_err());
    }
    #[test]
    fn axis_symmetry_and_domain() {
        let origin = tracker_field([0.0, 0.0, 0.0]).unwrap();
        assert_eq!(&origin[..2], &[0.0, 0.0]);
        assert!((origin[2] - 3.8).abs() < 0.02);
        let a = tracker_field([0.7, 0.0, 1.0]).unwrap();
        let b = tracker_field([0.0, 0.7, 1.0]).unwrap();
        assert_eq!(a[0], b[1]);
        assert_eq!(a[2], b[2]);
        assert!(tracker_field([1.15, 0.0, 0.0]).is_err());
        assert!(tracker_field([0.0, 0.0, 2.8]).is_err());
        assert!(tracker_field([f64::NAN, 0.0, 0.0]).is_err());
    }
}
