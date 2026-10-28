//! Launch, handshake, call, cancel and restart one packaged worker.
//!
//! The worker is started from an explicit executable path and a fixed
//! argument vector, never through a shell. Cancellation and timeouts terminate
//! the worker; the next call restarts it and repeats the version handshake.

use crate::protocol::{encode_request, spec, validate, IpcError};
use crate::tree::ProcessTree;
use serde_json::Value;
use std::collections::{BTreeSet, VecDeque};
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

const STDERR_LINES: usize = 64;
const POLL: Duration = Duration::from_millis(50);

/// Fixed launch description. `prefix_args` exists for development launches
/// such as `python -m heplab.desktop.worker`; release builds pass none.
#[derive(Debug, Clone)]
pub struct WorkerCommand {
    pub program: PathBuf,
    pub prefix_args: Vec<OsString>,
    pub project_root: PathBuf,
    pub env: Vec<(OsString, OsString)>,
}

/// Shared flag a second command can set to cancel the call in progress.
#[derive(Debug, Clone, Default)]
pub struct CancelToken(Arc<AtomicBool>);

impl CancelToken {
    pub fn cancel(&self) {
        self.0.store(true, Ordering::SeqCst);
    }
    fn take(&self) -> bool {
        self.0.swap(false, Ordering::SeqCst)
    }
}

enum Line {
    Text(String),
    TooLong,
}

struct Running {
    child: Child,
    tree: ProcessTree,
    stdin: ChildStdin,
    lines: Receiver<Line>,
    stderr: Arc<Mutex<VecDeque<String>>>,
}

impl Running {
    fn stop(&mut self) {
        self.tree.kill(&mut self.child);
    }

    fn crash_report(&mut self) -> String {
        let status = self
            .child
            .try_wait()
            .ok()
            .flatten()
            .map_or("running".to_owned(), |s| s.to_string());
        let tail: Vec<String> = self
            .stderr
            .lock()
            .map(|l| l.iter().cloned().collect())
            .unwrap_or_default();
        format!("worker status {status}; stderr tail: {}", tail.join(" | "))
    }
}

pub struct Supervisor {
    command: WorkerCommand,
    expected_version: String,
    running: Option<Running>,
    next_id: u64,
    pub restarts: u32,
}

/// Read one newline-terminated line of at most `limit` bytes; drain longer ones.
fn read_bounded(reader: &mut impl BufRead, limit: usize) -> std::io::Result<Option<Line>> {
    let mut buffer = Vec::new();
    let mut overflow = false;
    loop {
        let chunk = reader.fill_buf()?;
        if chunk.is_empty() {
            return Ok(None);
        }
        let (take, done) = match chunk.iter().position(|b| *b == b'\n') {
            Some(i) => (i + 1, true),
            None => (chunk.len(), false),
        };
        if !overflow {
            buffer.extend_from_slice(&chunk[..take]);
            if buffer.len() > limit + 1 {
                overflow = true;
                buffer.clear();
            }
        }
        reader.consume(take);
        if done {
            if overflow {
                return Ok(Some(Line::TooLong));
            }
            buffer.pop();
            return Ok(Some(match String::from_utf8(buffer) {
                Ok(text) => Line::Text(text),
                Err(_) => Line::TooLong,
            }));
        }
    }
}

impl Supervisor {
    pub fn new(command: WorkerCommand, expected_version: &str) -> Self {
        Self {
            command,
            expected_version: expected_version.to_owned(),
            running: None,
            next_id: 0,
            restarts: 0,
        }
    }

    /// Start the worker if needed and verify its protocol, version and operations.
    pub fn ensure_started(&mut self) -> Result<(), IpcError> {
        if let Some(running) = self.running.as_mut() {
            if matches!(running.child.try_wait(), Ok(None)) {
                return Ok(());
            }
            self.running = None;
            self.restarts += 1;
        }
        let command = &self.command;
        let mut process = Command::new(&command.program);
        process
            .args(&command.prefix_args)
            .arg("--project-root")
            .arg(&command.project_root)
            .envs(command.env.iter().map(|(k, v)| (k, v)))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        ProcessTree::prepare(&mut process);
        let mut child = process.spawn().map_err(|e| {
            IpcError::new("worker_unavailable", format!("cannot launch worker: {e}"))
        })?;
        let tree = match ProcessTree::attach(&child) {
            Ok(tree) => tree,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(IpcError::new(
                    "worker_unavailable",
                    format!("cannot contain worker process tree: {e}"),
                ));
            }
        };
        let stdin = child.stdin.take().expect("piped stdin");
        let stdout = child.stdout.take().expect("piped stdout");
        let stderr_pipe = child.stderr.take().expect("piped stderr");
        let (sender, lines) = mpsc::channel();
        let limit = spec().max_response_bytes;
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            while let Ok(Some(line)) = read_bounded(&mut reader, limit) {
                if sender.send(line).is_err() {
                    break;
                }
            }
        });
        let stderr = Arc::new(Mutex::new(VecDeque::with_capacity(STDERR_LINES)));
        let tail = Arc::clone(&stderr);
        thread::spawn(move || {
            for line in BufReader::new(stderr_pipe).lines().map_while(Result::ok) {
                if let Ok(mut tail) = tail.lock() {
                    if tail.len() == STDERR_LINES {
                        tail.pop_front();
                    }
                    tail.push_back(line.chars().take(1000).collect());
                }
            }
        });
        let mut running = Running {
            child,
            tree,
            stdin,
            lines,
            stderr,
        };
        let timeout = Duration::from_secs(spec().handshake_timeout_s);
        let hello = match running.lines.recv_timeout(timeout) {
            Ok(Line::Text(text)) => serde_json::from_str::<Value>(&text).ok(),
            _ => None,
        };
        if let Err(message) = self.check_hello(hello.as_ref()) {
            let report = running.crash_report();
            running.stop();
            return Err(IpcError::new(
                "handshake_failed",
                format!("{message}; {report}"),
            ));
        }
        self.running = Some(running);
        Ok(())
    }

    fn check_hello(&self, hello: Option<&Value>) -> Result<(), String> {
        let hello = hello.ok_or("no valid handshake line")?;
        let protocol = hello.get("protocol").and_then(Value::as_str);
        if protocol != Some(spec().protocol.as_str()) {
            return Err(format!("protocol {protocol:?} is not {}", spec().protocol));
        }
        let version = hello.get("worker_version").and_then(Value::as_str);
        if version != Some(self.expected_version.as_str()) {
            return Err(format!(
                "worker version {version:?} is not {}",
                self.expected_version
            ));
        }
        let offered: Option<BTreeSet<&str>> = hello
            .get("operations")
            .and_then(Value::as_array)
            .map(|ops| ops.iter().filter_map(Value::as_str).collect());
        let expected: BTreeSet<&str> = spec().operations.keys().map(String::as_str).collect();
        if offered.as_ref() != Some(&expected) {
            return Err("worker operations differ from the shell's table".to_owned());
        }
        Ok(())
    }

    fn abandon(&mut self) -> String {
        match self.running.take() {
            Some(mut running) => {
                let report = running.crash_report();
                running.stop();
                self.restarts += 1;
                report
            }
            None => String::new(),
        }
    }

    /// Validate, send and await one request. Errors never leave a half-read stream.
    pub fn call(
        &mut self,
        op: &str,
        args: &Value,
        cancel: &CancelToken,
    ) -> Result<Value, IpcError> {
        let operation = validate(op, args)?;
        cancel.take();
        self.ensure_started()?;
        self.next_id += 1;
        let id = self.next_id;
        let line = encode_request(id, op, args)?;
        let running = self.running.as_mut().expect("worker started");
        if writeln!(running.stdin, "{line}")
            .and_then(|_| running.stdin.flush())
            .is_err()
        {
            let report = self.abandon();
            return Err(IpcError::new("worker_crashed", report));
        }
        let deadline = Instant::now() + Duration::from_secs(operation.timeout_s);
        loop {
            if cancel.take() {
                self.abandon();
                return Err(IpcError::new(
                    "cancelled",
                    "request cancelled; worker restarted",
                ));
            }
            if Instant::now() >= deadline {
                self.abandon();
                return Err(IpcError::new(
                    "timeout",
                    format!("{op} exceeded {}s", operation.timeout_s),
                ));
            }
            let running = self.running.as_mut().expect("worker started");
            match running.lines.recv_timeout(POLL) {
                Err(RecvTimeoutError::Timeout) => continue,
                Err(RecvTimeoutError::Disconnected) => {
                    let report = self.abandon();
                    return Err(IpcError::new("worker_crashed", report));
                }
                Ok(Line::TooLong) => {
                    self.abandon();
                    return Err(IpcError::new(
                        "response_too_large",
                        "worker reply exceeds IPC budget",
                    ));
                }
                Ok(Line::Text(text)) => return self.reply(id, &text),
            }
        }
    }

    fn reply(&mut self, id: u64, text: &str) -> Result<Value, IpcError> {
        let parsed: Option<Value> = serde_json::from_str(text).ok();
        let Some(reply) = parsed.filter(|v| v.get("id").and_then(Value::as_u64) == Some(id)) else {
            self.abandon();
            return Err(IpcError::new(
                "protocol_error",
                "reply does not match the request",
            ));
        };
        match reply.get("ok").and_then(Value::as_bool) {
            Some(true) => Ok(reply.get("result").cloned().unwrap_or(Value::Null)),
            Some(false) => Err(reply
                .get("error")
                .and_then(|e| serde_json::from_value::<IpcError>(e.clone()).ok())
                .unwrap_or_else(|| IpcError::new("protocol_error", "malformed worker error"))),
            None => {
                self.abandon();
                Err(IpcError::new("protocol_error", "reply has no ok flag"))
            }
        }
    }

    pub fn shutdown(&mut self) {
        if let Some(mut running) = self.running.take() {
            running.stop();
        }
    }
}

impl Drop for Supervisor {
    fn drop(&mut self) {
        self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn bounded_reader_drains_long_lines_and_keeps_framing() {
        let data = format!("short\n{}\nnext\n", "x".repeat(100));
        let mut reader = Cursor::new(data.into_bytes());
        assert!(
            matches!(read_bounded(&mut reader, 10).unwrap(), Some(Line::Text(t)) if t == "short")
        );
        assert!(matches!(
            read_bounded(&mut reader, 10).unwrap(),
            Some(Line::TooLong)
        ));
        assert!(
            matches!(read_bounded(&mut reader, 10).unwrap(), Some(Line::Text(t)) if t == "next")
        );
        assert!(read_bounded(&mut reader, 10).unwrap().is_none());
    }
}
