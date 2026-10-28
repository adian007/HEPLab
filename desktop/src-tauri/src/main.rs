//! HEPLab desktop shell. The webview reaches physics and data only through
//! `heplab_invoke`, which validates against the shared operation table and
//! forwards to the bundled worker; there is no shell plugin and no network API.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use heplab_desktop_core::{CancelToken, IpcError, Supervisor, WorkerCommand};
use serde_json::Value;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::Manager;

/// PEP 440 spelling of the worker package version this shell was built with.
const EXPECTED_WORKER_VERSION: &str = "0.1.0.dev0";

struct Shell {
    worker: Arc<Mutex<Supervisor>>,
    cancel: CancelToken,
}

/// Tauri installs `externalBin` sidecars next to the main executable.
fn packaged_worker() -> Result<WorkerCommand, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().ok_or("executable has no directory")?;
    Ok(WorkerCommand {
        program: dir.join(format!("heplab-worker{}", std::env::consts::EXE_SUFFIX)),
        prefix_args: vec![],
        project_root: PathBuf::new(),
        env: vec![],
    })
}

/// Debug builds only: `HEPLAB_DEV_PYTHON` runs the worker from the source tree.
fn worker_command() -> Result<WorkerCommand, String> {
    #[cfg(debug_assertions)]
    if let Some(python) = std::env::var_os("HEPLAB_DEV_PYTHON") {
        return Ok(WorkerCommand {
            program: python.into(),
            prefix_args: vec!["-m".into(), "heplab.desktop.worker".into()],
            project_root: PathBuf::new(),
            env: vec![],
        });
    }
    packaged_worker()
}

#[tauri::command]
async fn heplab_invoke(
    state: tauri::State<'_, Shell>,
    op: String,
    args: Value,
) -> Result<Value, IpcError> {
    let worker = Arc::clone(&state.worker);
    let cancel = state.cancel.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut worker = worker
            .lock()
            .map_err(|_| IpcError::new("worker_unavailable", "worker lock poisoned"))?;
        worker.call(&op, &args, &cancel)
    })
    .await
    .map_err(|e| IpcError::new("worker_unavailable", e.to_string()))?
}

#[tauri::command]
fn heplab_cancel(state: tauri::State<'_, Shell>) {
    state.cancel.cancel();
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let root = app.path().app_data_dir()?.join("projects").join("default");
            std::fs::create_dir_all(root.join("artifacts"))?;
            let mut command = worker_command()?;
            command.project_root = root;
            app.manage(Shell {
                worker: Arc::new(Mutex::new(Supervisor::new(
                    command,
                    EXPECTED_WORKER_VERSION,
                ))),
                cancel: CancelToken::default(),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![heplab_invoke, heplab_cancel])
        .build(tauri::generate_context!())
        .expect("failed to build the HEPLab desktop shell");
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(shell) = handle.try_state::<Shell>() {
                // Stop any in-flight call, then wait briefly for the lock. Exit
                // must never hang on a busy worker: if the lock stays held, the
                // kill-on-close job ends the worker tree when this process exits.
                shell.cancel.cancel();
                let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
                loop {
                    match shell.worker.try_lock() {
                        Ok(mut worker) => break worker.shutdown(),
                        Err(std::sync::TryLockError::Poisoned(poisoned)) => {
                            break poisoned.into_inner().shutdown()
                        }
                        Err(std::sync::TryLockError::WouldBlock)
                            if std::time::Instant::now() < deadline =>
                        {
                            std::thread::sleep(std::time::Duration::from_millis(20))
                        }
                        Err(std::sync::TryLockError::WouldBlock) => break,
                    }
                }
            }
        }
    });
}
