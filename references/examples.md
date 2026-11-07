# Worked examples

Two case studies are available in the mother project:

- `method_based_handbook/HiC_Centered_Analysis_Handbook_Xu_2022.md` — a focused, Hi-C-centered handbook.
- `method_based_handbook/dugue-2026/dugue-2026.md` — a complete experimental + computational spatial/single-cell handbook.
- `method_based_handbook/dugue-2026/dugue-2026-computational.md` — a scoped computational variant.

## Xu 2022: Hi-C-centered handbook

**Organizing principle:** the Hi-C contact matrix is the central data layer; companion assays are included where they supply inputs or test predictions.

**Structure:** 8 chapters, 36 units, 8 chapters with chapter-level goals, then end matter A–D.

**What it does well:**

- Orders units by analytical dependency: preprocessing → compartments → TADs → loops → stripes → SVs → methylation/CTCF → perturbation.
- Keeps shared preprocessing in one unit and cross-references it.
- Preserves denominator and recurrence-definition conflicts in end matter C.
- Marks ambiguous statements literally, for example the MAPS "FDR of 2" without inventing units.
- Separates the authors' workflow from the implementation synthesis in end matter A.

**Formatting note:** the example was updated to use bold caption labels, for example:

```
![Fig. 1b](HiC_Centered_Analysis_Handbook_Xu_2022.assets/fig01b.png)

**Fig. 1b**: Example integrated genomic browser view (Hi-C, ATAC, H3K27ac, H3K27me3, CTCF, RNA and WGBS) from the same patient.
```

## Dugué 2026: multi-modal spatial handbook

**Organizing principle:** a multi-modal spleen atlas workflow rather than a single data layer. The paper combines human snRNA-seq, human Visium, mouse scRNA-seq, mouse Visium HD, CODEX, organoids and C3KO models.

**Structure:** 8 chapters, 38 units in the full handbook; 7 chapters, 30 units in the scoped computational handbook. Both are test artifacts from the same uniform workflow; the skill's default is one handbook per invocation.

**What it does well:**

- States the organizing principle in the Scope because no single assay dominates.
- Includes full experimental methods by default: mouse models, C3KO, histology, organoids, co-culture and ELISA.
- Uses panel-level crops and consecutive-run union rectangles for a Cell Press layout with vector and raster panels; captions match the embedded panel set.
- Keeps computational units separate from bench protocols and cross-references shared inputs.
- Records "Not specified" for missing parameters such as Harmony PCs, spot QC thresholds and CODEX arcsinh cofactor.
- Demonstrates the scoped computational style without a separate pipeline: the scope filter removes wet-lab units and keeps necessary background.

**Panel grouping example:**

- `Figure 3F–H` is one union rectangle.
- `Figure 1B–C` is one union rectangle.
- `Figure 2A–E` and `Figure 2H` are separate assets because the citation set is not one consecutive run.
- `Figure 7A–E` and `Figure 7F–I` are separate blocks; they are not concatenated across the gap.

**Scoped variant:**

- Keeps Chapters 1–6 and the statistics unit.
- Removes the wet-lab chapter and the CODEX antibody-conjugation protocol.
- Rewrites end matter A as a computational order.
- Adds a caution that wet-lab protocols are out of scope.
- Reuses the same panel assets; verify with `--reference-handbook` when the assets directory is shared.

## Patterns to copy

- Put the organizing principle in the Scope, not only in a chapter.
- Use unit IDs and `§N.M` cross-references.
- Put tool names in bold and literal parameters in backticks.
- Use one Results block per unit and a bold caption label.
- Keep the Reproducibility notes: implementation order, key parameters and thresholds, cautions, resources.

## Patterns to avoid

- A chronological list of experiments.
- One "bioinformatics" chapter that mixes preprocessing, statistics and interpretation.
- Repeating shared preprocessing in every unit.
- Silently merging conflicting definitions or denominators.
- Filling missing parameters with defaults.
- Treating a correlational panel as causal evidence.
- Embedding a figure without naming the claim it supports.
