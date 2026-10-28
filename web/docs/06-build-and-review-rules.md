# 06 · Build and review rules

How to make a change to the site so that it stays correct and consistent.

## Before you start

1. Decide what question the change answers for a visitor. If none, do not add it.
2. Check whether the content belongs on the site at all, or in the handbook
   (algorithms, requirements, validation detail belong in the handbook).
3. Find the existing pattern: a token, component class or `content.ts` list.
   Reuse it before adding a new one.

## Logic rules

- **One source per fact.** Product name in `brand.ts`, copy in `content.ts`,
  live data from the API, styles in `site.css`. Never copy a value into a second
  place.
- **Model every async state.** Use `useRemote`; render `loading`, `ready` and
  `offline` explicitly. A component must look intentional in all three.
- **Fallbacks must be true.** A static fallback is fine for descriptive content.
  For measured values, show "unavailable" with a link to the record; never a
  placeholder number.
- **No hidden network calls.** The site reads only `/api/v1/project/*`. Adding an
  endpoint means adding it to `src/heplab/server/project.py`, to the desktop
  `OPERATIONS` table, and to [01-stack.md](01-stack.md).
- **Browser storage is only for preferences** (theme). Wrap every access in
  try/catch; the page must render without it.
- **Derive, don't store.** Filtered lists, readouts and labels are computed from
  state during render, not kept in their own state.
- **Clean up effects.** Every listener, observer, animation frame and request
  started in `useEffect` is removed in its cleanup.
- **Keep components small.** If a component has its own data fetching or more
  than about 150 lines, move it to its own file.

## Design rules

- Use tokens. A raw color in a component rule is a review comment.
- New layouts must work at 320, 375, 768, 1080 and 1440 px with no horizontal
  page scroll.
- Check both themes. Instrument-glass elements are dark in both.
- Every interactive element has a visible focus state, a label, and a target of
  at least 38 px.
- Motion is optional decoration; the content must make sense with it off.
- Do not add a dependency for something CSS or 30 lines of code can do.

## Checks to run

```bash
pnpm --dir web typecheck
pnpm --dir web build
```

Then open the dev server and check by hand (until automated tests exist):

- [ ] Page loads with the API running: status dot is teal, evidence chart shows.
- [ ] Page loads with the API stopped: no errors in the console, evidence shows
      the offline message, everything else is unchanged.
- [ ] `document.documentElement.scrollWidth === innerWidth` at 375 px.
- [ ] Light and dark themes; theme choice survives a reload.
- [ ] Keyboard only: every control reachable with Tab, arrow keys switch quickstart tabs, Escape closes the menu.
- [ ] The standards checklist in [08-ui-ux-standards.md](08-ui-ux-standards.md).
- [ ] Event display: 4 GeV at 3.8 T reads R = 3.51 m, sagitta 41.8 mm, σ(pT)/pT 0.86 %.
- [ ] Text passes the checklist in [05-writing-guide.md](05-writing-guide.md).

## Review

A reviewer should be able to answer yes to:

- Is every new claim true today?
- Is there one source for every new fact?
- Does it work offline, on a phone, in both themes, from the keyboard?
- Was anything added that could have been reused instead?
