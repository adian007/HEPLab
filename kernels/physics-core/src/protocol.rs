//! Versioned JSON capability protocol; rejects unknown operations and fields.
use crate::{histogram::Histogram, random, response, FourVector, TrackState};
use serde::Deserialize;
use serde_json::{json, Value};
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Request {
    TraceCmsTracker {
        state: TrackState,
        path_length_m: f64,
        step_m: f64,
    },
    CmsTrackerField {
        position_m: [f64; 3],
    },
    Intersect {
        state: TrackState,
        surface: crate::geometry::Surface,
        bz_tesla: f64,
        max_path_m: f64,
    },
    Material {
        state: TrackState,
        slab: crate::material::Slab,
        address: random::Address,
    },
    Digitize {
        deposit_gev: f64,
        config: crate::material::Electronics,
        address: random::Address,
    },
    Mass {
        first: [f64; 4],
        second: [f64; 4],
    },
    Boost {
        vector: FourVector,
        beta: [f64; 3],
    },
    Propagate {
        state: TrackState,
        path_length_m: f64,
        bz_tesla: f64,
    },
    Uniform {
        address: random::Address,
    },
    Normal {
        address: random::Address,
    },
    Histogram {
        edges: Vec<f64>,
        fills: Vec<[f64; 2]>,
    },
    Simulate {
        particles: Vec<response::Particle>,
        config: response::ResponseConfig,
    },
}

fn execute(request: Request) -> crate::Result<Value> {
    Ok(match request {
        Request::TraceCmsTracker {
            state,
            path_length_m,
            step_m,
        } => crate::cms_field::trace_tracker(state, path_length_m, step_m)?,
        Request::CmsTrackerField { position_m } => {
            json!(crate::cms_field::tracker_field(position_m)?)
        }
        Request::Intersect {
            state,
            surface,
            bz_tesla,
            max_path_m,
        } => json!(crate::geometry::intersect(
            state, &surface, bz_tesla, max_path_m
        )?),
        Request::Material {
            state,
            slab,
            address,
        } => crate::material::interact(state, &slab, &address)?,
        Request::Digitize {
            deposit_gev,
            config,
            address,
        } => crate::material::digitize(deposit_gev, &config, &address)?,
        Request::Mass {
            first: a,
            second: b,
        } => json!(FourVector::from_pt_eta_phi_mass(a[0], a[1], a[2], a[3])?
            .checked_add(FourVector::from_pt_eta_phi_mass(b[0], b[1], b[2], b[3])?)?
            .physical_mass()?),
        Request::Boost { vector, beta } => json!(vector.boost(beta)?),
        Request::Propagate {
            state,
            path_length_m,
            bz_tesla,
        } => json!(crate::propagate_uniform_bz(state, path_length_m, bz_tesla)?),
        Request::Uniform { address } => json!(random::uniform(&address)?),
        Request::Normal { address } => json!(random::normal(&address)?),
        Request::Histogram { edges, fills } => {
            let mut histogram = Histogram::new(edges)?;
            for [x, w] in fills {
                histogram.fill(x, w)?;
            }
            histogram.snapshot()?
        }
        Request::Simulate { particles, config } => response::simulate(&particles, &config)?,
    })
}

pub fn execute_json(input: &str) -> crate::Result<Value> {
    crate::require(input.len() <= 1_048_576, "JSON request exceeds 1 MiB")?;
    let request = serde_json::from_str(input).map_err(|e| crate::PhysicsError(e.to_string()))?;
    execute(request)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn malformed_and_unknown_fields_reject() {
        assert!(execute_json("not json").is_err());
        assert!(execute_json(r#"{"op":"boost","vector":{"energy":1,"px":0,"py":0,"pz":0},"beta":[0,0,0],"extra":true}"#).is_err());
    }
    #[test]
    fn request_allocation_budget_is_enforced_at_library_boundary() {
        assert!(execute_json(&"x".repeat(1_048_577)).is_err());
    }
}
