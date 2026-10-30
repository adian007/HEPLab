//! HEPLab desktop shell. The webview reaches physics and data only through
//! `heplab_invoke`, which validates against the shared operation table and
//! forwards to the bundled worker; there is no shell plugin and no network API.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use heplab_desktop_core::{CancelToken, IpcError, Supervisor, WorkerCommand};
use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tauri::Manager;

/// PEP 440 spelling of the worker package version this shell was built with.
const EXPECTED_WORKER_VERSION: &str = "0.1.0.dev0";

/// The supervisor multiplexes calls itself, so there is no shell-wide lock: a
/// slow operation never queues the UI's job polls behind it.
struct Shell {
    worker: Arc<Supervisor>,
    in_flight: Arc<Mutex<HashMap<u64, CancelToken>>>,
    next_call: AtomicU64,
}

impl Shell {
    /// Abandon every waiting call. The worker and its simulation jobs keep running.
    fn cancel_all(&self) {
        let calls = self.in_flight.lock().unwrap_or_else(|p| p.into_inner());
        for token in calls.values() {
            token.cancel();
        }
    }
}

/// The one-dir frozen worker ships as the `worker/` bundle resource.
fn packaged_worker(resources: &std::path::Path) -> Result<WorkerCommand, String> {
    Ok(WorkerCommand {
        program: resources
            .join("worker")
            .join(format!("heplab-worker{}", std::env::consts::EXE_SUFFIX)),
        prefix_args: vec![],
        project_root: PathBuf::new(),
        env: vec![],
    })
}

/// Debug builds only: `HEPLAB_DEV_PYTHON` runs the worker from the source tree.
fn worker_command(resources: &std::path::Path) -> Result<WorkerCommand, String> {
    #[cfg(debug_assertions)]
    if let Some(python) = std::env::var_os("HEPLAB_DEV_PYTHON") {
        return Ok(WorkerCommand {
            program: python.into(),
            prefix_args: vec!["-m".into(), "heplab.desktop.worker".into()],
            project_root: PathBuf::new(),
            env: vec![],
        });
    }
    packaged_worker(resources)
}

#[tauri::command]
async fn heplab_invoke(
    state: tauri::State<'_, Shell>,
    op: String,
    args: Value,
) -> Result<Value, IpcError> {
    let worker = Arc::clone(&state.worker);
    let in_flight = Arc::clone(&state.in_flight);
    let call = state.next_call.fetch_add(1, Ordering::SeqCst);
    let cancel = CancelToken::default();
    in_flight
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .insert(call, cancel.clone());
    let outcome = tauri::async_runtime::spawn_blocking(move || worker.call(&op, &args, &cancel))
        .await
        .map_err(|e| IpcError::new("worker_unavailable", e.to_string()));
    in_flight
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .remove(&call);
    outcome?
}

#[tauri::command]
fn heplab_cancel(state: tauri::State<'_, Shell>) {
    state.cancel_all();
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            // Apply the same bundled mark to the native title bar and taskbar.
            // Bundle metadata alone may not update the live window icon.
            let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/128x128.png"))?;
            app.get_webview_window("main")
                .expect("main window is configured")
                .set_icon(icon)?;
            let root = app.path().app_data_dir()?.join("projects").join("default");
            std::fs::create_dir_all(root.join("artifacts"))?;
            let mut command = worker_command(&app.path().resource_dir()?)?;
            command.project_root = root;
            app.manage(Shell {
                worker: Arc::new(Supervisor::new(command, EXPECTED_WORKER_VERSION)),
                in_flight: Arc::default(),
                next_call: AtomicU64::new(0),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![heplab_invoke, heplab_cancel])
        .build(tauri::generate_context!())
        .expect("failed to build the HEPLab desktop shell");
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(shell) = handle.try_state::<Shell>() {
                // Release waiting calls, then stop the worker tree. Queued and
                // running simulation jobs are durable and resume at next launch.
                shell.cancel_all();
                shell.worker.shutdown();
            }
        }
    });
}
