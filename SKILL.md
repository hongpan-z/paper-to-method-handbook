---
name: paper-to-method-handbook
description: Convert a published paper PDF into a source-grounded, method-centered Markdown handbook. Use whenever the user asks to reconstruct, reorganize, or extract the methods from a paper; build a methods handbook or analysis workflow from a PDF; focus on a specific method family such as Hi-C, spatial transcriptomics, or scRNA-seq; map figure panels to analytical steps; or turn a STAR Methods or Nature Methods section into a usable workflow. Supports full experimental plus computational methods or a scoped computational/data-analysis handbook. Always preserves tool versions and parameters, marks unspecified steps, and extracts and embeds figure panels. Do not use for paper summaries, peer review, or results-only digests.
compatibility: Requires Python 3.10+ with PyMuPDF and Pillow.
license: MIT
metadata:
  version: "0.1.0"
  author: "Hongpan Zhang"
  repository: "https://github.com/hongpan-z/paper-to-method-handbook.git"
---

# Paper to Method Handbook

Build a handbook that reconstructs a paper's methods as a reproducible, analysis-unit-by-analysis-unit workflow. The output is not a summary: every Methods statement is traceable to the source, and every figure panel is linked to the claim it supports.

## When to use this skill

Use it when the user wants any of the following:

- A complete methods handbook from a paper PDF.
- A focused handbook for one assay or analysis family, such as "all Hi-C data analysis" or "the spatial transcriptomics workflow."
- A methods section reorganized by analytical dependency rather than paper chronology.
- A figure-to-method map, a parameter/threshold table, or a reproducibility audit of a paper's methods.
- A computational workflow extracted from a paper that also contains wet-lab experiments.

Do not use it for a paper summary, a results-only digest, peer review, or a literature comparison. Do not invent missing parameters to make a workflow look complete.

## Intake contract

Before writing files, settle these points and record them in `working/scope.md`:

1. **Scope**: complete methods, or a named method family/data layer?
2. **Organizing principle**: a data layer (for example, the Hi-C contact matrix) or an analytical/biological workflow (for a multi-modal paper with no dominant data layer)?
3. **Experimental content**: for a complete-methods request, include experimental and computational methods. For an explicitly computational request, include only the experimental background needed to interpret inputs and validation, and state that wet-lab protocols are out of scope.
4. **Output location and name**: one Markdown handbook plus a sibling assets directory.
5. **Figure policy**: extract and embed the panels cited by each Results section. A single cited panel is cropped alone; consecutive cited panels are cropped as one union rectangle. Uncited panels inside that rectangle are acceptable. Different figures use separate image blocks. A full figure is used only for a whole-figure citation or a figure with no panel structure.
6. **Available sources**: main PDF, supplementary PDF, tables, code repositories, data accessions.

If the user asks for a full methods handbook, default to including experimental methods. If the user asks for a computational/data-analysis workflow, mirror the focused style: computational units plus necessary experimental context, not full bench protocols.

The workflow is uniform: scope changes which units are included, not a separate pipeline. Produce one handbook per invocation. If the user wants both a full and a scoped handbook, run the workflow twice.

## Deterministic code vs. LLM judgment

Scripts own everything that can be parsed, validated, or rendered from structured data:

- PDF text, page map, candidate headings, caption candidates, image rectangles and thumbnails.
- Manifest schema validation, slugging, path resolution, coordinate-unit checks.
- Figure cropping, grouping, compositing, asset naming and preview generation.
- Markdown normalization: blank lines, list markers, caption bolding, section labels, trailing whitespace and final newline.
- Checks for anchors, image/link resolution, missing or unreferenced assets, placeholders and coverage.

The LLM owns everything that requires reading the paper or judging meaning:

- Scope, organizing principle and inclusion/exclusion.
- Unit boundaries, granularity, dependency order and chapter structure.
- Goal/principle text, Methods synthesis, Results interpretation and caption text.
- Which panel supports which claim, and which experimental context is necessary.
- Conflict resolution, "Not specified" decisions and scientific hedging.
- Final fidelity and plausibility audit.

**Rule of thumb:** if a transformation can be expressed as a parser or regex over structured artifacts, put it in a script; if it requires understanding the paper, leave it to the LLM. Formatting is split: the LLM writes content and semantic emphasis; scripts enforce canonical syntax and lint deviations.

## Workflow

### Phase 1 — Scope and source inventory

Run `scripts/pdf_inventory.py` to create page-anchored evidence:

```bash
python scripts/pdf_inventory.py \
  --pdf "path/to/paper.pdf" \
  --out "output/source"
```

It writes `pages.json`, `source_text.md`, `captions.json`, `methods_candidates.json`, `inventory_summary.md`, page thumbnails and a contact sheet. These are facts and candidates, not decisions. Read the Methods/Methods-equivalent section and the figure legends; build the assay and terminology map. Do not classify sections or figure types from the inventory alone.

### Phase 2 — Decompose into analytical units

Create `working/units.json` (see `templates/units_template.json`). A unit is one reproducible analytical operation that answers one question: inputs → transformation → outputs → figure evidence. Split when tools, parameters or claims differ; merge shared preprocessing into an upstream unit and cross-reference it. Order units by data dependency, not chronology.

For each unit record:

- `id`, `title`, `goal_principle`.
- `inputs`, `outputs`, `methods` (procedure summary).
- `tools` with names, versions and reported parameters.
- `evidence` (main figure panels) and `source_refs` (page/section/figure legend).
- `depends_on`, `unspecified`, `cautions`.

If no single data layer dominates, state the organizing principle explicitly, for example "spatial and single-cell atlas construction" or "complement-driven stromal niche." Do not force a multi-modal paper into a single-assay frame.

### Phase 3 — Draft the handbook

Use `templates/handbook_template.md` and `references/handbook-schema.md`. Draft from `units.json`, not from memory. Preserve tool names, versions, flags, sample sizes, filters and statistical tests exactly as reported. Mark missing details as "Not specified". Distinguish authors' statements from handbook synthesis.

Writing rules:

- No column-based hard wrapping. One paragraph, bullet or table row per line.
- One Methods bullet per procedure or decision.
- One Results block per unit: image block(s), then a bold caption label and a short interpretation.
- Cross-reference related units with `§N.M`.
- Put synthesis and caveats in the end matter, not silently in Methods.

### Phase 4 — Extract and embed cited panels

Create a per-paper manifest with `scripts/paper_manifest.py init`, then calibrate panel boxes:

```bash
python scripts/paper_manifest.py init --pdf "path/to/paper.pdf" --out "output/paper_manifest.json"
python scripts/calibrate_figure_boxes.py --manifest "output/paper_manifest.json" --figures "Figure 1"
```

Read the generated grid image, then write exact panel coordinates into the manifest. Use `page-crop` with PDF points for vector/multi-panel figures and `embedded-panel` with image pixels for raster figures. The script never chooses boxes.

Record the panels cited by each Results section in `units.json` (`result_blocks` or `evidence`). Build panel sets mechanically:

```bash
python scripts/build_panel_sets.py \
  --units "output/working/units.json" \
  --manifest "output/paper_manifest.json" \
  --write --backup
```

The rule is consecutive panel letters only. Within one Results section:

- `Fig. 2a–c` or `Fig. 2a` <br> `Fig. 2b` <br> `Fig. 2c` → one union rectangle `2a–c`.
- `Fig. 2a`, `Fig. 2c`, `Fig. 2d` → `2a` alone, then `2c–d` as one rectangle.
- Uncited panels inside a rectangle are acceptable.
- Panels from different figures remain separate image blocks.
- A full figure is used only for a whole-figure citation or a figure with no panel structure.

Extract and preview:

```bash
python scripts/extract_figures.py --manifest "output/paper_manifest.json" --previews
```

Check `_qa/previews/` visually. Re-crop any panel that includes a header, caption or cut-off content. Embed the panel/group assets in the relevant Results blocks with a caption label that matches the embedded panel set.

### Phase 5 — Normalize and verify

```bash
python scripts/format_handbook.py --handbook "output/handbook.md" --write --backup
python scripts/verify_handbook.py \
  --handbook "output/handbook.md" \
  --manifest "output/paper_manifest.json" \
  --units "output/working/units.json" \
  --source "output/source" \
  --strict
```

`format_handbook.py` is conservative: it never reflows prose. `verify_handbook.py` fails structural, caption, link and asset errors; it warns on heuristic coverage/fidelity issues. Fix all errors before delivery.

The verifier also checks that every caption matches its asset's panel set, that panel-specific claims do not use a full figure, and that every cited consecutive run has a matching image. If a scoped handbook shares an assets directory with a full handbook, pass `--reference-handbook full-handbook.md` so the unreferenced-asset check uses the union of both handbooks.

### Phase 6 — Delivery

Use this layout:

```
<output>/
├── <slug>.md
├── <slug>.assets/
├── source/                 # page text, captions, inventory, thumbnails
├── working/
│   ├── scope.md
│   ├── units.json
│   └── paper_manifest.json
├── qa_report.md
└── qa_report.json
```

Deliver the single Markdown handbook plus assets. Keep `source/` and `working/` as provenance. Do not put generated handbooks inside the skill directory.

## Output contract

Every handbook contains:

1. H1 title.
2. Source citation with DOI.
3. `Scope:` paragraph that states inclusion, exclusion and organizing principle.
4. `## Reading conventions`.
5. `## Chapter catalogue` with resolvable anchors.
6. H1 chapters, each with a chapter-level **Goal and principle.**
7. H2 units (`N.M Title`), each with **Goal and principle.**, **Methods**, **Results**.
8. `# Reproducibility and implementation notes` with `## A.` minimal analysis order, `## B.` resolution/threshold quick reference, `## C.` methodological cautions, `## D.` source-specific resources.
9. Bold figure-caption labels whose panel set matches the embedded asset; panel crops for specific citations and union rectangles for consecutive runs.

## Formatting contract

Full rules are in `references/formatting.md`. Summary:

- No hard wrapping; blank lines separate blocks.
- `**Goal and principle.**`, `**Methods**`, `**Results**` exactly.
- Caption labels bold and matched to the embedded set: `**Figure 1A**:`, `**Figure 3F–H**:`, `**Fig. 1b**:`, `**ED Fig. 1**:`.
- Consecutive cited panels use one union-rectangle asset; a citation gap splits the asset.
- Tool names bold at first mention; inline code only for literal flags, parameters, filenames and identifiers.
- Do not bold inline figure references; link them only when useful.
- One table row per line; no blank lines inside tables.
- No trailing whitespace; exactly one final newline.

## Scripts

| Script | Purpose | Deterministic? |
|---|---|---|
| `pdf_inventory.py` | Page text, candidate headings/captions, image rectangles, thumbnails | Yes; raw facts and candidates only |
| `paper_manifest.py` | Initialize and validate a per-paper figure manifest | Yes; no page/panel guessing |
| `calibrate_figure_boxes.py` | Render grids and detected image rectangles for manual coordinate entry | Yes; rendering only |
| `build_panel_sets.py` | Split cited panels into consecutive runs and write `panel_sets` | Yes; structured input only |
| `extract_figures.py` | Crop panels and union-rectangle panel sets; write `asset_index.json` and previews | Yes |
| `format_handbook.py` | Normalize safe Markdown formatting and bold Results captions | Yes; skips ambiguous cases |
| `verify_handbook.py` | Structure, anchors, assets, caption/panel matching, coverage, optional fidelity flags | Yes; hard errors vs. warnings |
| `prune_unreferenced_assets.py` | Report or move assets unreferenced by one or more handbooks; never deletes | Yes |
| `common.py` | Shared deterministic helpers | Yes |

There are deliberately no prose or Markdown rewriters for captions/links. The LLM authors those blocks; the formatter and verifier enforce the contract. If repeated formatting errors appear in evals, add a structured JSON-only renderer rather than a prose parser.

## Decision rules

- **Unit granularity:** if two steps use different tools, parameters, statistical tests or evidence panels, they are separate units.
- **Shared preprocessing:** one upstream unit; downstream units reference it with `§`.
- **Full vs. scoped:** full includes experimental and computational methods. A scoped computational handbook includes data-generation details only where needed to interpret inputs; it explicitly excludes wet-lab protocols.
- **Ambiguity:** preserve conflicting definitions, denominators and recurrence thresholds as cautions rather than reconciling them silently.
- **Causal language:** do not upgrade correlational associations from figures. Mark perturbation-supported claims separately.
- **Missing parameters:** "Not specified" means the paper does not state it. Never substitute a default unless the paper or a cited protocol explicitly supplies it.
- **Figures:** crop the panels cited by each Results section. Consecutive panel letters form one union rectangle; a citation gap splits the crop. Uncited panels inside a rectangle are acceptable. Use a full figure only for a whole-figure citation or a figure with no panels. Cite supplementary figures/tables by label if they are not in the provided PDF.

## Verification gates

Before considering the handbook complete:

1. **Execution:** all scripts ran; no errors; formatter is idempotent.
2. **Data validity:** every image resolves and opens; no missing or unreferenced assets; anchors resolve; no placeholders.
3. **Structural completeness:** every chapter has a goal; every unit has Goal/principle, Methods and Results; end matter A–D exists.
4. **Panel/citation consistency:** each caption label matches the asset's panel set; every cited consecutive run has one matching image; full figures are not used for panel claims; citation gaps are not bridged.
5. **Coverage:** every main figure is represented in the manifest and either appears in a unit or is explicitly excluded; every Methods heading is mapped to a unit or exclusion.
6. **Fidelity:** spot-check tool versions, parameters and numbers against the source; audit every "Not specified".
7. **Scientific plausibility:** check causal language, denominators, recurrence definitions and platform mixing.

## Reference map

- `references/recomposition.md` — how to turn a paper into units, dependencies and a chapter structure.
- `references/handbook-schema.md` — exact section and formatting contract.
- `references/formatting.md` — line breaks, bold, inline code, italics, tables and captions.
- `references/pdf-figure-pipeline.md` — manifest schema, calibration, extraction and fallbacks.
- `references/qa-checklist.md` — coverage, fidelity, figure QA and sign-off.
- `references/examples.md` — condensed Xu 2022 and Dugué 2026 worked examples.
- `templates/handbook_template.md`, `templates/units_template.json`, `templates/paper_manifest.example.json`.

## Environment and safety

- Python 3.10+ with PyMuPDF and Pillow; no network access is required for the core workflow.
- Process PDFs locally; do not upload papers or unpublished data to external services.
- Figure extraction is allowed by the skill, but the user is responsible for figure reuse rights. Record `figure_rights: user-confirmed` in the manifest.
- Destructive operations are opt-in: `extract_figures.py --force` overwrites, `prune_unreferenced_assets.py --apply` moves files to a backup, and `format_handbook.py --backup` preserves the prior version.
- Never delete source PDFs, assets or handbooks. Move them to a timestamped backup instead.
