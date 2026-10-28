# Product and information architecture

## Purpose

Make HEPLab understandable and useful to people evaluating the open-source
project, learners, and contributors. The public website summarizes the project's
scope, architecture, evidence, roadmap and documentation. The simulator itself
runs locally; a dedicated desktop app is planned. This site does not execute
simulations or inspect local results.

## Product principles

1. State the evidence and limitations alongside every simulation claim.
2. Teach through inspectable inputs, events, units and provenance.
3. Keep project discovery useful without requiring installation or an account.
4. Make local data ownership and offline capability clear.
5. Keep documentation authoritative: link to the engineering handbook rather
   than creating a second, divergent physics specification.

## Sitemap

```text
/
├── Project       purpose, capabilities, status, citations
├── Simulator     launch/install instructions and browser workbench entry
├── Learn         guided concepts, example workflows, event-display explainer
├── Documentation quickstart, architecture, API, handbook, FAQ
├── Community     contribution guide, issue tracker, governance, license
└── Releases      version notes, supported platforms, runtime requirements
```

The browser workbench is an installed/local application served by the local
HEPLab process. A hosted project landing page must not imply that it can execute
the user's simulation or access local artifacts.

## Page content requirements

### Project home

- Clear one-sentence description: reproducible LHC analysis and simulation on
  CERN Open Data, with custom and reference simulation paths.
- Status panel: early implementation, supported capabilities, limitations and
  links to evidence. Distinguish numerical smoke tests from physics validation.
- Primary calls to action: try the local simulator, read the quickstart, explore
  the source/contribution guide.
- Small architecture overview, project license and upstream attribution.

### Simulator

- Explain local prerequisites and provide platform-specific installation/run
  steps grounded in `docs/engineering/sim-runtime.md`.
- Explain reference bench vs PYTHIA8/DELPHES runtime and their fidelity limits.
- Explain data stays in the user's configured local directories.
- Link to the current `heplab gui --open-browser` launch path until a portable
  web client replaces the embedded UI.

### Learn and documentation

- Build a guided path from event record to detector response and reconstructed
  objects, with units and provenance.
- Keep worked examples reproducible and sourced; label illustrative displays.
- Link handbook chapters, schemas, API behavior and ADRs by canonical file.

### Community and release

- Describe good first contributions, setup, coding conventions and review path.
- Publish actual release assets and support matrix only after they exist.
- Link security reporting, license, code of conduct if adopted, and upstream
  simulator/data citations.

## Simulator workspace navigation

Keep the existing task-oriented workspace: model browser, event viewport,
parameter inspector, run controls, and result/diagnostic panels. Add a lightweight
application navigation rail for Home, Simulator, Runs, Datasets and Help. Do not
turn scientific controls into marketing content. Show backend, model domain,
validation state and provenance in context.

## Content ownership

The website owns concise orientation, onboarding and community content. The
engineering handbook owns physics algorithms, requirements and validation
evidence. API schemas own wire contracts. Release metadata owns current download
assets and platform support. Avoid copying full technical chapters into website
pages.
