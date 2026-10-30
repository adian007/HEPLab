//! Safe, checked physics primitives. Uniform-field motion is vacuum-only.
#![forbid(unsafe_code)]

pub mod cms_field;
pub mod geometry;
pub mod histogram;
pub mod material;
pub mod protocol;
pub mod random;
pub mod response;
pub mod trajectory;

use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

pub type Result<T> = std::result::Result<T, PhysicsError>;

#[derive(Debug, Clone)]
pub struct PhysicsError(pub String);
impl std::fmt::Display for PhysicsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for PhysicsError {}

pub fn require(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(PhysicsError(message.into()))
    }
}

pub fn finite(values: &[f64]) -> Result<()> {
    require(
        values.iter().all(|x| x.is_finite()),
        "nonfinite numerical value",
    )
}

pub fn wrap_phi(angle: f64) -> Result<f64> {
    finite(&[angle])?;
    Ok((angle + PI).rem_euclid(2.0 * PI) - PI)
}

#[derive(Debug, Copy, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FourVector {
    pub energy: f64,
    pub px: f64,
    pub py: f64,
    pub pz: f64,
}

impl FourVector {
    pub fn new(energy: f64, px: f64, py: f64, pz: f64) -> Result<Self> {
        finite(&[energy, px, py, pz])?;
        require(energy >= 0.0, "negative energy")?;
        Ok(Self { energy, px, py, pz })
    }
    pub fn from_pt_eta_phi_mass(pt: f64, eta: f64, phi: f64, mass: f64) -> Result<Self> {
        finite(&[pt, eta, phi, mass])?;
        require(pt >= 0.0 && mass >= 0.0, "negative momentum or mass")?;
        let pz = pt * eta.sinh();
        Self::new(pt.hypot(pz).hypot(mass), pt * phi.cos(), pt * phi.sin(), pz)
    }
    pub fn validate(self) -> Result<Self> {
        Self::new(self.energy, self.px, self.py, self.pz)
    }
    pub fn momentum(self) -> f64 {
        self.px.hypot(self.py).hypot(self.pz)
    }
    pub fn mass_squared(self) -> Result<f64> {
        self.validate()?;
        let e2 = self.energy * self.energy;
        let p2 = self.px * self.px + self.py * self.py + self.pz * self.pz;
        finite(&[e2, p2])?;
        Ok(e2 - p2)
    }
    pub fn physical_mass(self) -> Result<f64> {
        let m2 = self.mass_squared()?;
        let tolerance = 64.0
            * f64::EPSILON
            * (self.energy * self.energy)
                .max(self.momentum().powi(2))
                .max(1.0);
        require(m2 >= -tolerance, "spacelike physical momentum")?;
        Ok(m2.max(0.0).sqrt())
    }
    pub fn checked_add(self, other: Self) -> Result<Self> {
        self.validate()?;
        other.validate()?;
        Self::new(
            self.energy + other.energy,
            self.px + other.px,
            self.py + other.py,
            self.pz + other.pz,
        )
    }
    pub fn boost(self, beta: [f64; 3]) -> Result<Self> {
        self.validate()?;
        finite(&beta)?;
        let b2 = beta.iter().map(|x| x * x).sum::<f64>();
        require(b2 < 1.0, "boost must be subluminal")?;
        let gamma = 1.0 / (1.0 - b2).sqrt();
        let dot = beta[0] * self.px + beta[1] * self.py + beta[2] * self.pz;
        let coefficient = gamma * gamma / (gamma + 1.0) * dot - gamma * self.energy;
        Self::new(
            gamma * (self.energy - dot),
            self.px + coefficient * beta[0],
            self.py + coefficient * beta[1],
            self.pz + coefficient * beta[2],
        )
    }
}

#[derive(Debug, Copy, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrackState {
    pub position: [f64; 3],
    pub momentum: FourVector,
    pub charge: f64,
    pub time_ns: f64,
}

pub fn propagate_uniform_bz(
    state: TrackState,
    path_length_m: f64,
    bz_tesla: f64,
) -> Result<TrackState> {
    finite(&state.position)?;
    finite(&[state.charge, state.time_ns, path_length_m, bz_tesla])?;
    require(
        state.time_ns >= 0.0 && path_length_m >= 0.0,
        "negative time or path",
    )?;
    state.momentum.physical_mass()?;
    let p4 = state.momentum;
    let p = p4.momentum();
    require(
        p.is_finite() && p > 0.0,
        "stopped particle has no direction",
    )?;
    let omega = -0.299_792_458 * state.charge * bz_tesla / p;
    let angle = omega * path_length_m;
    finite(&[angle])?;
    let a2 = angle * angle;
    let (sinc, cosc) = if angle.abs() < 1e-4 {
        (
            1.0 - a2 / 6.0 + a2 * a2 / 120.0,
            angle * (0.5 - a2 / 24.0 + a2 * a2 / 720.0),
        )
    } else {
        (angle.sin() / angle, (1.0 - angle.cos()) / angle)
    };
    let position = [
        state.position[0] + path_length_m * (p4.px * sinc - p4.py * cosc) / p,
        state.position[1] + path_length_m * (p4.px * cosc + p4.py * sinc) / p,
        state.position[2] + path_length_m * p4.pz / p,
    ];
    let momentum = FourVector::new(
        p4.energy,
        p4.px * angle.cos() - p4.py * angle.sin(),
        p4.px * angle.sin() + p4.py * angle.cos(),
        p4.pz,
    )?;
    let time_ns = state.time_ns + path_length_m * p4.energy / (p * 0.299_792_458);
    finite(&position)?;
    finite(&[time_ns])?;
    Ok(TrackState {
        position,
        momentum,
        time_ns,
        ..state
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn near(a: f64, b: f64) {
        assert!((a - b).abs() < 1e-10, "{a} != {b}");
    }
    #[test]
    fn rest_boost_and_inverse() -> Result<()> {
        let rest = FourVector::new(5.0, 0.0, 0.0, 0.0)?;
        let moved = rest.boost([0.6, 0.0, 0.0])?;
        near(moved.energy, 6.25);
        near(moved.px, -3.75);
        near(moved.physical_mass()?, 5.0);
        near(moved.boost([-0.6, 0.0, 0.0])?.px, 0.0);
        assert!(rest.boost([1.0, 0.0, 0.0]).is_err());
        Ok(())
    }
    #[test]
    fn helix_radius_sign_and_line_limit() -> Result<()> {
        let state = TrackState {
            position: [0.0; 3],
            momentum: FourVector::new(5.0, 3.0, 0.0, 0.0)?,
            charge: 1.0,
            time_ns: 0.0,
        };
        let radius = 3.0 / (0.299_792_458 * 2.0);
        let moved = propagate_uniform_bz(state, radius * PI / 2.0, 2.0)?;
        near(moved.position[0], radius);
        near(moved.position[1], -radius);
        near(moved.momentum.py, -3.0);
        near(moved.momentum.energy, 5.0);
        let line = propagate_uniform_bz(state, 6.0, 0.0)?;
        near(line.position[0], 6.0);
        near(line.time_ns, 6.0 / (0.6 * 0.299_792_458));
        Ok(())
    }
    #[test]
    fn invalid_domain_rejected() {
        assert!(FourVector::new(f64::NAN, 0.0, 0.0, 0.0).is_err());
        assert!(FourVector::new(1.0, 2.0, 0.0, 0.0)
            .and_then(|x| x.physical_mass())
            .is_err());
        assert!(FourVector::from_pt_eta_phi_mass(-1.0, 0.0, 0.0, 0.0).is_err());
        near(wrap_phi(PI).unwrap(), -PI);
    }
}
