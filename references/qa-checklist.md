# QA checklist

Run the scripts, then perform the judgment checks the scripts cannot make.

## 1. Execution

- [ ] `check_environment.py` passed, or the text-only fallback is documented.
- [ ] `pdf_inventory.py` ran on the intended PDF.
- [ ] The manifest validates with `paper_manifest.py validate --strict`.
- [ ] `extract_figures.py` ran without unresolved warnings.
- [ ] `format_handbook.py --check` is idempotent (no changes).
- [ ] `verify_handbook.py --strict` has 0 errors and 0 warnings, or every warning is explained in the final response.
- [ ] `finalize_output.py --apply` ran, or the user requested `--keep-work`.

## 2. Data validity

- [ ] Every image link resolves and opens.
- [ ] No missing assets.
- [ ] No unreferenced assets unless intentionally kept for a documented reason.
- [ ] Catalogue anchors resolve.
- [ ] No `TODO`, `TBD`, `XXX`, `FIXME` or `???`.
- [ ] Exactly one final newline; no trailing whitespace.

## 3. Structure

- [ ] H1 title and source citation with DOI.
- [ ] `Scope:` paragraph states inclusion, exclusion and organizing principle.
- [ ] `## Reading conventions` and `## Chapter catalogue` exist.
- [ ] Every chapter has a chapter-level **Goal and principle.**
- [ ] Every `N.M` unit has **Goal and principle.**, **Methods** and **Results**.
- [ ] Reproducibility notes have A (minimal analysis order), B (key parameters and thresholds), C (cautions), D (resources).
- [ ] Figure captions are bold and use the paper's figure naming.

## 4. Coverage

- [ ] For a text-only handbook, the final response states that figure coverage was intentionally skipped and how the text was obtained.
- [ ] Every main figure is in the manifest and either appears in a unit or is explicitly excluded.
- [ ] Every Methods heading is mapped to a unit or listed in the exclusions.
- [ ] Shared preprocessing is described once and cross-referenced.
- [ ] No unit is a single tool mention without an analytical purpose.
- [ ] Every Results section's cited panels are covered by a matching panel/group asset.
- [ ] Consecutive cited panels form one union rectangle; citation gaps split into separate crops.
- [ ] Uncited panels inside a rectangle are allowed and do not fail verification.
- [ ] Full figures are used only for whole-figure citations or figures with no panels.
- [ ] The scoped (if any) handbook states what experimental content was excluded; if it shares assets with a full handbook, verify with `--reference-handbook`.

## 5. Fidelity audit

Spot-check against the source:

- [ ] Tool names and versions.
- [ ] Exact flags and parameter values.
- [ ] Sample sizes, cohort definitions and inclusion criteria.
- [ ] Statistical tests and correction methods.
- [ ] Recurrence/denominator definitions.
- [ ] Every "Not specified" claim.
- [ ] Every number that appears in Methods.

Investigate any number flagged by `verify_handbook.py --fidelity`. The script is heuristic; absence of a warning does not prove fidelity.

## 6. Scientific plausibility

- [ ] Correlational claims are not written as causal.
- [ ] Perturbation evidence is distinguished from association.
- [ ] Different denominators or definitions are preserved as cautions.
- [ ] Cross-platform comparisons (Visium/Visium HD/CODEX) are qualified.
- [ ] Module scores are not described as direct pathway flux.
- [ ] Ligand–receptor or loop–expression associations are hedged.
- [ ] The handbook does not claim that a successful script run establishes biological validity.

## 7. Figure QA

- [ ] Text-only handbooks mark figure QA as not applicable and explain why.
- [ ] Previews were inspected.
- [ ] No caption or header is included in a figure crop.
- [ ] No panel is cut off.
- [ ] Panel crops and union rectangles preserve the cited run's order.
- [ ] Caption labels match the asset index's panel sets.
- [ ] Uncited panels inside a rectangle were checked and are acceptable.
- [ ] Low-resolution or tiny images are noted.
- [ ] Figure reuse rights were confirmed by the user.

## 8. Sign-off

- [ ] Verification results, figure QA, known limitations and regression checks are summarized for the user; `qa_report.md` and `qa_report.json` are kept only with `--keep-work`.
- [ ] Temporary source, working, calibration, preview, backup and manifest files are removed by default.
- [ ] The handbook is delivered as a single Markdown file plus its assets directory, or as a single Markdown file for a text-only handbook.
