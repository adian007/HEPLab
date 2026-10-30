//! Operation table shared with the Python worker and request validation.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeMap;
use std::fmt;
use std::sync::OnceLock;

/// The single operation table; the worker loads the same file.
pub const OPERATIONS_JSON: &str = include_str!("../../../src/heplab/desktop/operations.json");

#[derive(Debug, Deserialize)]
pub struct Spec {
    pub protocol: String,
    pub max_request_bytes: usize,
    pub max_response_bytes: usize,
    pub max_string_chars: usize,
    pub handshake_timeout_s: u64,
    /// Worker request threads; also how many abandoned calls it may carry.
    pub max_concurrent_requests: usize,
    pub operations: BTreeMap<String, Operation>,
}

#[derive(Debug, Deserialize)]
pub struct Operation {
    pub args: BTreeMap<String, Argument>,
    pub timeout_s: u64,
}

#[derive(Debug, Deserialize)]
pub struct Argument {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(default)]
    pub optional: bool,
    pub access: Option<String>,
    pub min: Option<f64>,
    pub max: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IpcError {
    pub code: String,
    pub message: String,
}

impl IpcError {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.to_owned(),
            message: message.into(),
        }
    }
}

impl fmt::Display for IpcError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for IpcError {}

pub fn spec() -> &'static Spec {
    static SPEC: OnceLock<Spec> = OnceLock::new();
    SPEC.get_or_init(|| serde_json::from_str(OPERATIONS_JSON).expect("operations.json is valid"))
}

fn is_identifier(value: &str) -> bool {
    let bytes = value.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= 128
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'-'))
}

/// Lexical project-relative path check; the worker resolves and confines it.
fn is_project_path(value: &str) -> bool {
    !value.is_empty()
        && !value.starts_with('/')
        && !value.contains(['\\', ':', '\0'])
        && value
            .split('/')
            .all(|part| !matches!(part, "" | "." | ".."))
}

/// Check an operation name and its arguments against the table.
pub fn validate(op: &str, args: &Value) -> Result<&'static Operation, IpcError> {
    let table = spec();
    let operation = table
        .operations
        .get(op)
        .ok_or_else(|| IpcError::new("unknown_operation", format!("unknown operation {op:?}")))?;
    let args: &Map<String, Value> = args
        .as_object()
        .ok_or_else(|| IpcError::new("invalid_arguments", "arguments must be an object"))?;
    if let Some(extra) = args.keys().find(|k| !operation.args.contains_key(*k)) {
        return Err(IpcError::new(
            "invalid_arguments",
            format!("unexpected argument {extra}"),
        ));
    }
    for (name, rule) in &operation.args {
        let Some(value) = args.get(name) else {
            if rule.optional {
                continue;
            }
            return Err(IpcError::new(
                "invalid_arguments",
                format!("missing argument {name}"),
            ));
        };
        match rule.kind.as_str() {
            "id" | "path" => {
                let text = value
                    .as_str()
                    .filter(|s| s.chars().count() <= table.max_string_chars)
                    .ok_or_else(|| {
                        IpcError::new(
                            "invalid_arguments",
                            format!("{name} must be a bounded string"),
                        )
                    })?;
                if rule.kind == "id" && !is_identifier(text) {
                    return Err(IpcError::new(
                        "invalid_arguments",
                        format!("{name} is not a valid identifier"),
                    ));
                }
                if rule.kind == "path" && !is_project_path(text) {
                    return Err(IpcError::new(
                        "path_rejected",
                        "paths must be plain relative paths in the project",
                    ));
                }
            }
            // Structure only; the worker validates contents against the operation's model.
            "object" => {
                if !value.is_object() {
                    return Err(IpcError::new(
                        "invalid_arguments",
                        format!("{name} must be an object"),
                    ));
                }
            }
            "number" | "integer" => {
                let integer = rule.kind == "integer";
                let number = if integer {
                    value.as_i64().map(|n| n as f64)
                } else {
                    value.as_f64().filter(|n| n.is_finite())
                };
                let number = number.ok_or_else(|| {
                    let kind = if integer { "an integer" } else { "a number" };
                    IpcError::new("invalid_arguments", format!("{name} must be {kind}"))
                })?;
                let (low, high) = (rule.min.unwrap_or(f64::MIN), rule.max.unwrap_or(f64::MAX));
                if !(low..=high).contains(&number) {
                    return Err(IpcError::new(
                        "invalid_arguments",
                        format!("{name} is out of range"),
                    ));
                }
            }
            other => {
                return Err(IpcError::new(
                    "invalid_arguments",
                    format!("unsupported argument type {other}"),
                ))
            }
        }
    }
    Ok(operation)
}

/// Serialise one bounded request line (without the trailing newline).
pub fn encode_request(id: u64, op: &str, args: &Value) -> Result<String, IpcError> {
    let line = serde_json::json!({"id": id, "op": op, "args": args}).to_string();
    if line.len() > spec().max_request_bytes {
        return Err(IpcError::new("too_large", "request exceeds IPC budget"));
    }
    Ok(line)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn table_loads_and_names_protocol() {
        assert_eq!(spec().protocol, "heplab-desktop-ipc-v1");
        assert!(spec().operations.contains_key("lab.replay"));
    }

    #[test]
    fn accepts_declared_operations() {
        validate("runs.list", &json!({})).unwrap();
        validate("runs.get", &json!({"run_id": "abc-1.2"})).unwrap();
        validate("jobs.submit", &json!({"config": {"mode": "analytic"}})).unwrap();
        validate("jobs.event", &json!({"job_id": "f00d", "index": 0})).unwrap();
        validate(
            "lab.replay",
            &json!({"profile": "p.json", "raw": "d/run.bin", "output": "o/r.json", "window_ns": 25}),
        )
        .unwrap();
    }

    #[test]
    fn rejects_unknown_malformed_and_unauthorized() {
        let cases = [
            (
                "os.system",
                json!({"command": "rm -rf /"}),
                "unknown_operation",
            ),
            ("runs.list", json!([]), "invalid_arguments"),
            ("runs.list", json!({"shell": true}), "invalid_arguments"),
            ("runs.get", json!({}), "invalid_arguments"),
            ("runs.get", json!({"run_id": "../x"}), "invalid_arguments"),
            ("runs.get", json!({"run_id": 3}), "invalid_arguments"),
            (
                "lab.profile",
                json!({"profile": "/etc/passwd"}),
                "path_rejected",
            ),
            ("lab.profile", json!({"profile": "C:/x"}), "path_rejected"),
            ("lab.profile", json!({"profile": "a\\b"}), "path_rejected"),
            ("lab.profile", json!({"profile": "a/../b"}), "path_rejected"),
            ("lab.profile", json!({"profile": "a//b"}), "path_rejected"),
            (
                "lab.profile",
                json!({"profile": "x".repeat(2000)}),
                "invalid_arguments",
            ),
            (
                "lab.replay",
                json!({"profile": "p", "raw": "r", "output": "o", "window_ns": 0}),
                "invalid_arguments",
            ),
            (
                "jobs.submit",
                json!({"config": "rm -rf"}),
                "invalid_arguments",
            ),
            ("jobs.submit", json!({}), "invalid_arguments"),
            (
                "jobs.get",
                json!({"job_id": "../../x"}),
                "invalid_arguments",
            ),
            (
                "jobs.event",
                json!({"job_id": "a", "index": 1.5}),
                "invalid_arguments",
            ),
            (
                "jobs.event",
                json!({"job_id": "a", "index": 1000}),
                "invalid_arguments",
            ),
            (
                "jobs.event",
                json!({"job_id": "a", "index": -1}),
                "invalid_arguments",
            ),
        ];
        for (op, args, code) in cases {
            assert_eq!(validate(op, &args).unwrap_err().code, code, "{op} {args}");
        }
    }

    #[test]
    fn request_budget_is_enforced() {
        let big = json!({"profile": "a".repeat(spec().max_request_bytes)});
        assert_eq!(
            encode_request(1, "lab.profile", &big).unwrap_err().code,
            "too_large"
        );
    }
}
