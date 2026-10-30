//! Launch, handshake, call, cancel and restart one packaged worker.
//!
//! The worker is started from an explicit executable path and a fixed
//! argument vector, never through a shell. Requests are multiplexed: each call
//! waits only for its own reply (matched by id), so a slow operation never
//! blocks a quick one. Cancelling or timing out a call abandons that call
//! alone; the worker, and every simulation job it owns, keeps running. The
//! worker is restarted only when it crashes, breaks the protocol, or has more
//! abandoned requests outstanding than it has request threads (it is wedged).

use crate::protocol::{encode_request, spec, validate, IpcError};
use crate::tree::ProcessTree;
use serde_json::Value;
use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

const STDERR_LINES: usize = 64;
const POLL: Duration = Duration::from_millis(50);
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

/// Fixed launch description. `prefix_args` exists for development launches
/// such as `python -m heplab.desktop.worker`; release builds pass none.
#[derive(Debug, Clone)]
pub struct WorkerCommand {
    pub program: PathBuf,
    pub prefix_args: Vec<OsString>,
    pub project_root: PathBuf,
    pub env: Vec<(OsString, OsString)>,
}

/// Flag another thread can set to cancel one call (or a group of calls).
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

/// What the router delivers to a waiting call.
enum Outcome {
    Reply(Value),
    Fatal(IpcError),
}

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    // A panicked holder cannot leave these maps logically inconsistent.
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

struct Running {
    child: Mutex<Child>,
    tree: Mutex<ProcessTree>,
    stdin: Mutex<Option<ChildStdin>>,
    stderr: Arc<Mutex<VecDeque<String>>>,
    pending: Mutex<HashMap<u64, Sender<Outcome>>>,
    abandoned: Mutex<HashSet<u64>>,
    dead: AtomicBool,
}

impl Running {
    fn alive(&self) -> bool {
        !self.dead.load(Ordering::SeqCst) && matches!(lock(&self.child).try_wait(), Ok(None))
    }

    fn crash_report(&self) -> String {
        let status = lock(&self.child)
            .try_wait()
            .ok()
            .flatten()
            .map_or("running".to_owned(), |s| s.to_string());
        let tail: Vec<String> = lock(&self.stderr).iter().cloned().collect();
        format!("worker status {status}; stderr tail: {}", tail.join(" | "))
    }

    /// Kill the process tree and fail every waiting call with `error`.
    fn fail(&self, error: &IpcError) {
        if self.dead.swap(true, Ordering::SeqCst) {
            return;
        }
        lock(&self.tree).kill(&mut lock(&self.child));
        for (_, waiter) in lock(&self.pending).drain() {
            let _ = waiter.send(Outcome::Fatal(error.clone()));
        }
    }

    /// Route replies by id until the stream ends or breaks the protocol.
    fn route(&self, lines: Receiver<Line>) {
        for line in lines {
            let text = match line {
                Line::Text(text) => text,
                Line::TooLong => {
                    return self.fail(&IpcError::new(
                        "response_too_large",
                        "worker reply exceeds IPC budget",
                    ))
                }
            };
            let reply: Option<Value> = serde_json::from_str(&text).ok();
            let id = reply
                .as_ref()
                .and_then(|r| r.get("id"))
                .and_then(Value::as_u64);
            let (Some(reply), Some(id)) = (reply, id) else {
                return self.fail(&IpcError::new(
                    "protocol_error",
                    "reply does not match the request",
                ));
            };
            // Lock order pending → abandoned, as in `Supervisor::abandon`, so a
            // reply racing an abandonment is always found in one of the two.
            let known = {
                let mut pending = lock(&self.pending);
                match pending.remove(&id) {
                    Some(waiter) => {
                        let _ = waiter.send(Outcome::Reply(reply));
                        true
                    }
                    None => lock(&self.abandoned).remove(&id),
                }
            };
            if !known {
                return self.fail(&IpcError::new(
                    "protocol_error",
                    "reply does not match the request",
                ));
            }
        }
        // EOF: give the stderr drain a moment so the report carries the cause.
        thread::sleep(Duration::from_millis(100));
        let report = self.crash_report();
        self.fail(&IpcError::new("worker_crashed", report));
    }
}

pub struct Supervisor {
    command: WorkerCommand,
    expected_version: String,
    running: Mutex<Option<Arc<Running>>>,
    next_id: AtomicU64,
    restarts: AtomicU32,
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
            running: Mutex::new(None),
            next_id: AtomicU64::new(0),
            restarts: AtomicU32::new(0),
        }
    }

    /// Times the worker was replaced after a crash, protocol error or wedge.
    pub fn restarts(&self) -> u32 {
        self.restarts.load(Ordering::SeqCst)
    }

    /// Start the worker if needed and verify its protocol, version and operations.
    pub fn ensure_started(&self) -> Result<(), IpcError> {
        self.running().map(|_| ())
    }

    fn running(&self) -> Result<Arc<Running>, IpcError> {
        let mut slot = lock(&self.running);
        if let Some(running) = slot.as_ref() {
            if running.alive() {
                return Ok(Arc::clone(running));
            }
            slot.take();
            self.restarts.fetch_add(1, Ordering::SeqCst);
        }
        let running = self.launch()?;
        *slot = Some(Arc::clone(&running));
        Ok(running)
    }

    fn launch(&self) -> Result<Arc<Running>, IpcError> {
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
            // Read raw bytes: a non-UTF-8 line (e.g. a cp1252 path in a traceback)
            // must not end the drain, or the worker would block on a full pipe.
            let mut reader = BufReader::new(stderr_pipe);
            let mut buffer = Vec::new();
            while matches!(reader.read_until(b'\n', &mut buffer), Ok(n) if n > 0) {
                let line = String::from_utf8_lossy(&buffer)
                    .trim_end_matches(['\r', '\n'])
                    .to_owned();
                buffer.clear();
                let mut tail = lock(&tail);
                if tail.len() == STDERR_LINES {
                    tail.pop_front();
                }
                tail.push_back(line.chars().take(1000).collect());
            }
        });
        let running = Arc::new(Running {
            child: Mutex::new(child),
            tree: Mutex::new(tree),
            stdin: Mutex::new(Some(stdin)),
            stderr,
            pending: Mutex::new(HashMap::new()),
            abandoned: Mutex::new(HashSet::new()),
            dead: AtomicBool::new(false),
        });
        let timeout = Duration::from_secs(spec().handshake_timeout_s);
        let hello = match lines.recv_timeout(timeout) {
            Ok(Line::Text(text)) => serde_json::from_str::<Value>(&text).ok(),
            _ => None,
        };
        if let Err(message) = self.check_hello(hello.as_ref()) {
            let report = running.crash_report();
            running.fail(&IpcError::new("handshake_failed", message.clone()));
            return Err(IpcError::new(
                "handshake_failed",
                format!("{message}; {report}"),
            ));
        }
        let router = Arc::clone(&running);
        thread::spawn(move || router.route(lines));
        Ok(running)
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

    /// Stop waiting for `id`; its late reply is discarded. A worker with more
    /// abandoned requests than request threads can serve nothing else, so it
    /// is restarted.
    fn abandon(&self, running: &Running, id: u64) {
        let outstanding = {
            let mut pending = lock(&running.pending);
            if pending.remove(&id).is_none() {
                return; // the reply (or a fatal error) won the race
            }
            let mut abandoned = lock(&running.abandoned);
            abandoned.insert(id);
            abandoned.len()
        };
        if outstanding > spec().max_concurrent_requests {
            running.fail(&IpcError::new(
                "worker_restarted",
                "worker stopped answering and was restarted",
            ));
        }
    }

    /// Validate, send and await one request. Safe to call from many threads.
    pub fn call(&self, op: &str, args: &Value, cancel: &CancelToken) -> Result<Value, IpcError> {
        let operation = validate(op, args)?;
        let running = self.running()?;
        let id = self.next_id.fetch_add(1, Ordering::SeqCst) + 1;
        let line = encode_request(id, op, args)?;
        let (sender, outcome) = mpsc::channel();
        lock(&running.pending).insert(id, sender);
        let written = match lock(&running.stdin).as_mut() {
            Some(stdin) => writeln!(stdin, "{line}").and_then(|_| stdin.flush()),
            None => Err(std::io::ErrorKind::BrokenPipe.into()),
        };
        if written.is_err() {
            let error = IpcError::new("worker_crashed", running.crash_report());
            running.fail(&error);
            return Err(error);
        }
        let deadline = Instant::now() + Duration::from_secs(operation.timeout_s);
        loop {
            match outcome.recv_timeout(POLL) {
                Ok(Outcome::Reply(reply)) => return interpret(&reply),
                Ok(Outcome::Fatal(error)) => return Err(error),
                Err(RecvTimeoutError::Disconnected) => {
                    return Err(IpcError::new("worker_crashed", running.crash_report()))
                }
                Err(RecvTimeoutError::Timeout) => {}
            }
            if cancel.take() {
                self.abandon(&running, id);
                return Err(IpcError::new("cancelled", "request cancelled"));
            }
            if Instant::now() >= deadline {
                self.abandon(&running, id);
                return Err(IpcError::new(
                    "timeout",
                    format!("{op} exceeded {}s", operation.timeout_s),
                ));
            }
        }
    }

    /// Stop the worker and its process tree; the next call starts a fresh one.
    ///
    /// Closing stdin first lets the worker park its running jobs as queued (so
    /// they resume at next launch without spending a retry); the tree is
    /// killed if it has not exited within `SHUTDOWN_GRACE`.
    pub fn shutdown(&self) {
        let running = lock(&self.running).take();
        if let Some(running) = running {
            lock(&running.stdin).take();
            let deadline = Instant::now() + SHUTDOWN_GRACE;
            while Instant::now() < deadline && matches!(lock(&running.child).try_wait(), Ok(None)) {
                thread::sleep(POLL);
            }
            running.fail(&IpcError::new("worker_unavailable", "worker shut down"));
        }
    }
}

fn interpret(reply: &Value) -> Result<Value, IpcError> {
    match reply.get("ok").and_then(Value::as_bool) {
        Some(true) => Ok(reply.get("result").cloned().unwrap_or(Value::Null)),
        Some(false) => Err(reply
            .get("error")
            .and_then(|e| serde_json::from_value::<IpcError>(e.clone()).ok())
            .unwrap_or_else(|| IpcError::new("protocol_error", "malformed worker error"))),
        None => Err(IpcError::new("protocol_error", "reply has no ok flag")),
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
