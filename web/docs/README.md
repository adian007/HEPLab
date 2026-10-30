# HEPLab website: engineering notes

These notes describe how the HEPLab Starlight project guide in `web/` is built,
how to edit its pages, and how to keep the content accurate. They are for anyone
editing the site.

Product scope, API contracts and desktop packaging for the whole project live in
[`docs/web/`](../../docs/web/README.md) at the repository root. This folder covers
only the website's own code, design and writing.

| File | Read it when you want to |
|---|---|
| [01-stack.md](01-stack.md) | Know what the site runs on, how to run it, and how it is served. |
| [02-architecture.md](02-architecture.md) | Find where something lives and how data reaches the page. |
| [03-design-system.md](03-design-system.md) | Change colors, type, spacing, layout or components. |
| [04-event-display.md](04-event-display.md) | Document the separate local workbench display. |
| [05-writing-guide.md](05-writing-guide.md) | Write or edit any text on the site. |
| [06-build-and-review-rules.md](06-build-and-review-rules.md) | Make a change and check it before merging. |
| [07-future-improvements.md](07-future-improvements.md) | Pick up the next piece of work. |
| [08-ui-ux-standards.md](08-ui-ux-standards.md) | Check the site against the accessibility, usability and scientific-figure standards it follows. |

## The site in one paragraph

An Astro Starlight documentation site that explains HEPLab: what it does today,
how mature each part is, recorded validation evidence, architecture, install
commands, links to the handbook, and known limits. It is static and has no
dependency on the local FastAPI service. The simulator is a separate local
application.

## Rules that override everything else

1. Do not claim more than the code and evidence support. If a feature is
   partial, say so on the page.
2. The engineering handbook is the source of truth for physics and
   requirements. The site summarizes and links; it does not restate.
3. The site must work as static content at narrow widths and in both color
   themes. Starlight's search and mobile navigation are the only essential
   interactive features.
