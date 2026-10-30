# Site design

ASP.NET Core 10 Razor Pages, C# Tag Helpers, and Bootstrap 5.3.8 provide the
interface. `wwwroot/css/site.css` owns the shared design tokens, layout, typography,
and documentation workspace. `activities.css` styles the lab and gallery.

The visual direction combines an instrument console and a field notebook:
graphite surfaces, teal actions, warm highlights, fine rules, and a clear reading
hierarchy. IBM Plex Sans is the body/interface face; IBM Plex Mono distinguishes
technical labels, units, and code. The light theme uses pale paper surfaces and
dark green text. Both fonts are hosted locally with their licenses.

The home page places its introduction above a separate, centered event display so
the explanatory copy and detector view read as distinct sections. The interactive
Canvas 2D renderer projects the checked-in synthetic fixture's 3D points and
declared cylindrical/disk surfaces; it runs no simulation. The C# preview service
supplies fixture settings and provenance. Keep the synthetic label, field-region
style, units, and limitations visible. Gallery thumbnails are explicitly schematic.
Never imply that a rendered trajectory is a measurement.

## Theme adjustments

Use `--page`, `--surface`, `--raised`, `--line`, `--ink`, `--muted`, `--subtle`,
`--accent`, `--amber`, and `--blue`. Compatibility `--sl-color-*` variables map the
activity components to those same tokens. `data-theme` and Bootstrap's
`data-bs-theme` are synchronized before styles load and when the selection changes.
Storage is optional. Keep links and focus indicators visible in both themes.

The Bootstrap offcanvas handles the mobile navigation backdrop, focus trap,
Escape dismissal, and focus return. Search uses a native dialog with arrow-key
result navigation. Use `lab-icon` for decorative interface icons and visible text
for accessible control names. Use real links for navigation and buttons for actions.
Respect reduced motion and keep the layout readable at 390 px and browser zoom.

## Content and accessibility

- Use sentence case headings and short paragraphs.
- Give images useful alt text, captions, and source credits.
- Label scientific figures as data, simulation, or illustration.
- Put units on measured values and explain the limits of comparisons.
- Use semantic headings, lists, tables, and native links.
- Do not encode status or meaning using color alone.

See [writing guide](05-writing-guide.md) and [UI standards](08-ui-ux-standards.md)
for the content rules.
