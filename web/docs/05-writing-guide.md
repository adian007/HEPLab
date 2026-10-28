# 05 · Writing guide

The site is read by physicists, students and developers deciding whether to
trust and use HEPLab. Text should be accurate first, short second.

## Accuracy rules

1. Every capability claim must match the code today. If it is partial, give its
   maturity level.
2. "Runs", "completed" and "passed" describe software, not physics. Never write
   "validated", "accurate" or "calibrated" unless the handbook records that
   evidence for that exact scope.
3. Numbers come from the API or the repository, never typed from memory. Give
   units.
4. Name the source for every evidence figure and link it.
5. Label anything illustrative as illustrative, where it appears.
6. Do not promise dates or releases. Roadmap items describe work, not delivery.

## Style

- Plain words. "Uses" not "leverages", "shows" not "showcases", "lets you" not
  "empowers you to".
- Short sentences with a subject and a verb. Headings may be phrases, body text
  may not.
- Say what something does, then stop. Remove the sentence that restates the
  heading.
- One idea per paragraph. Two to three sentences is normal.
- Sentence case for headings. American spelling.
- Units with a space: `3.8 T`, `1.1 m`, `45 GeV`.

## Patterns to remove ("AI slop")

These read as generated filler and lower trust. Delete them on sight.

| Pattern | Example | Write instead |
|---|---|---|
| Inflated adjectives | "cutting-edge", "powerful", "seamless", "robust", "state-of-the-art" | Say what it does and how well. |
| Empty verbs | "unlock", "empower", "elevate", "supercharge", "streamline" | The actual action. |
| Promises the code can't keep | "every number traces back to its inputs" while provenance is in progress | "Runs record their configuration and seed. Full lineage is in progress." |
| Slogan fragments | "Local compute. Clear boundaries." | A full sentence, or a plain label. |
| Triplet value lists | "Fast, reliable, and scalable." | One specific property with evidence. |
| Restated headings | Heading "Get started", text "Getting started is easy." | Go straight to the first step. |
| Fake balance | "Whether you're a student or a researcher…" | Write for the reader in front of you. |
| Rhetorical openers | "Ever wondered how…?", "Imagine…" | State the point. |
| Decorative em-dash chains | "It's fast — really fast — and simple." | One clause. |
| Generic icon grids | Three cards with icons and two-word benefits | Real content, or nothing. |

During this redesign the following were removed for these reasons: a three-card
"Inspectable / Reproducible / Honest" block (repeated other sections), a hero
claim of full traceability (not yet true), and the tagline "Trust the result"
(the site's own limits section says results are not validated).

## Checklist before merging text

- [ ] Each claim is true today, or marked with its maturity.
- [ ] No word from the table above.
- [ ] Numbers have units and a source.
- [ ] Nothing says the site runs simulations.
- [ ] Read it aloud once. Cut anything you skipped while reading.
