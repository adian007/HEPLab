//! Versioned, address-derived streams, independent of event processing order.
use crate::{require, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Address {
    pub master_seed: u64,
    pub event_key: String,
    pub object_id: u64,
    pub stage_id: String,
    pub counter: u64,
    pub correlation_group: String,
    pub model_id: String,
}

pub fn uniform(address: &Address) -> Result<f64> {
    let max = (1u64 << 53) - 1;
    require(
        address.master_seed <= max && address.object_id <= max && address.counter <= max,
        "random address integer range",
    )?;
    require(
        !address.event_key.is_empty()
            && !address.stage_id.is_empty()
            && !address.correlation_group.is_empty()
            && !address.model_id.is_empty(),
        "empty random label",
    )?;
    let value = serde_json::json!({"algorithm":"heplab-sha256-address-v1",
        "master_seed":address.master_seed,"event_key":address.event_key,"object_id":address.object_id,
        "stage_id":address.stage_id,"counter":address.counter,"correlation_group":address.correlation_group,
        "model_id":address.model_id});
    // serde_json sorts object keys. Match Python ensure_ascii=True, including surrogate pairs.
    let mut encoded = String::new();
    for character in value.to_string().chars() {
        if character.is_ascii() {
            encoded.push(character);
        } else {
            for unit in character.encode_utf16(&mut [0u16; 2]) {
                use std::fmt::Write;
                write!(&mut encoded, "\\u{unit:04x}").expect("String formatting cannot fail");
            }
        }
    }
    let digest = Sha256::digest(encoded.as_bytes());
    let integer = u64::from_be_bytes(digest[..8].try_into().expect("fixed digest length")) >> 11;
    let result = (integer as f64 + 0.5) / ((1u64 << 53) as f64);
    Ok(result.min(f64::from_bits(1.0f64.to_bits() - 1)))
}

pub fn normal(address: &Address) -> Result<f64> {
    require(
        address.counter < (1u64 << 52),
        "normal address counter overflow",
    )?;
    let mut first = address.clone();
    first.counter = 2 * address.counter;
    let mut second = first.clone();
    second.counter += 1;
    Ok((-2.0 * uniform(&first)?.ln()).sqrt() * (std::f64::consts::TAU * uniform(&second)?).cos())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn addressed_stream_is_open_and_repeatable() -> Result<()> {
        let mut a = Address {
            master_seed: 42,
            event_key: "event-1".into(),
            object_id: 3,
            stage_id: "tracking".into(),
            counter: 0,
            correlation_group: "nominal".into(),
            model_id: "reference".into(),
        };
        let expected = uniform(&a)?;
        assert!(expected > 0.0 && expected < 1.0);
        a.stage_id = "unrelated".into();
        let _ = uniform(&a)?;
        a.stage_id = "tracking".into();
        assert_eq!(expected, uniform(&a)?);
        Ok(())
    }
}
