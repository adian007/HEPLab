# HEPLab website: engineering notes

These notes describe how the HEPLab project website in `web/` is built, why it
is built that way, and what to change next. They are for anyone editing the
site, including AI coding assistants.

Product scope, API contracts and desktop packaging for the whole project live in
[`docs/web/`](../../docs/web/README.md) at the repository root. This folder covers
only the website's own code, design and writing.

| File | Read it when you want to |
|---|---|
| [01-stack.md](01-stack.md) | Know what the site runs on, how to run it, and how it is served. |
| [02-architecture.md](02-architecture.md) | Find where something lives and how data reaches the page. |
| [03-design-system.md](03-design-system.md) | Change colors, type, spacing, layout or components. |
| [04-event-display.md](04-event-display.md) | Change the interactive track display or its physics. |
| [05-writing-guide.md](05-writing-guide.md) | Write or edit any text on the site. |
| [06-build-and-review-rules.md](06-build-and-review-rules.md) | Make a change and check it before merging. |
| [07-future-improvements.md](07-future-improvements.md) | Pick up the next piece of work. |
| [08-ui-ux-standards.md](08-ui-ux-standards.md) | Check the site against the accessibility, usability and scientific-figure standards it follows. |

## The site in one paragraph

A single React page that explains HEPLab: what it does today, how mature each
part is, recorded validation evidence, architecture, install commands, links to
the handbook, and known limits. It reads two public, read-only endpoints from the
local FastAPI service and works without them. It never runs simulations; the
simulator is a separate local application at `/workbench`.

## Rules that override everything else

1. Do not claim more than the code and evidence support. If a feature is
   partial, say so on the page.
2. The engineering handbook is the source of truth for physics and
   requirements. The site summarizes and links; it does not restate.
3. The site must work with the API offline, with JavaScript-heavy features
   degraded rather than broken, at 320 px wide, and in both color themes.
