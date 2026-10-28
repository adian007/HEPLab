//! Thin homogeneous slabs: declared stopping power, Gaussian Highland core, and digits.
//! This is not a shower, straggling, or calibrated detector model.
use crate::{finite, propagate_uniform_bz, random, require, FourVector, Result, TrackState};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Slab {
    pub id: String,
    pub thickness_m: f64,
    pub radiation_length_m: f64,
    pub stopping_power_gev_per_m: f64,
    pub min_beta_gamma: f64,
    pub max_beta_gamma: f64,
    pub scatter: bool,
}

pub fn interact(
    state: TrackState,
    slab: &Slab,
    address: &random::Address,
) -> Result<serde_json::Value> {
    random::uniform(address)?;
    finite(&[
        slab.thickness_m,
        slab.radiation_length_m,
        slab.stopping_power_gev_per_m,
        slab.min_beta_gamma,
        slab.max_beta_gamma,
        state.charge,
    ])?;
    require(
        !slab.id.is_empty() && slab.id.len() <= 128,
        "invalid material ID",
    )?;
    require(
        slab.thickness_m >= 0.0
            && slab.radiation_length_m > 0.0
            && slab.stopping_power_gev_per_m >= 0.0
            && slab.min_beta_gamma > 0.0
            && slab.max_beta_gamma >= slab.min_beta_gamma,
        "invalid material parameters",
    )?;
    let p4 = state.momentum;
    let mass = p4.physical_mass()?;
    let p = p4.momentum();
    require(
        mass >= 0.1 && state.charge.abs() == 1.0 && p > 0.0,
        "thin-slab model requires a moving, singly charged heavy particle (mass >= 0.1 GeV)",
    )?;
    let bg = p / mass;
    require(
        bg >= slab.min_beta_gamma && bg <= slab.max_beta_gamma,
        "outside declared stopping-power beta-gamma range",
    )?;
    let deposit = slab.stopping_power_gev_per_m * slab.thickness_m;
    let kinetic = p4.energy - mass;
    require(
        deposit <= 0.1 * kinetic,
        "thin-step loss exceeds 10% of kinetic energy; subdivide with a valid stopping table",
    )?;
    let energy = p4.energy - deposit;
    let remaining_p = ((energy - mass) * (energy + mass)).sqrt();
    require(
        remaining_p / mass >= slab.min_beta_gamma,
        "step exits stopping-power validity range",
    )?;
    let fraction = slab.thickness_m / slab.radiation_length_m;
    let theta = if slab.scatter && slab.thickness_m > 0.0 {
        require(
            (0.001..=0.1).contains(&fraction),
            "Highland core requires 0.001 <= thickness/X0 <= 0.1",
        )?;
        let value =
            0.0136 / ((p / p4.energy) * p) * fraction.sqrt() * (1.0 + 0.038 * fraction.ln());
        require(value <= 0.2, "small-angle scattering domain exceeded")?;
        value
    } else {
        0.0
    };
    let u = [p4.px / p, p4.py / p, p4.pz / p];
    let axis = if u[2].abs() < 0.9 {
        [0.0, 0.0, 1.0]
    } else {
        [1.0, 0.0, 0.0]
    };
    let cross = |a: [f64; 3], b: [f64; 3]| {
        [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]
    };
    let mut v = cross(u, axis);
    let norm = v.iter().map(|x| x * x).sum::<f64>().sqrt();
    for x in &mut v {
        *x /= norm;
    }
    let w = cross(u, v);
    let mut rng = address.clone();
    rng.model_id = "thin-slab-highland-v1".into();
    rng.stage_id = format!("{}.scatter_x", slab.id);
    let a = if theta > 0.0 {
        theta * random::normal(&rng)?
    } else {
        0.0
    };
    rng.stage_id = format!("{}.scatter_y", slab.id);
    let b = if theta > 0.0 {
        theta * random::normal(&rng)?
    } else {
        0.0
    };
    let mut direction = [0.0; 3];
    for i in 0..3 {
        direction[i] = u[i] + a * v[i] + b * w[i];
    }
    let norm = direction.iter().map(|x| x * x).sum::<f64>().sqrt();
    // Midpoint loss/kick convention; total path is specified, not a geometric navigator.
    let middle = propagate_uniform_bz(state, slab.thickness_m * 0.5, 0.0)?;
    let changed = TrackState {
        momentum: FourVector::new(
            energy,
            remaining_p * direction[0] / norm,
            remaining_p * direction[1] / norm,
            remaining_p * direction[2] / norm,
        )?,
        ..middle
    };
    let result = propagate_uniform_bz(changed, slab.thickness_m * 0.5, 0.0)?;
    Ok(
        serde_json::json!({"state":result,"deposit_gev":deposit,"theta0_rad":theta,
        "energy_residual_gev":p4.energy-result.momentum.energy-deposit,
        "model":"thin-slab-highland-v1","validation":"educational_unvalidated",
        "material_id":slab.id,"momentum_exchange":"untracked medium recoil; energy transfer is continuous loss"}),
    )
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Electronics {
    pub gain_adc_per_gev: f64,
    pub pedestal_adc: f64,
    pub noise_sigma_adc: f64,
    pub threshold_adc: f64,
    pub saturation_adc: f64,
}

pub fn digitize(
    deposit_gev: f64,
    config: &Electronics,
    address: &random::Address,
) -> Result<serde_json::Value> {
    random::uniform(address)?;
    finite(&[
        deposit_gev,
        config.gain_adc_per_gev,
        config.pedestal_adc,
        config.noise_sigma_adc,
        config.threshold_adc,
        config.saturation_adc,
    ])?;
    require(
        deposit_gev >= 0.0
            && config.gain_adc_per_gev > 0.0
            && config.noise_sigma_adc >= 0.0
            && config.pedestal_adc >= 0.0
            && config.threshold_adc >= 0.0
            && config.saturation_adc > config.threshold_adc
            && config.saturation_adc <= 16_777_215.0,
        "invalid electronics parameters",
    )?;
    let mut rng = address.clone();
    rng.model_id = "deposit-electronics-v1".into();
    rng.stage_id = "channel_noise".into();
    let analog = deposit_gev * config.gain_adc_per_gev
        + config.pedestal_adc
        + config.noise_sigma_adc * random::normal(&rng)?;
    finite(&[analog])?;
    let accepted = analog >= config.threshold_adc;
    let adc = if accepted {
        Some(analog.clamp(0.0, config.saturation_adc).floor() as u32)
    } else {
        None
    };
    Ok(
        serde_json::json!({"adc":adc,"accepted":accepted,"saturated":analog > config.saturation_adc,
        "analog_adc":analog,"deposit_gev":deposit_gev,"model":"deposit-electronics-v1",
        "validation":"educational_unvalidated"}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn address() -> random::Address {
        random::Address {
            master_seed: 42,
            event_key: "e".into(),
            object_id: 1,
            stage_id: "test".into(),
            counter: 0,
            correlation_group: "nominal".into(),
            model_id: "test".into(),
        }
    }
    #[test]
    fn loss_ledger_mass_and_domain() -> Result<()> {
        let state = TrackState {
            position: [0.0; 3],
            momentum: FourVector::new(10.0, (100.0_f64 - 1.0).sqrt(), 0.0, 0.0)?,
            charge: 1.0,
            time_ns: 0.0,
        };
        let mut slab = Slab {
            id: "silicon".into(),
            thickness_m: 0.001,
            radiation_length_m: 0.0937,
            stopping_power_gev_per_m: 0.4,
            min_beta_gamma: 1.0,
            max_beta_gamma: 100.0,
            scatter: true,
        };
        let value = interact(state, &slab, &address())?;
        assert!((value["deposit_gev"].as_f64().unwrap() - 0.0004).abs() < 1e-15);
        assert!(value["energy_residual_gev"].as_f64().unwrap().abs() < 1e-14);
        let moved: TrackState = serde_json::from_value(value["state"].clone()).unwrap();
        assert!((moved.momentum.physical_mass()? - 1.0).abs() < 1e-12);
        slab.thickness_m = 10.0;
        assert!(interact(state, &slab, &address()).is_err());
        Ok(())
    }
    #[test]
    fn electronics_threshold_saturation_and_identity() -> Result<()> {
        let cfg = Electronics {
            gain_adc_per_gev: 1000.0,
            pedestal_adc: 0.0,
            noise_sigma_adc: 0.0,
            threshold_adc: 5.0,
            saturation_adc: 255.0,
        };
        assert_eq!(
            digitize(0.001, &cfg, &address())?["adc"],
            serde_json::Value::Null
        );
        assert_eq!(digitize(0.01, &cfg, &address())?["adc"], 10);
        assert_eq!(digitize(1.0, &cfg, &address())?["adc"], 255);
        assert_eq!(digitize(1.0, &cfg, &address())?["saturated"], true);
        assert!(digitize(-1.0, &cfg, &address()).is_err());
        Ok(())
    }
}
