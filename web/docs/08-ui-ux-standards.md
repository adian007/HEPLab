# UI and content standards

Razor Pages provides the navigation and documentation interface. Preserve
keyboard support, focus visibility, responsive layout, and theme controls when
customizing the site. Reuse Bootstrap components and the shared Razor partials
before adding a separate control implementation. Navigation drawers must trap
focus and restore it on dismissal. Theme controls must work in the mobile drawer.
All small-screen checkpoint buttons need descriptive accessible names.

## Page structure

- Use one clear page title and an ordered heading hierarchy.
- Write descriptive link text; avoid generic “click here” labels.
- Use tables for genuinely tabular comparisons and lists for sequences.
- Ensure content remains readable at narrow widths and browser zoom.
- Keep controls operable by keyboard and focus indicators visible.
- Check all indexed pages and local anchors with `tools/check_site_runtime.py`.
- Inspect real browser screenshots in both themes and at phone/desktop widths;
  a passing HTML response or accessibility snapshot does not prove visual quality.
- Keep vendored UI package licenses and hashes current when upgrading assets.

## Scientific communication

Every figure, table, or result excerpt should state what it shows, its source,
units, and limits. Label content as recorded data, simulation, or illustration.
Explain the scope of a validation result; a code run or regression check alone
does not establish agreement with measured detector data.

## Images

Use project assets or images whose license permits redistribution. Include a
useful alternative description and nearby source credit. Do not use decorative
science imagery to imply a result or capability.
