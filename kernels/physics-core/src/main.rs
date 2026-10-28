//! Bounded JSON-lines bridge to the pure Rust physics library.
use serde_json::json;
use std::io::{self, BufRead, Read, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let stdin = io::stdin();
    let mut reader = stdin.lock();
    let mut writer = io::BufWriter::new(io::stdout().lock());
    loop {
        let mut line = Vec::new();
        // A fixed input ceiling avoids unbounded allocation on malformed lines.
        let count = reader
            .by_ref()
            .take(1_048_577)
            .read_until(b'\n', &mut line)?;
        if count == 0 {
            break;
        }
        if line.len() > 1_048_576 {
            return Err("JSON request exceeds 1 MiB".into());
        }
        let answer = match std::str::from_utf8(&line) {
            Ok(text) => match heplab_physics::protocol::execute_json(text) {
                Ok(value) => json!({"ok":true,"result":value}),
                Err(error) => json!({"ok":false,"error":error.to_string()}),
            },
            Err(error) => json!({"ok":false,"error":error.to_string()}),
        };
        writeln!(writer, "{answer}")?;
        writer.flush()?;
    }
    Ok(())
}
