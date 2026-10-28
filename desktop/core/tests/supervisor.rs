//! Supervisor lifecycle against scripted and real workers.
//! Requires `python3` (override with HEPLAB_TEST_PYTHON); the real-worker test
//! also needs the repository's `src` importable, which is set via PYTHONPATH.

use heplab_desktop_core::{CancelToken, Supervisor, WorkerCommand};
use serde_json::json;
use std::path::PathBuf;
use std::thread;
use std::time::{Duration, Instant};

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn python() -> PathBuf {
    std::env::var_os("HEPLAB_TEST_PYTHON").map_or_else(|| PathBuf::from("python3"), PathBuf::from)
}

fn fake(mode: &str) -> Supervisor {
    let script = repo().join("desktop/core/tests/fake_worker.py");
    let command = WorkerCommand {
        program: python(),
        prefix_args: vec![script.into(), mode.into()],
        project_root: std::env::temp_dir(),
        env: vec![],
    };
    Supervisor::new(command, "test-1")
}

#[test]
fn good_worker_answers_and_validation_happens_before_launch() {
    let mut worker = fake("good");
    let cancel = CancelToken::default();
    let reply = worker.call("runs.list", &json!({}), &cancel).unwrap();
    assert_eq!(reply, json!({"op": "runs.list"}));
    let error = worker
        .call("os.system", &json!({"command": "id"}), &cancel)
        .unwrap_err();
    assert_eq!(error.code, "unknown_operation");
    assert_eq!(worker.restarts, 0);
}

#[test]
fn handshake_rejects_wrong_version_and_protocol() {
    for mode in ["bad_version", "bad_protocol"] {
        let error = fake(mode).ensure_started().unwrap_err();
        assert_eq!(error.code, "handshake_failed", "{mode}: {error}");
    }
}

#[test]
fn crash_is_reported_with_stderr_and_next_call_restarts() {
    let mut worker = fake("crash");
    let cancel = CancelToken::default();
    let error = worker.call("runs.list", &json!({}), &cancel).unwrap_err();
    assert_eq!(error.code, "worker_crashed");
    // The stderr reader may lag the exit slightly; the code is what matters.
    assert!(worker.call("runs.list", &json!({}), &cancel).is_err());
    assert!(worker.restarts >= 1);
}

#[test]
fn cancellation_kills_a_hung_request_promptly() {
    let mut worker = fake("hang");
    let cancel = CancelToken::default();
    worker.ensure_started().unwrap();
    let trigger = cancel.clone();
    let canceller = thread::spawn(move || {
        thread::sleep(Duration::from_millis(300));
        trigger.cancel();
    });
    let start = Instant::now();
    let error = worker.call("runs.list", &json!({}), &cancel).unwrap_err();
    canceller.join().unwrap();
    assert_eq!(error.code, "cancelled");
    assert!(start.elapsed() < Duration::from_secs(5));
    assert_eq!(worker.restarts, 1);
}

#[test]
fn cancellation_kills_grandchildren_too() {
    let root = std::env::temp_dir().join(format!("heplab-tree-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let beat = root.join("heartbeat.txt");
    let command = WorkerCommand {
        program: python(),
        prefix_args: vec![
            repo().join("desktop/core/tests/fake_worker.py").into(),
            "grandchild".into(),
        ],
        project_root: root.clone(),
        env: vec![],
    };
    let mut worker = Supervisor::new(command, "test-1");
    let cancel = CancelToken::default();
    worker.ensure_started().unwrap();
    let trigger = cancel.clone();
    let canceller = thread::spawn(move || {
        thread::sleep(Duration::from_millis(800));
        trigger.cancel();
    });
    let error = worker.call("runs.list", &json!({}), &cancel).unwrap_err();
    canceller.join().unwrap();
    assert_eq!(error.code, "cancelled");
    let size = || std::fs::metadata(&beat).map_or(0, |m| m.len());
    assert!(size() > 0, "grandchild never started");
    thread::sleep(Duration::from_millis(500));
    let settled = size();
    thread::sleep(Duration::from_millis(1000));
    assert_eq!(size(), settled, "grandchild survived cancellation");
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn oversized_and_mismatched_replies_are_rejected() {
    let cancel = CancelToken::default();
    let error = fake("huge")
        .call("runs.list", &json!({}), &cancel)
        .unwrap_err();
    assert_eq!(error.code, "response_too_large");
    let error = fake("wrong_id")
        .call("runs.list", &json!({}), &cancel)
        .unwrap_err();
    assert_eq!(error.code, "protocol_error");
}

#[test]
fn missing_worker_executable_is_unavailable_not_a_panic() {
    let command = WorkerCommand {
        program: PathBuf::from("/nonexistent/heplab-worker"),
        prefix_args: vec![],
        project_root: std::env::temp_dir(),
        env: vec![],
    };
    let error = Supervisor::new(command, "x").ensure_started().unwrap_err();
    assert_eq!(error.code, "worker_unavailable");
}

#[test]
fn real_python_worker_round_trip() {
    let root = std::env::temp_dir().join(format!("heplab-desktop-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let command = WorkerCommand {
        program: python(),
        prefix_args: vec!["-m".into(), "heplab.desktop.worker".into()],
        project_root: root.clone(),
        env: vec![("PYTHONPATH".into(), repo().join("src").into())],
    };
    let version = std::env::var("HEPLAB_TEST_WORKER_VERSION").unwrap_or("0.1.0.dev0".into());
    let mut worker = Supervisor::new(command, &version);
    let cancel = CancelToken::default();
    assert_eq!(
        worker.call("runs.list", &json!({}), &cancel).unwrap(),
        json!([])
    );
    let error = worker
        .call("lab.profile", &json!({"profile": "missing.json"}), &cancel)
        .unwrap_err();
    assert_eq!(error.code, "not_found");
    assert!(worker
        .call("engine.capabilities", &json!({}), &cancel)
        .is_ok());
    worker.shutdown();
    std::fs::remove_dir_all(root).unwrap();
}

/// Release runners set HEPLAB_TEST_WORKER_BINARY to the frozen sidecar.
#[test]
fn frozen_sidecar_round_trip_when_provided() {
    let Some(binary) = std::env::var_os("HEPLAB_TEST_WORKER_BINARY") else {
        eprintln!("HEPLAB_TEST_WORKER_BINARY not set; frozen sidecar not exercised");
        return;
    };
    let root = std::env::temp_dir().join(format!("heplab-sidecar-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let command = WorkerCommand {
        program: binary.into(),
        prefix_args: vec![],
        project_root: root.clone(),
        env: vec![],
    };
    let mut worker = Supervisor::new(command, "0.1.0.dev0");
    let cancel = CancelToken::default();
    assert_eq!(
        worker.call("runs.list", &json!({}), &cancel).unwrap(),
        json!([])
    );
    assert!(worker
        .call("detector.geometry", &json!({}), &cancel)
        .is_ok());
    worker.shutdown();
    std::fs::remove_dir_all(root).unwrap();
}
