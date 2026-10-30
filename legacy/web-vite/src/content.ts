// Static site content. Live values from /api/v1/project/overview override the
// fallbacks where the API provides them.

export type Maturity = 'planned' | 'in-progress' | 'early-implementation' | 'working-increment' | 'foundations'

export const maturityScale: { id: Maturity; label: string; level: number }[] = [
  { id: 'planned', label: 'Planned', level: 0 },
  { id: 'in-progress', label: 'In progress', level: 1 },
  { id: 'early-implementation', label: 'Early implementation', level: 2 },
  { id: 'foundations', label: 'Foundations in place', level: 3 },
  { id: 'working-increment', label: 'Working increment', level: 3 },
]

export const capabilities: {
  id: string; name: string; status: Maturity; summary: string; includes: string[]; href: string
}[] = [
  {
    id: 'simulation', name: 'Local particle simulation', status: 'working-increment',
    summary: 'A deterministic muon thin-slab reference bench, a Rust numerical engine, and native Drell–Yan generation through PYTHIA8 + DELPHES when that runtime is present.',
    includes: ['Solenoid-field propagation and XY/XZ/3D track views', 'Energy loss, multiple scattering, channel response', 'Seeded configurations and exportable artifacts'],
    href: 'docs/engineering/sim-runtime.md',
  },
  {
    id: 'data', name: 'CERN Open Data path', status: 'foundations',
    summary: 'Versioned dataset manifests carry certification, exact source ranges, checksums and provenance from the record into your analysis.',
    includes: ['Verified Run2016G DoubleMuon record', 'NanoAOD and Delphes readers', 'Bounded Parquet cache with integrity checks'],
    href: 'docs/engineering/02-data-supply.md',
  },
  {
    id: 'analysis', name: 'Analysis & comparison', status: 'early-implementation',
    summary: 'Shared event and artifact contracts connect simulated and recorded events to the same processors, histograms and fits.',
    includes: ['Schema-v1 event model', 'Dimuon analysis with cutflows', 'iminuit fitting and PNG plots'],
    href: 'docs/engineering/01-architecture.md',
  },
  {
    id: 'evidence', name: 'Reproducible run records', status: 'in-progress',
    summary: 'Each run is meant to carry what produced it: frozen configuration, seed, engine version and software lineage — kept separate from physics validation.',
    includes: ['Run identity and frozen config', 'Engine capability reporting', 'Immutable, source-linked outputs'],
    href: 'docs/engineering/14-verification.md',
  },
]

export const workflow = [
  { step: 'Source', detail: 'Pick a CERN Open Data record or a generator configuration.', meta: 'manifest · DOI · checksum' },
  { step: 'Model', detail: 'Set field, material, seed and response — with units.', meta: 'B = 3.8 T · Si · seed 42' },
  { step: 'Run', detail: 'Execute locally on the reference bench, Rust engine or native runtime.', meta: 'Python · Rust · PYTHIA8' },
  { step: 'Inspect', detail: 'Follow particles through the detector in linked views.', meta: 'XY · XZ · 3D · crossings' },
  { step: 'Record', detail: 'Write the result with its configuration, seed and source.', meta: 'config · run id · lineage' },
]

export const architecture = [
  { lane: 'Interfaces', nodes: [
    { name: 'Workbench GUI', note: 'Local browser app · today' },
    { name: 'CLI & notebooks', note: 'Automation and research' },
    { name: 'Desktop app', note: 'Planned', planned: true },
  ] },
  { lane: 'Services · Python 3.12', nodes: [
    { name: 'Contracts & run plans', note: 'Validated, scoped inputs' },
    { name: 'Jobs & artifacts', note: 'Run lifecycle, durable outputs' },
    { name: 'Data & analysis', note: 'Readers, processors, provenance' },
  ] },
  { lane: 'Compute & sources', nodes: [
    { name: 'Python reference', note: 'Transparent baselines' },
    { name: 'Rust + PyO3', note: 'Numerical kernels' },
    { name: 'PYTHIA8 + DELPHES', note: 'Optional native runtime' },
    { name: 'CERN Open Data', note: 'Versioned records' },
  ] },
]

export const fallbackStack = [
  { name: 'Python 3.12', role: 'Application services, CLI and data workflows' },
  { name: 'Rust + PyO3', role: 'Numerical engine and Python integration' },
  { name: 'PYTHIA8 + DELPHES', role: 'Optional native collision generation and fast simulation' },
  { name: 'React + TypeScript', role: 'Project website' },
]

export const quickstart: { id: string; label: string; steps: { note: string; cmd: string }[] }[] = [
  { id: 'workbench', label: 'Workbench', steps: [
    { note: 'Install with the analysis and server extras', cmd: "pip install -e '.[analysis,serve]'" },
    { note: 'Open the local simulator in your browser', cmd: 'heplab gui --open-browser' },
  ] },
  { id: 'windows', label: 'Windows + WSL', steps: [
    { note: 'Configure Rust and native runtimes, then launch', cmd: '.\\tools\\start_workbench.ps1' },
  ] },
  { id: 'analysis', label: 'Analysis CLI', steps: [
    { note: 'Browse the dataset catalog', cmd: 'heplab catalog list' },
    { note: 'Run the dimuon analysis on schema-v1 events or NanoAOD', cmd: 'heplab run dimuon --input events.json --output artifacts/dimuon.json' },
    { note: 'Plot the result', cmd: 'heplab plot artifacts/dimuon.json' },
  ] },
]

export const docs = [
  { group: 'Start here', title: 'Project README', description: 'Install the package and run the local workbench.', path: 'README.md' },
  { group: 'Engineering', title: 'Engineering handbook', description: 'Architecture, requirements, algorithms, verification and limitations.', path: 'docs/engineering/README.md' },
  { group: 'Simulator', title: 'Native simulation runtime', description: 'Supported PYTHIA8 + DELPHES environment, setup and acceptance.', path: 'docs/engineering/sim-runtime.md' },
  { group: 'Simulator', title: 'Geometry & calibration', description: 'CMS pixel surfaces, solenoid trajectories and the silicon loss fit.', path: 'docs/engineering/geometry-calibration.md' },
  { group: 'Evidence', title: 'Implementation record', description: 'What exists today, what was checked, what remains incomplete.', path: 'docs/engineering/implementation.md' },
  { group: 'Architecture', title: 'Website & desktop architecture', description: 'Site boundaries, local service and desktop release direction.', path: 'docs/web/README.md' },
  { group: 'Contribute', title: 'Architecture decisions', description: 'Why the project uses its languages and component boundaries.', path: 'docs/adr/README.md' },
]

export const limits = [
  { area: 'Physics validation', state: 'Open', summary: 'Smoke checks and named-reference comparisons do not establish detector calibration or broad agreement with measured physics.', next: 'Independent comparisons and a stated validity domain per model.' },
  { area: 'Thin-slab reference bench', state: 'Scoped', summary: 'Covers heavy, singly charged particles in thin silicon. No straggling, secondaries, showers or full detector response.', next: 'Keep it transparent for teaching; extend only with explicit contracts and evidence.' },
  { area: 'Native event generation', state: 'Environment-dependent', summary: 'PYTHIA8 and DELPHES need the supported Linux/WSL runtime and are not available everywhere.', next: 'Document versions, capability checks and deterministic smoke coverage.' },
  { area: 'Desktop distribution', state: 'Planned', summary: 'No installer yet. Today the simulator is a local Python app with a browser workbench.', next: 'Platform installers, signing, updates and a support matrix.' },
]

export const fallbackRoadmap = [
  { phase: 'FOUNDATIONS', name: 'Contracts & numerical core', status: 'IN PROGRESS', detail: 'Versioned schemas, requirements, numerical references, and Rust/PyO3 integration.' },
  { phase: 'DATA', name: 'Trustworthy data path', status: 'IN PROGRESS', detail: 'Certification, exact ranges, bounded caching, integrity evidence, and offline replay.' },
  { phase: 'SIMULATION', name: 'Generation & detector response', status: 'IN PROGRESS', detail: 'Pinned native runtime and scoped reference bench; independent validation remains open.' },
  { phase: 'RELEASE', name: 'Desktop distribution', status: 'PLANNED', detail: 'Desktop shell, packaged service, installers, signing, updates, and supported runtime matrix.' },
]
