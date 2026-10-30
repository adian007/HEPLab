# Website and desktop delivery plan

This plan separates project documentation, local simulation, scientific
validation, and desktop packaging.

## Milestones

### W0 — project documentation site (implemented)

- Build a project guide with ASP.NET Core Razor Pages and Markdig.
- Document setup, workbench behavior, analysis, evidence, limitations, and
  contribution paths.
- Keep public documentation independent of local APIs and artifacts.

### W1 — public hosting and maintenance

- Choose a .NET 10 hosting target and add deployment automation.
- Keep project status pages aligned with implementation evidence.
- Add release-specific pages when supported installers exist.

### W2 — desktop application

- Select and implement a shell after measuring Python/runtime packaging options.
- Add supervised service lifecycle, installers, platform support matrix, signing,
  notices, update/rollback and data migration.
- Publish only after clean-machine and native-runtime evidence.

## Acceptance evidence

- A new visitor can tell what HEPLab implements and which physics claims remain
  unvalidated.
- A contributor can find setup, architecture, contribution, and license guidance.
- Local users can run bounded jobs and inspect results through the Python
  workbench without granting arbitrary filesystem authority to a public site.
- Scientific output preserves run identity, immutable artifacts, provenance,
  units, and validation state.
- Published app content is reproducible and reviewed for licenses and unwanted
  network calls.
