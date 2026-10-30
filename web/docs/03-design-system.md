# Site design

Starlight supplies the documentation interface, mobile navigation, theme
switcher, search, and accessible content structure. `src/styles/site.css`
contains a small set of project-level custom properties and spacing adjustments.

The visual direction is an instrument manual: quiet surfaces, readable prose,
clear hierarchy, and evidence only where there is a source. The HEPLab detector
mark is the site's logo and favicon. Avoid decorative gradients, stock imagery,
unsupported claims, and repeated feature cards.

## Theme adjustments

Use Starlight's `--sl-color-*` variables and semantic selectors when adjusting
the palette. Keep links and focus indicators visible in both themes. Preserve
the built-in theme switcher and reduced-motion behavior. Prefer the standard
Starlight content width unless a page has a specific reason to differ.

## Content and accessibility

- Use sentence case headings and short paragraphs.
- Give images useful alt text, captions, and source credits.
- Label scientific figures as data, simulation, or illustration.
- Put units on measured values and explain the limits of comparisons.
- Use semantic headings, lists, tables, and native links.
- Do not encode status or meaning using color alone.

See [writing guide](05-writing-guide.md) and [UI standards](08-ui-ux-standards.md)
for the content rules.
