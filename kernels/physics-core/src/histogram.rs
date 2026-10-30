//! Weighted bins, flow counters and compensated sums. Mutations are transactional.
use crate::{finite, require, Result};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Histogram {
    edges: Vec<f64>,
    entries: Vec<u64>,
    sumw: Vec<f64>,
    sumw2: Vec<f64>,
    compensation: Vec<f64>,
    compensation2: Vec<f64>,
}

fn add(sum: &mut f64, correction: &mut f64, value: f64) -> Result<()> {
    let previous = *sum;
    let next = previous + value;
    finite(&[next])?;
    *correction += if previous.abs() >= value.abs() {
        (previous - next) + value
    } else {
        (value - next) + previous
    };
    finite(&[*correction])?;
    *sum = next;
    Ok(())
}

impl Histogram {
    pub fn new(edges: Vec<f64>) -> Result<Self> {
        finite(&edges)?;
        require(
            edges.len() >= 2 && edges.windows(2).all(|pair| pair[0] < pair[1]),
            "invalid histogram edges",
        )?;
        let length = edges.len() + 1;
        Ok(Self {
            edges,
            entries: vec![0; length],
            sumw: vec![0.0; length],
            sumw2: vec![0.0; length],
            compensation: vec![0.0; length],
            compensation2: vec![0.0; length],
        })
    }
    pub fn fill(&mut self, value: f64, weight: f64) -> Result<()> {
        finite(&[value, weight, weight * weight])?;
        let index = self.edges.partition_point(|edge| *edge <= value);
        // Stage the single touched bin, then commit: O(1) and still transactional.
        let entries = self.entries[index]
            .checked_add(1)
            .ok_or_else(|| crate::PhysicsError("entry counter overflow".into()))?;
        let (mut sumw, mut compensation) = (self.sumw[index], self.compensation[index]);
        add(&mut sumw, &mut compensation, weight)?;
        let (mut sumw2, mut compensation2) = (self.sumw2[index], self.compensation2[index]);
        add(&mut sumw2, &mut compensation2, weight * weight)?;
        self.entries[index] = entries;
        self.sumw[index] = sumw;
        self.compensation[index] = compensation;
        self.sumw2[index] = sumw2;
        self.compensation2[index] = compensation2;
        Ok(())
    }
    pub fn merge(&mut self, other: &Self) -> Result<()> {
        require(self.edges == other.edges, "incompatible histogram edges")?;
        let mut next = self.clone();
        for index in 0..self.entries.len() {
            next.entries[index] = next.entries[index]
                .checked_add(other.entries[index])
                .ok_or_else(|| crate::PhysicsError("entry counter overflow".into()))?;
            add(
                &mut next.sumw[index],
                &mut next.compensation[index],
                other.sumw[index],
            )?;
            add(
                &mut next.sumw[index],
                &mut next.compensation[index],
                other.compensation[index],
            )?;
            add(
                &mut next.sumw2[index],
                &mut next.compensation2[index],
                other.sumw2[index],
            )?;
            add(
                &mut next.sumw2[index],
                &mut next.compensation2[index],
                other.compensation2[index],
            )?;
        }
        *self = next;
        Ok(())
    }
    pub fn snapshot(&self) -> Result<serde_json::Value> {
        let sumw: Vec<f64> = self
            .sumw
            .iter()
            .zip(&self.compensation)
            .map(|(a, b)| a + b)
            .collect();
        let sumw2: Vec<f64> = self
            .sumw2
            .iter()
            .zip(&self.compensation2)
            .map(|(a, b)| a + b)
            .collect();
        finite(&sumw)?;
        finite(&sumw2)?;
        Ok(
            serde_json::json!({"edges":self.edges,"entries_with_flow":self.entries,
                            "sumw_with_flow":sumw,"sumw2_with_flow":sumw2}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn negative_weights_and_final_edge_overflow() -> Result<()> {
        let mut h = Histogram::new(vec![0.0, 1.0, 2.0])?;
        for (x, w) in [(-1.0, 1.0), (0.0, 2.0), (0.5, -2.0), (1.0, 3.0), (2.0, 4.0)] {
            h.fill(x, w)?;
        }
        let v = h.snapshot()?;
        assert_eq!(v["sumw_with_flow"], serde_json::json!([1.0, 0.0, 3.0, 4.0]));
        assert_eq!(
            v["sumw2_with_flow"],
            serde_json::json!([1.0, 8.0, 9.0, 16.0])
        );
        let before = h.snapshot()?;
        assert!(h.fill(f64::NAN, 1.0).is_err());
        assert_eq!(before, h.snapshot()?);
        Ok(())
    }
    #[test]
    fn compensated_cancellation_and_checked_merge() -> Result<()> {
        let mut h = Histogram::new(vec![0.0, 1.0])?;
        for w in [1e16, 1.0, -1e16] {
            h.fill(0.5, w)?;
        }
        assert_eq!(h.snapshot()?["sumw_with_flow"][1], 1.0);
        assert!(h.merge(&Histogram::new(vec![0.0, 2.0])?).is_err());
        Ok(())
    }
}
