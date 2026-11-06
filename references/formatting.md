# Formatting contract

The formatter and verifier enforce the mechanical parts of this contract. The LLM writes content and semantic emphasis. When in doubt, prefer the simpler form.

## Line breaks

- **No column-based hard wrapping.** Keep each paragraph, bullet, table row and caption on one logical line.
- Separate blocks with one blank line: headings, paragraphs, lists, images, captions, tables and horizontal rules.
- Do not put a blank line inside a bullet or between an image and its caption.
- Grouped captions are consecutive lines. Add `<br>` at the end of every line except the last:
  ```
  **Figure 1B**: ...<br>
  **Figure 1C**: ...
  ```
- End the file with exactly one newline.
- Strip trailing whitespace.

## Headings

- H1: handbook title and each chapter (`# Chapter 1. ...`).
- H2: analytical units (`## 1.1 ...`) and end-matter sections (`## A. ...`).
- H3 only when a unit truly needs sub-structure; avoid it by default.
- Do not skip heading levels.

## Bold

Use bold for:

- Unit labels: `**Goal and principle.**`, `**Methods**`, `**Results**`.
- Figure caption labels: `**Figure 1A**:`, `**Fig. 1b**:`, `**ED Fig. 1**:`.
- Tool names at first mention in Methods: `**Trim Galore! v0.6.0**`, `**MACS2**`.
- Table column headers? No: use Markdown table header syntax, not bold.

Do not bold:

- Ordinary emphasis, gene names, cell-type names, or units.
- Inline figure references (`Figure 1A`, `[Fig. 2g](...)`).
- Table cells.
- Whole sentences.

## Inline code

Use backticks for literal, machine-readable tokens:

- flags: `--paired`, `-SP5M`, `--min-alternate-fraction 0.05`
- parameter values: `N_cells_per_location = 30`
- filenames and extensions: `.cool`, `c2.all.v7.1.symbols.gmt`
- identifiers and functions: `preprocessCore::normalize.quantiles`, `RunPCA`
- short command fragments

Do not use inline code for:

- tool names (`**MACS2**`, not `` `MACS2` ``)
- gene names
- ordinary numbers or units (`10 kb`, not `` `10 kb` ``)
- section names or figure labels

## Italics

Use italics for:

- emphasis and defined terms: *putative silencers*, *neo P-S*
- paper section names: *Methods*
- species names if conventional

Do not italicize figure labels or tool names.

## Lists

- Use `- ` for unordered lists.
- One item per line.
- Do not put a blank line between consecutive items.
- Use a colon to introduce a list if the list is long or itemized.
- Nested lists are allowed only when the hierarchy is real; the formatter does not renumber them.

## Tables

- Use a header row, separator row, then one record per line.
- No blank lines inside a table.
- Keep cells concise.
- Use backticks inside cells for literal parameters.
- Do not use tables for long prose; use bullets.

## Figure captions

Canonical form:

```
![Figure 1A–B](slug.assets/figure01a-b.png)

**Figure 1A–B**: Integrated analysis of the embedded panels.
```

- The image line is on its own line.
- One blank line between image and caption.
- The label is bold, followed by a colon outside the bold.
- Preserve the paper's figure naming (`Figure`, `Fig.`, `ED Fig.`, `Extended Data Fig.`).
- Panel qualifiers stay inside the bold label: `**Fig. 1c (right)**: ...`.
- The caption label must match the embedded asset's panel set. A single-panel crop uses `**Figure 1G**`; a consecutive run uses `**Figure 3F–H**`.
- Consecutive cited panels form one union rectangle. A citation gap splits the crop: `2a`, `2c`, `2d` becomes `2a` and `2c–d`.
- Uncited panels inside a union rectangle are acceptable; the caption lists the cited panels.
- A full figure label (`**Figure 1**`) is allowed only for a whole-figure citation or a figure with no panel structure.
- Grouped captions use `<br>` and no blank lines between caption lines.
- Inline references stay plain or linked; only caption labels are bold.

## Deterministic enforcement

`format_handbook.py` performs only safe transformations:

- trailing whitespace and final newline,
- blank-line separation,
- list marker normalization,
- exact section-label normalization,
- bold caption labels in Results context.

It skips ambiguous lines and reports them. `verify_handbook.py` fails nonconforming caption labels and trailing whitespace. Neither script reflows or rewrites prose.
