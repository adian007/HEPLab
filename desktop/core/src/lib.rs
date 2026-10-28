//! Desktop IPC boundary for HEPLab (M7).
//!
//! The webview may only name an operation from `operations.json` with
//! arguments that pass these checks; the packaged worker re-checks them and
//! confines paths to its project root. No request is ever turned into a shell
//! command line.

pub mod protocol;
pub mod supervisor;
mod tree;

pub use protocol::{spec, validate, IpcError, Spec};
pub use supervisor::{CancelToken, Supervisor, WorkerCommand};
