//! Explicitly educational object response with positive lognormal resolution.
use crate::{finite, propagate_uniform_bz, random, require, FourVector, Result, TrackState};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Particle {
    pub object_id: u64,
    pub state: TrackState,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResponseConfig {
    #[serde(default = "unit_scale")]
    pub momentum_scale: f64,
    pub seed: u64,
    pub event_key: String,
    pub efficiency: f64,
    pub relative_pt_resolution: f64,
    pub path_length_m: f64,
    pub bz_tesla: f64,
    pub max_objects: usize,
}

fn unit_scale() -> f64 {
    1.0
}

pub fn simulate(particles: &[Particle], config: &ResponseConfig) -> Result<serde_json::Value> {
    finite(&[
        config.efficiency,
        config.relative_pt_resolution,
        config.path_length_m,
        config.bz_tesla,
        config.momentum_scale,
    ])?;
    require(
        (0.0..=1.0).contains(&config.efficiency) && config.relative_pt_resolution >= 0.0,
        "invalid response parameters",
    )?;
    require(
        config.momentum_scale > 0.0,
        "momentum scale must be positive",
    )?;
    require(
        config.path_length_m >= 0.0
            && config.max_objects > 0
            && particles.len() <= config.max_objects,
        "object or path budget invalid",
    )?;
    let mut ids = std::collections::HashSet::new();
    let mut objects = Vec::new();
    for particle in particles {
        require(ids.insert(particle.object_id), "duplicate object identity")?;
        let propagated =
            propagate_uniform_bz(particle.state, config.path_length_m, config.bz_tesla)?;
        let mut address = random::Address {
            master_seed: config.seed,
            event_key: config.event_key.clone(),
            object_id: particle.object_id,
            stage_id: "tracking_efficiency".into(),
            counter: 0,
            correlation_group: "nominal".into(),
            model_id: "educational-response-v1".into(),
        };
        if random::uniform(&address)? >= config.efficiency {
            continue;
        }
        address.stage_id = "momentum_resolution".into();
        let sigma = config
            .relative_pt_resolution
            .hypot(1.0)
            .ln()
            .mul_add(2.0, 0.0)
            .sqrt();
        let scale =
            config.momentum_scale * (sigma * random::normal(&address)? - 0.5 * sigma * sigma).exp();
        let p4 = propagated.momentum;
        let mass = p4.physical_mass()?;
        let momentum = FourVector::new(
            (p4.momentum() * scale).hypot(mass),
            p4.px * scale,
            p4.py * scale,
            p4.pz * scale,
        )?;
        objects.push(Particle {
            object_id: particle.object_id,
            state: TrackState {
                momentum,
                ..propagated
            },
        });
    }
    Ok(
        serde_json::json!({"fidelity":"T0","validation":"educational_unvalidated",
                         "model":"educational-response-v1","objects":objects,
                         "input_objects":particles.len(),"accepted_objects":objects.len()}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn efficiency_endpoints_and_reordering() -> Result<()> {
        let state = TrackState {
            position: [0.0; 3],
            momentum: FourVector::new(5.0, 3.0, 0.0, 0.0)?,
            charge: 1.0,
            time_ns: 0.0,
        };
        let mut config = ResponseConfig {
            momentum_scale: 1.0,
            seed: 42,
            event_key: "e".into(),
            efficiency: 0.0,
            relative_pt_resolution: 0.1,
            path_length_m: 1.0,
            bz_tesla: 2.0,
            max_objects: 10,
        };
        let particles = [
            Particle {
                object_id: 0,
                state,
            },
            Particle {
                object_id: 1,
                state,
            },
        ];
        assert_eq!(simulate(&particles, &config)?["accepted_objects"], 0);
        config.efficiency = 1.0;
        let first = simulate(&particles, &config)?;
        let second = simulate(&[particles[1].clone(), particles[0].clone()], &config)?;
        assert_eq!(first["objects"][0], second["objects"][1]);
        assert_eq!(first["objects"][1], second["objects"][0]);
        Ok(())
    }
}
