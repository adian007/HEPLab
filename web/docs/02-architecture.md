# 02 · Architecture

## Files

```text
web/
├── index.html                 meta tags, favicon, theme pre-paint script
├── src/
│   ├── main.tsx               font imports, global CSS, React root
│   ├── brand.ts               product name, tagline, CLI name, repository URL
│   ├── content.ts             all static copy and lists (capabilities, docs, limits…)
│   ├── lib/
│   │   ├── api.ts             payload types and the useRemote hook
│   │   └── desktop.ts         Tauri transport (owned by the desktop shell work)
│   ├── components/
│   │   ├── Logo.tsx           logo mark and wordmark
│   │   └── TrackLab.tsx       interactive event display (see 04-event-display.md)
│   ├── features/
│   │   └── EvidenceFigure.tsx validation chart and field-check panel
│   ├── app/
│   │   └── App.tsx            page shell, sections, small UI pieces
│   └── styles/
│       └── site.css           tokens, themes, every component style
└── docs/                      these notes
```

Where to put a change:

- **Wording or a list item** → `content.ts`. Do not hard-code copy in components
  unless it is a single heading.
- **Product name or repository link** → `brand.ts`. Everything else reads from it.
- **A new section** → a component in `App.tsx`; move it to its own file under
  `features/` once it has its own state or data.
- **Anything visual** → `site.css`, using existing tokens.

## Page structure

One page, sections in reading order. Navigation is plain anchor links; there is
no client-side router.

| Anchor | Section | Data source |
|---|---|---|
| `#top` | Hero: what HEPLab is, status, install link | `brand.ts`, overview API (stage, license) |
| `#simulator` | Interactive event display | computed in the browser |
| `#capabilities` | Capabilities with maturity, then the 5-step workflow | `content.ts` |
| `#evidence` | Silicon energy-loss chart, CMS field check | evidence API |
| `#architecture` | Layers diagram, language stack | `content.ts`, overview API (stack) |
| `#quickstart` | Tabbed install/run commands with copy buttons | `content.ts` |
| `#docs` | Searchable list of handbook documents | `content.ts` |
| `#roadmap` | Known limits, roadmap | `content.ts`, overview API (roadmap) |

The order follows the questions a visitor has: what is it, can I see it work,
what does it do, can I trust it, how is it built, how do I run it, where is the
detail, what is missing.

## Data flow

```text
FastAPI (/api/v1/project/*) ──fetch──┐
                                     ├── useRemote<T>(url) ── { loading | ready | offline }
Tauri heplab_invoke ───(desktop)─────┘            │
                                                  ▼
                       App / EvidenceFigure: live value ?? fallback from content.ts
```

`useRemote` is the only network code. It:

- returns a tagged union, so a component cannot read `data` before it exists;
- aborts the request on unmount;
- turns any failure into `offline` and logs at `debug` level only.

Every API-backed value has a static fallback in `content.ts`, so the page reads
the same with the service down. The evidence section is the exception: it shows a
short explanation and a link to the recorded results, because inventing numbers
would be worse than showing none.

## Client state

All state is local `useState`. There is nothing global to share.

| State | Where | Persisted |
|---|---|---|
| Theme (`light`/`dark`) | `useTheme` in `App.tsx` | `localStorage` key `theme`, wrapped in try/catch |
| Active section | `useActiveSection` (IntersectionObserver) | no |
| Mobile menu open | `App` | no; closes on Escape or link click |
| Quickstart tab, docs query | their components | no |
| Event display controls | `TrackLab` | no |

The theme is applied before React loads by a small inline script in
`index.html`, so the page does not flash the wrong theme. Without a stored
choice the page follows `prefers-color-scheme`.

## Keyboard and accessibility behaviour

- Skip link to `#main`.
- Escape closes the mobile menu; the menu button has `aria-expanded` and `aria-controls`.
- Quickstart tabs follow the WAI-ARIA tabs pattern: arrow keys, Home and End.
- No single-key shortcuts (WCAG 2.1.4).
- Charts and the canvas have text alternatives: `aria-label`, figure captions,
  and a screen-reader list of every track in the event display.
- Live regions announce the docs result count, copy confirmation, and the
  event display's track status.
- Animations stop under `prefers-reduced-motion`.

Full criteria: [08-ui-ux-standards.md](08-ui-ux-standards.md).
