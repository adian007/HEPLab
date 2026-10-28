//! Exact intersections of a uniform-field helix with finite cylinders and annular disks.
use crate::{finite, propagate_uniform_bz, require, Result, TrackState};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Surface {
    Cylinder {
        radius_m: f64,
        half_length_m: f64,
    },
    Disk {
        z_m: f64,
        inner_radius_m: f64,
        outer_radius_m: f64,
    },
}

pub fn intersect(state: TrackState, surface: &Surface, bz: f64, limit: f64) -> Result<Vec<f64>> {
    finite(&[bz, limit])?;
    require(
        limit > 0.0 && limit <= 100.0,
        "intersection path budget invalid",
    )?;
    // Validate full state, including momentum shell, positions and time.
    propagate_uniform_bz(state, 0.0, bz)?;
    let p = state.momentum.momentum();
    let [x, y, z] = state.position;
    let ux = state.momentum.px / p;
    let uy = state.momentum.py / p;
    let uz = state.momentum.pz / p;
    let tolerance = 1e-9;
    let (radius, half) = match *surface {
        Surface::Disk {
            z_m,
            inner_radius_m: low,
            outer_radius_m: high,
        } => {
            finite(&[z_m, low, high])?;
            require(low >= 0.0 && high > low, "invalid annular disk")?;
            if uz.abs() < 1e-15 {
                return Ok(vec![]);
            }
            let path = (z_m - z) / uz;
            if path <= tolerance || path > limit {
                return Ok(vec![]);
            }
            let point = propagate_uniform_bz(state, path, bz)?.position;
            let r = point[0].hypot(point[1]);
            return Ok(if r >= low - tolerance && r <= high + tolerance {
                vec![path]
            } else {
                vec![]
            });
        }
        Surface::Cylinder {
            radius_m,
            half_length_m,
        } => (radius_m, half_length_m),
    };
    finite(&[radius, half])?;
    require(radius > 0.0 && half > 0.0, "invalid finite cylinder")?;
    let omega = -0.299792458 * state.charge * bz / p;
    let mut candidates = Vec::new();
    if omega.abs() * limit < 1e-8 {
        let a = ux * ux + uy * uy;
        let b = 2.0 * (x * ux + y * uy);
        let c = x * x + y * y - radius * radius;
        if a < 1e-30 {
            return Ok(vec![]);
        }
        let discriminant = b * b - 4.0 * a * c;
        if discriminant < -1e-13 * 1.0_f64.max(b * b).max((4.0 * a * c).abs()) {
            return Ok(vec![]);
        }
        let root = discriminant.max(0.0).sqrt();
        let q = -0.5 * (b + root.copysign(b));
        if q != 0.0 {
            candidates.extend([q / a, c / q]);
        } else {
            candidates.push(-b / (2.0 * a));
        }
    } else {
        let cx = x - uy / omega;
        let cy = y + ux / omega;
        let distance = cx.hypot(cy);
        let track_radius = ux.hypot(uy) / omega.abs();
        if distance < 1e-14 || track_radius == 0.0 {
            return Ok(vec![]);
        }
        let along = (radius * radius - track_radius * track_radius + distance * distance)
            / (2.0 * distance);
        let height2 = radius * radius - along * along;
        if height2 < -1e-12 * 1.0_f64.max(radius * radius) {
            return Ok(vec![]);
        }
        let height = height2.max(0.0).sqrt();
        let vx = x - cx;
        let vy = y - cy;
        let turn_count = (omega.abs() * limit / std::f64::consts::TAU).ceil();
        require(
            turn_count.is_finite() && turn_count <= 1023.0,
            "helix turn budget exceeded",
        )?;
        let turns = turn_count as i32 + 1;
        for sign in [-1.0, 1.0] {
            let ix = along * cx / distance - sign * height * cy / distance;
            let iy = along * cy / distance + sign * height * cx / distance;
            let dx = ix - cx;
            let dy = iy - cy;
            let angle = (vx * dy - vy * dx).atan2(vx * dx + vy * dy);
            for n in -turns..=turns {
                candidates.push((angle + std::f64::consts::TAU * f64::from(n)) / omega);
            }
        }
    }
    candidates.sort_by(f64::total_cmp);
    let mut output: Vec<f64> = Vec::new();
    for path in candidates {
        if path > tolerance
            && path <= limit
            && (z + uz * path).abs() <= half + tolerance
            && output
                .last()
                .is_none_or(|last| (path - last).abs() > tolerance)
        {
            output.push(path);
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::FourVector;
    #[test]
    fn straight_helix_tangent_and_finite_extent() -> Result<()> {
        let mut state = TrackState {
            position: [0.0; 3],
            momentum: FourVector::new(5.0, 3.0, 0.0, 0.0)?,
            charge: 1.0,
            time_ns: 0.0,
        };
        let surface = Surface::Cylinder {
            radius_m: 1.0,
            half_length_m: 2.0,
        };
        assert_eq!(intersect(state, &surface, 0.0, 10.0)?, vec![1.0]);
        let paths = intersect(state, &surface, 3.8, 10.0)?;
        let radius: f64 = 3.0 / (0.299792458 * 3.8);
        let expected = 2.0 * radius * (1.0 / (2.0 * radius)).asin();
        assert!((paths[0] - expected).abs() < 1e-12);
        state.position = [-2.0, 1.0, 0.0];
        assert_eq!(intersect(state, &surface, 0.0, 10.0)?, vec![2.0]);
        state.position[2] = 3.0;
        assert!(intersect(state, &surface, 0.0, 10.0)?.is_empty());
        state.position = [0.0; 3];
        state.momentum = FourVector::new(1.0, 1e-6, 0.0, 0.0)?;
        let tiny = Surface::Cylinder {
            radius_m: 1e-7,
            half_length_m: 1.0,
        };
        assert!(intersect(state, &tiny, 3.8, 100.0).is_err());
        Ok(())
    }
}
