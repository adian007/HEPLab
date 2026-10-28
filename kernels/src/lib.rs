//! Python ABI boundary; all physics and validation live in the pure Rust core.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn run_json(py: Python<'_>, request: String) -> PyResult<String> {
    py.allow_threads(move || {
        let result = heplab_physics::protocol::execute_json(&request)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        serde_json::to_string(&result).map_err(|error| PyValueError::new_err(error.to_string()))
    })
}

#[pymodule]
fn heplab_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_json, m)?)?;
    m.add("ENGINE_VERSION", "0.1.0")?;
    m.add("FIDELITY", "T0-vacuum-and-educational-response")?;
    Ok(())
}
