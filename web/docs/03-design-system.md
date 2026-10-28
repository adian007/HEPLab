# 03 · Design system

All styles are in `src/styles/site.css`. This file explains the decisions so
they can be kept consistent.

## Direction

The site should look like a well-made scientific instrument manual: quiet
surfaces, precise numbers, one accent color, and real data as the main visual.
It should not look like a startup landing page. No stock gradients, glowing
blobs, floating 3D shapes, testimonial carousels or emoji.

The one dark, high-contrast element in both themes is the "instrument glass":
the event display and the terminal. They stay dark because they show data and
commands, and they read as tools rather than decoration.

## Wordmark

`components/Logo.tsx`. The name "HEPLab" as text in the display face, 600
weight, in the header and footer. There is no logo icon on the page. The browser
tab icon (favicon) is a data URI in `index.html`.

## Color tokens

Defined on `:root` for light, and again for dark under
`@media (prefers-color-scheme: dark)` and `:root[data-theme="dark"]`. Components
only use tokens, never raw hex, except inside the instrument glass.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f6f5f1` | `#080b0f` | page |
| `--bg-alt` | `#efede6` | `#0c1015` | alternating sections |
| `--surface` | `#ffffff` | `#10151c` | cards, inputs |
| `--line` / `--line-strong` | `#e2dfd6` / `#cbc6ba` | `#1d2530` / `#2b3542` | borders, grids |
| `--text` / `--muted` / `--subtle` | `#11151a` / `#555c66` / `#63686f` | `#e8edf1` / `#9aa5b0` / `#7f8a96` | text levels |
| `--accent` | `#06705f` | `#3fe0c0` | links, active state, "done" |
| `--amber` | `#975006` | `#ffb547` | the user's track, limits, caveats |

Meaning is fixed: teal means working or selected; amber means "look here" or
"limit". Do not use either for decoration.

Instrument glass uses its own fixed set (`--glass`, `--glass-2`, `--glass-line`,
`--glass-text`, `--glass-muted`) plus the dark-theme teal and amber.

## Type

| Role | Family | Notes |
|---|---|---|
| Headings | Space Grotesk Variable, 600 | tight letter-spacing (−0.02em; −0.045em on the hero) |
| Body | Inter Variable, 400/500 | 16 px base, line-height 1.6 |
| Numbers, labels, code | JetBrains Mono Variable | uppercase labels at 11 px with 0.08em tracking |

Every measured value (radius, sagitta, field, error) is in the mono face with
its unit in a smaller, muted span. Numbers should never be in the display face.

Sizes use `clamp()` for headings only: hero `44–92 px`, section titles `30–46 px`.

## Layout

- Content width `1180px`, side padding `24px` (`16px` under 700 px).
- Section padding `104px` (`72px` on phones).
- Radius: `14px` cards, `9px` small elements, `18px` the event display.
- Breakpoints: `1080px` (navigation becomes a menu, two-column layouts stack)
  and `700px` (all grids become one column).
- Grid columns use `minmax(0, 1fr)`, not `1fr`, so long code lines scroll inside
  their box instead of widening the page.

## Components

| Class | What it is |
|---|---|
| `.card` | Surface with border and soft shadow. The only raised element. |
| `.button`, `.button.primary` | Primary is inverted text/background, not accent-filled. |
| `.tag` | Status pill in mono. |
| `.mono-label` | Small uppercase metadata label. |
| `.kicker` | Section number and name above a heading, accent color. |
| `.maturity` | Three-bar maturity meter: Planned 0, In progress 1, Early implementation 2, Working/Foundations 3. Level comes from `maturityScale` in `content.ts`. |
| `.tracklab`, `.terminal` | Instrument glass. |

Add a component class only when a pattern appears twice. One-off tweaks belong
next to the section's existing rules.

## Motion

One animation: event-display tracks grow outward when a new event is
generated. It is off under `prefers-reduced-motion`. Hover effects are color or
1 px movement only.

No decorative graphics behind text. An earlier hand-drawn "tracks" background
in the hero was removed: it was not physically consistent and it crossed the
body text. Images on the site must be real data or real photographs, with a
caption and credit (see [08-ui-ux-standards.md](08-ui-ux-standards.md)).

## Accessibility checks

- Text contrast: every text token (`--text`, `--muted`, `--subtle`, `--accent`,
  `--amber`) is at least 4.5:1 (WCAG AA) on `--bg`, `--bg-alt` and `--surface`
  in both themes, and `--glass-muted` is at least 4.5:1 on the glass. Measured
  28 Oct 2026; the lowest pair is `--subtle` on light `--bg-alt` at 4.8:1.
  Re-measure whenever a text or background token changes.
- Visible focus ring on every interactive element (`:focus-visible`, accent).
- Touch targets at least 38 px.
- Meaning never by color alone: maturity has a text label, status has a word.
