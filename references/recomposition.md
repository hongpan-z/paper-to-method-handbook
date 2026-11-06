# Recomposing a paper into a methods handbook

## Purpose

A methods handbook reconstructs the paper's analytical workflow so that a reader can understand, audit, or re-implement it. It is not a summary and not a results digest. The organizing question is: **what was done, in what order, with which inputs and settings, and which figure panel demonstrates the outcome?**

The handbook must be source-grounded. Every Methods statement should be traceable to the paper's Methods, a figure legend, a supplementary table, or a cited protocol. If the source is silent, say so.

## 1. Scope contract

Record these decisions in `working/scope.md` before drafting:

- **Requested scope:** complete methods, or a named method family/data layer.
- **Organizing principle:** a data layer (for example, the Hi-C contact matrix) or an analytical/biological workflow (for a multi-modal paper with no dominant layer).
- **Experimental content:** full methods include experimental and computational procedures. A computational-only request includes only the experimental background needed to interpret inputs and validation.
- **Exclusions:** assays, results, supplements, or validation experiments that are out of scope. State them explicitly.
- **Figure policy:** extract and embed the panels cited by each Results section. A single cited panel is cropped alone; consecutive cited panels from one figure form one union rectangle. A citation gap splits the crop. Uncited panels inside a rectangle are acceptable. Different figures use separate image blocks. A full figure is used only for a whole-figure citation or a figure with no panel structure.
- **Unit of evidence:** main figure panels, supplementary panels, tables, or external code/data resources.

A complete methods request defaults to including experimental methods. A computational request should not be padded with bench protocols; include them only where they explain an input, a confound, or a validation step. This is one uniform workflow with a scope filter, not two separate pipelines. Produce one handbook per invocation; if both scopes are needed, run the workflow twice.

## 2. Source inventory

Use `pdf_inventory.py` to produce page-anchored text and candidates. Then read:

- The Methods or STAR Methods section.
- Every main figure legend.
- The key resources table (for tools, antibodies, plasmids, software versions).
- Supplementary methods/tables if available.
- Data/code availability statements.

Build a source map:

| Source artifact | What it supplies |
|---|---|
| Methods section | Procedure, parameters, versions, sample sizes |
| Figure legends | Statistical tests, panel-to-claim mapping |
| Key resources table | Tool names, versions, catalog numbers |
| Supplementary tables | Cohort details, DEG lists, primers, antibodies |
| Data/code statements | Accessions, repositories, reusable inputs |

Do not classify sections or figure types from the inventory alone. The LLM reads the source and decides.

## 3. Unit decomposition

A unit is one reproducible analytical operation that answers one question:

```
inputs → transformation → outputs → evidence
```

Good unit boundaries:

- Split when tools, parameters, statistical tests or evidence panels differ.
- Merge shared preprocessing into an upstream unit; downstream units reference it.
- Keep experimental and computational steps separate when they answer different questions.
- Treat a perturbation/validation experiment as its own unit if it tests a specific claim.
- Do not create one unit per reagent or per tool mention.

Example units from a Hi-C paper:

- Hi-C preprocessing and matrix generation.
- A/B compartment inference.
- Differential compartment switching.
- TAD calling and boundary comparison.
- Loop calling and differential looping.
- Loop anchoring to promoters/enhancers.
- SV-aware neo-loop calling.
- Perturbation and validation.

Example units from a multi-modal spatial paper:

- Human cohort and tissue selection.
- snRNA-seq generation and preprocessing.
- Spatial transcriptomics generation and preprocessing.
- Cell-type annotation and composition.
- Differential expression and pathway activity.
- Cell-cell communication.
- CODEX imaging and co-localization.
- Mouse models and C3KO validation.

## 4. Dependency ordering

Order units by data dependency, not by the order experiments appear in the paper. The reader should be able to follow the workflow from raw inputs to interpreted outputs.

A useful dependency chain:

1. Samples, models and data generation.
2. Preprocessing and quality control.
3. Integration and annotation.
4. Composition and differential expression.
5. Regulatory/program-level analysis.
6. Communication or spatial relationship analysis.
7. Perturbation and validation.
8. Statistics and synthesis.

If a unit depends on a shared upstream step, reference it with `§N.M` instead of repeating the procedure.

## 5. Organizing principle for multi-modal papers

Not every paper has a single organizing data layer. When several assays contribute equally:

- Choose the biological/analytical workflow as the organizing principle, for example "spatial atlas construction" or "complement-driven stromal niche."
- State the choice in the Scope paragraph.
- Group units by analytical stage, not by assay list.
- Keep cross-assay integration units explicit (for example, deconvolution, co-localization, multi-modal comparison).
- Do not force all methods into a single assay chapter.

## 6. Epistemic rules

These rules prevent the handbook from becoming more confident than the paper:

- **No invented defaults.** "Not specified" means the paper does not state it. Do not fill gaps with tool defaults.
- **Preserve conflicts.** Different denominators, recurrence definitions, thresholds or sample subsets should be reported as cautions, not merged.
- **Separate reported from synthesized.** If you provide an executable order or threshold table, label it as an implementation synthesis.
- **Do not upgrade causality.** A loop–expression or ligand–receptor association is correlational unless perturbation evidence supports it.
- **Respect platform boundaries.** Do not pool Visium, Visium HD and CODEX values without platform-aware normalization.
- **Keep supplementary boundaries visible.** If a supplementary figure or table is unavailable, cite it by label and say it was not reproduced.

## 7. Drafting from units

Draft from `units.json`, not from memory. Each unit becomes:

- a `Goal and principle` paragraph (why and how),
- Methods bullets (procedure, tools, versions, parameters, filters, statistics),
- Results blocks (panel/group image, bold caption matching the embedded panel set, one-line interpretation).

Keep the Methods section operational. Use exact tool names and versions. Put flags and literal parameters in backticks. Put tool names in bold. Put synthesis, caveats and implementation order in the end matter.

## 8. Common failure modes

- A method list with no dependency structure.
- A summary that omits parameters and filters.
- One giant "bioinformatics" chapter that mixes preprocessing, statistics and interpretation.
- Repeating shared preprocessing in every unit.
- Silently merging different recurrence definitions or denominators.
- Embedding a figure without saying what claim it supports.
- Filling unspecified parameters with defaults.
- Treating a correlational panel as causal evidence.
- Omitting the end matter that makes the workflow auditable.
