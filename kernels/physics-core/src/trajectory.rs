//! Composite uniform-field trajectory with guide-surface crossings in one call.
//!
//! Semantics mirror `heplab.physics.detector.trajectory`: vacuum motion in an
//! ideal axial bore with straight-line continuation past the field exit, a
//! uniform sample grid, and crossings of caller-declared surfaces. Surfaces
//! travel with the request so the Python detector model stays the single
//! source of geometry truth.
use crate::geometry::Surface;
use crate::{finite, propagate_uniform_bz, require, Result, TrackState};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Debug, Deserialize)]
pub struct NamedSurface {
    pub id: String,
    #[serde(flatten)]
    pub surface: Surface,
}

#[derive(Debug, Deserialize)]
pub struct TrajectoryRequest {
    pub state: TrackState,
    pub surfaces: Vec<NamedSurface>,
    pub exit_surfaces: Vec<NamedSurface>,
    pub bz_tesla: f64,
    pub max_path_m: f64,
    pub step_m: f64,
}

pub fn trajectory(request: TrajectoryRequest) -> Result<Value> {
    let TrajectoryRequest {
        state,
        surfaces,
        exit_surfaces,
        bz_tesla,
        max_path_m,
        step_m,
    } = request;
    finite(&[bz_tesla, max_path_m, step_m])?;
    require(
        !surfaces.is_empty() && !exit_surfaces.is_empty(),
        "trajectory requires nonempty surface lists",
    )?;
    require(
        0.0 < max_path_m && max_path_m <= 20.0,
        "trajectory sampling/path budget invalid",
    )?;
    require(
        (0.005..=0.2).contains(&step_m),
        "trajectory sampling/path budget invalid",
    )?;
    let [x, y, z] = state.position;
    require(
        x.hypot(y) < 3.0 && z.abs() < 6.25,
        "trajectory must start inside the modeled solenoid bore",
    )?;
    // Propagate validates the full state (vacuum, on-shell momentum).
    propagate_uniform_bz(state, 0.0, bz_tesla)?;

    let mut exits: Vec<f64> = Vec::new();
    for named in &exit_surfaces {
        exits.extend(crate::geometry::intersect(
            state,
            &named.surface,
            bz_tesla,
            max_path_m,
        )?);
    }
    let exit_path = exits
        .iter()
        .copied()
        .min_by(f64::total_cmp)
        .unwrap_or(max_path_m);
    let boundary = propagate_uniform_bz(state, exit_path, bz_tesla)?;

    let at = |path: f64| -> Result<TrackState> {
        if path <= exit_path {
            propagate_uniform_bz(state, path, bz_tesla)
        } else {
            propagate_uniform_bz(boundary, path - exit_path, 0.0)
        }
    };

    let mut crossings: Vec<(String, f64, [f64; 3], f64)> = Vec::new();
    for named in &surfaces {
        for path in crate::geometry::intersect(state, &named.surface, bz_tesla, exit_path)? {
            let moved = at(path)?;
            crossings.push((named.id.clone(), path, moved.position, moved.time_ns));
        }
    }
    crossings.sort_by(|a, b| a.1.total_cmp(&b.1));

    let mut paths: Vec<f64> = vec![0.0, max_path_m, exit_path];
    let count = (max_path_m / step_m).ceil() as i64 + 1;
    for i in 0..count {
        paths.push((i as f64 * step_m).min(max_path_m));
    }
    for (_, path, _, _) in &crossings {
        paths.push(*path);
    }
    // Python builds a set (exact-equality dedup) then sorts ascending.
    paths.sort_by(f64::total_cmp);
    paths.dedup_by(|a, b| a == b);

    let mut points: Vec<[f64; 3]> = Vec::with_capacity(paths.len());
    for path in &paths {
        points.push(at(*path)?.position);
    }
    let crossings: Vec<Value> = crossings
        .iter()
        .map(|(surface_id, path_m, position_m, time_ns)| {
            json!({
                "surface_id": surface_id,
                "path_m": path_m,
                "position_m": position_m,
                "time_ns": time_ns,
                "kind": "predicted_surface_crossing",
            })
        })
        .collect();
    Ok(json!({
        "points": points,
        "path_m": paths,
        "crossings": crossings,
        "field_exit_path_m": if exits.is_empty() { Value::Null } else { json!(exit_path) },
        "termination": if exits.is_empty() {
            "path_budget_inside_field"
        } else {
            "path_budget_after_field_exit"
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::FourVector;

    fn state(px: f64, py: f64, pz: f64, charge: f64) -> TrackState {
        TrackState {
            position: [0.0; 3],
            momentum: FourVector::new((px * px + py * py + pz * pz + 0.01116).sqrt(), px, py, pz)
                .unwrap(),
            charge,
            time_ns: 0.0,
        }
    }

    fn surfaces() -> Vec<NamedSurface> {
        serde_json::from_value(json!([
            {"id": "BPIX1", "kind": "cylinder", "radius_m": 0.044, "half_length_m": 0.265},
            {"id": "strip-envelope", "kind": "cylinder", "radius_m": 1.10, "half_length_m": 2.80},
        ]))
        .unwrap()
    }

    fn exit_surfaces() -> Vec<NamedSurface> {
        serde_json::from_value(json!([
            {"id": "solenoid-bore", "kind": "cylinder", "radius_m": 3.0, "half_length_m": 6.25},
            {"id": "bore-end-m", "kind": "disk", "z_m": -6.25, "inner_radius_m": 0.0, "outer_radius_m": 3.0},
            {"id": "bore-end-p", "kind": "disk", "z_m": 6.25, "inner_radius_m": 0.0, "outer_radius_m": 3.0},
        ]))
        .unwrap()
    }

    #[test]
    fn samples_reach_budget_and_crossings_carry_ids() -> Result<()> {
        let request = TrajectoryRequest {
            state: state(10.0, 0.0, 1.0, 1.0),
            surfaces: surfaces(),
            exit_surfaces: exit_surfaces(),
            bz_tesla: 3.8,
            max_path_m: 16.0,
            step_m: 0.05,
        };
        let value = trajectory(request)?;
        let paths = value["path_m"].as_array().unwrap();
        assert_eq!(paths.last().unwrap().as_f64().unwrap(), 16.0);
        // Sample grid is monotone and starts at zero.
        let values: Vec<f64> = paths.iter().map(|v| v.as_f64().unwrap()).collect();
        assert_eq!(values[0], 0.0);
        assert!(values.windows(2).all(|w| w[0] < w[1]));
        // A 10 GeV/c track must cross the strip envelope inside the bore.
        let crossings = value["crossings"].as_array().unwrap();
        assert!(crossings
            .iter()
            .any(|c| c["surface_id"] == "strip-envelope"));
        assert_eq!(value["termination"], "path_budget_after_field_exit");
        Ok(())
    }

    #[test]
    fn straight_through_exit_reports_field_exit() -> Result<()> {
        let request = TrajectoryRequest {
            state: state(0.0, 0.0, 20.0, 1.0),
            surfaces: surfaces(),
            exit_surfaces: exit_surfaces(),
            bz_tesla: 3.8,
            max_path_m: 16.0,
            step_m: 0.05,
        };
        let value = trajectory(request)?;
        assert_eq!(value["termination"], "path_budget_after_field_exit");
        let exit = value["field_exit_path_m"].as_f64().unwrap();
        assert!((exit - 6.25).abs() < 1e-12);
        Ok(())
    }

    #[test]
    fn domain_rejects_outside_bore_and_bad_step() {
        let request = TrajectoryRequest {
            state: TrackState {
                position: [3.5, 0.0, 0.0],
                momentum: FourVector::new(10.0, 10.0, 0.0, 0.0).unwrap(),
                charge: 1.0,
                time_ns: 0.0,
            },
            surfaces: surfaces(),
            exit_surfaces: exit_surfaces(),
            bz_tesla: 3.8,
            max_path_m: 16.0,
            step_m: 0.05,
        };
        assert!(trajectory(request).is_err());
        let request = TrajectoryRequest {
            state: state(10.0, 0.0, 1.0, 1.0),
            surfaces: surfaces(),
            exit_surfaces: exit_surfaces(),
            bz_tesla: 3.8,
            max_path_m: 16.0,
            step_m: 0.4,
        };
        assert!(trajectory(request).is_err());
    }
}
