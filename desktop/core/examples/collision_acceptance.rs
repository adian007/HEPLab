//! Opt-in real-runtime acceptance using the desktop's actual process supervisor.
use heplab_desktop_core::{CancelToken, Supervisor, WorkerCommand};
use serde_json::json;
use std::path::PathBuf;
use std::thread::sleep;
use std::time::{Duration, Instant};

fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    assert_eq!(args.len(), 2, "usage: collision_acceptance WORKER PROJECT");
    let root = PathBuf::from(&args[1]);
    std::fs::create_dir_all(&root).unwrap();
    let command = WorkerCommand {
        program: PathBuf::from(&args[0]),
        prefix_args: vec![],
        project_root: root.clone(),
        env: vec![],
    };
    let worker = Supervisor::new(command, "0.1.0.dev0");
    let cancel = CancelToken::default();
    let session = worker
        .call("workbench.session", &json!({}), &cancel)
        .unwrap();
    assert_eq!(session["simulation"]["available"], true, "{session}");
    let submitted = worker
        .call(
            "jobs.submit",
            &json!({"config": {
                "mode":"pythia", "backend":"delphes", "events":100, "seed":42
            }}),
            &cancel,
        )
        .unwrap();
    let id = &submitted["id"];
    let started = Instant::now();
    let mut phase = String::new();
    let result = loop {
        assert!(started.elapsed() < Duration::from_secs(180));
        let job = worker
            .call("jobs.get", &json!({"job_id":id}), &cancel)
            .unwrap();
        let current = format!("{} {}", job["status"], job["phase"]);
        if phase != current {
            eprintln!("{current}");
            phase = current;
        }
        match job["status"].as_str().unwrap() {
            "completed" => break job["result"].clone(),
            "running" | "queued" => sleep(Duration::from_millis(250)),
            _ => panic!("{job}"),
        }
    };
    let selected = result["analysis"]["event_rows"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["selected"] == true)
        .unwrap()["event"]
        .clone();
    let event = worker
        .call(
            "jobs.event",
            &json!({"job_id":id,"index":selected}),
            &cancel,
        )
        .unwrap();
    assert_eq!(event["event_info"]["selected"], true);
    worker.shutdown();
    assert_eq!(
        worker
            .call("jobs.get", &json!({"job_id":id}), &cancel)
            .unwrap()["result"],
        result
    );
    worker.shutdown();
    let report = json!({"status":"passed","run_id":id,"summary":result["summary"],
        "selected_events":result["analysis"]["selected_events"],"selected_event":selected,
        "supervised_process_tree":true,"restart_reopened":true});
    std::fs::write(
        root.join("supervisor-acceptance.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    println!("{report}");
}
