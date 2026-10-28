# 08 · UI/UX standards

The site follows published standards rather than taste. This file lists which
ones, what each requires of this site, and where the site stands. Status was
checked on 28 Oct 2026; re-check after any layout or component change.

## Standards used

| Standard | Scope here |
|---|---|
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/), level AA | Accessibility: contrast, keyboard, structure, motion. EU public-sector rules (EN 301 549) reference WCAG 2.1 AA; 2.2 AA is a superset. |
| [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) | Keyboard and screen-reader behaviour of interactive widgets (tabs, menu button, live regions). |
| ISO 9241-110:2020, interaction principles | Suitability for the task, self-descriptiveness, conformity with expectations, error tolerance. |
| Scientific figure conventions (PDG style, journal figure guidelines) | Axes with quantities and units, captions, stated sources and uncertainties, colour-blind-safe encoding. |

## WCAG 2.2 AA: criteria that matter for this site

| Criterion | Requirement | How the site meets it |
|---|---|---|
| 1.1.1 Non-text content | Text alternative for images and charts | Canvas has `aria-label` plus a hidden list of every track; the evidence chart has `ariaLabel` and a caption. |
| 1.3.1 Info and relationships | Structure is in the markup | One `h1`, `h2` per section, `h3` inside; `dl` for facts and metrics; real lists and tables. |
| 1.4.3 Contrast (minimum) | 4.5:1 for text | All text tokens measured ≥ 4.5:1 in both themes; see [03-design-system.md](03-design-system.md). |
| 1.4.10 Reflow | No horizontal scroll at 320 px | Grids use `minmax(0, 1fr)`; checked at 375 px. |
| 1.4.11 Non-text contrast | 3:1 for controls and focus rings | Inputs and buttons use `--line-strong` borders; focus ring is the accent. |
| 2.1.1 Keyboard | Everything works by keyboard | All controls are native buttons, links or inputs. |
| 2.1.4 Character key shortcuts | Single-key shortcuts must be removable | None. The former `/` search shortcut was removed for this reason. |
| 2.3.3 Animation from interactions | Motion can be disabled | `prefers-reduced-motion` stops all animation. |
| 2.4.1 Bypass blocks | Skip link | "Skip to content" link to `#main`. |
| 2.4.7 / 2.4.11 Focus visible, not obscured | Focus always visible, not under the sticky header | `:focus-visible` ring; `scroll-padding-top: 76px`. |
| 2.5.8 Target size (minimum) | 24 × 24 px targets | Smallest targets are the copy buttons at 30 px. |
| 3.1.1 Language of page | `lang` attribute | `<html lang="en">`. |
| 4.1.2 Name, role, value | Widgets expose state | Sliders have `aria-valuetext` with units (the momentum slider is logarithmic, so the raw value would be meaningless); tabs have `aria-selected`; menu has `aria-expanded`. |
| 4.1.3 Status messages | Announce changes without moving focus | `aria-live` on docs result count, copy confirmation and track status; API state is announced in the status pill. |

Known gaps:

- Links that open a new tab do not announce it. Add a visually hidden
  "(opens in a new tab)" to external links.
- Contrast and keyboard checks are manual. Automate with axe-core in the
  Playwright test proposed in [07-future-improvements.md](07-future-improvements.md).

## ISO 9241-110 principles applied

- **Suitability for the task.** Sections are ordered by the visitor's questions
  (what is it, does it work, can I trust it, how do I run it). No content that
  serves none of them.
- **Self-descriptiveness.** Every number has a unit. Every status has a word,
  not only a colour. The status pill says whether live project data loaded.
- **Conformity with expectations.** Standard controls only: native range
  inputs, buttons, links, a search field. The logo-free text wordmark links to
  the top, as users expect.
- **Error tolerance.** When the API is down, the page keeps working with stored
  content and says so. The evidence section shows no numbers rather than
  invented ones.
- **Controllability.** Visitors choose theme, momentum, field, charge and event;
  nothing changes on a timer.

## Scientific figures

Every chart, display or image must have:

1. **Axes or scale with quantity and unit.** "Muon kinetic energy (GeV)", a
   "0.5 m" scale bar.
2. **A caption** that says what is shown and what is not.
3. **A source**: dataset DOI, reference table, simulator run ID, or photo credit.
4. **Its status**: recorded data, simulation, or illustration. Never leave the
   reader to guess.
5. **Uncertainty or limits** where a value is measured or computed (for example
   the acceptance band in the evidence chart, the stated assumptions under the
   resolution readout).
6. **Colour-blind-safe encoding.** Never rely on hue alone. In the event
   display the highlighted muon differs from other tracks by colour (amber vs
   blue) and by line weight; extrapolations are dashed; the sagitta is labelled
   "s". Not yet checked with a colour-vision simulator; do that before adding
   new series.

## Images and photographs

- Use real event displays or real photographs only. No stock art, no
  AI-generated imagery, no decorative "science" graphics.
- Check the licence on the image's own record before use:
  - CMS Open Data (opendata.cern.ch) is released under CC0, so events rendered
    from it can be shipped in this repository.
  - Most CMS images on the CERN Document Server are "© CERN, for the benefit of
    the CMS Collaboration … freely available for non-commercial use", and
    CERN's [terms of use](https://copyright.web.cern.ch/) forbid making them
    available to third parties. They must not be committed to this Apache-2.0
    repository.
  - Some ATLAS event displays are CC BY 4.0 and may be included with credit.
- Credit format next to the image: what it shows, the experiment, year, and the
  copyright line exactly as on the record, with a link to the record.
- Self-host images (no hotlinking) and give width and height to avoid layout shift.
