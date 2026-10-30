---
title: Python API v1
description: A small, reproducible Python workflow from local events to a shareable result.
---

import { Aside, LinkCard } from '@astrojs/starlight/components'

## From events to a result

The Python API is the same analysis path used by the guided lab. Start with a local event file, inspect the deterministic provenance, then fit and share the result.

```python
import heplab

events = heplab.read("events.json", simulation=True)
result = heplab.run(
    events,
    analysis="dimuon",
    config={
        "selection": {
            "muons": {"min_pt": 20, "max_rel_iso": 0.15},
            "pairs": {"require_opposite_charge": True},
        },
    },
)

print(result["provenance"]["input_events_sha256"])
fit = heplab.fit_peak(result)  # requires heplab[analysis]
heplab.export_html(result, "z-result.html", title="My Z measurement")
```

<code>run</code> consumes the event iterable once. It adds the event count and SHA-256, config SHA-256, API/package versions, and source or certification identifiers carried by the input. Its result digest is stable for identical inputs and configuration.

<Aside type="caution" title="Local input and current scope">
  <code>read</code> handles local JSON event lists and ROOT files. JSON and ROOT input are returned eagerly as lists. The public <code>run</code> API currently supports <code>dimuon</code>; it does not fetch data, publish results, or manage background jobs.
</Aside>

## Load a published result

Use <code>load</code> when reopening a JSON artifact produced by the CLI. It verifies the deterministic result or payload digest when one is present.

```python
artifact = heplab.load("artifacts/dimuon-result.json")
heplab.export_html(artifact, "reopened-result.html", include_raw=True)
```

The HTML export is one file and works offline. Candidate arrays are omitted unless <code>include_raw=True</code> is requested.

## Contract and functions

<code>heplab.API_VERSION</code> is <code>"1"</code> and evolves independently from the package release. A breaking change to public function signatures or normalized event/result contracts requires a new API version.

| Entry point | What it does |
| --- | --- |
| <code>heplab.read(path, simulation=False, max_events=None, format="nanoaod")</code> | Read local JSON or ROOT events. |
| <code>heplab.run(events, analysis="dimuon", config=None)</code> | Analyze an iterable of finite JSON-compatible event records and attach provenance. |
| <code>heplab.fit_peak(result, window=(70, 110))</code> | Fit candidate masses; requires <code>heplab[analysis]</code>. |
| <code>heplab.export_html(result_or_path, output, title=None, include_raw=False)</code> | Write a self-contained result page. |
| <code>heplab.load(path)</code> | Load a published result and verify its digest. |
| <code>heplab.notebook.show(result)</code> | Show a result in Jupyter; install <code>heplab[notebook]</code> for widgets. |

<LinkCard title="Try the interactive Z lab" href="/education/" description="Use the same dimuon workflow with guided checkpoints and immediate feedback." />
