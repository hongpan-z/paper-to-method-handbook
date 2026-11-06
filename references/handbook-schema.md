# Handbook schema

Use this outline exactly. The verifier checks the required sections and anchors.

## Front matter

```
# <Handbook title>

Source paper: <Authors>. *<Title>.* <Journal> <Volume>, <Pages> (<Year>). DOI: [<doi>](https://doi.org/<doi>).

Scope: <One paragraph: what is reconstructed, the organizing principle, what is included/excluded, and the evidence policy. State that "Not specified" means the paper does not state a setting.>

## Reading conventions

- **Goal and principle** briefly explains why the analysis is performed and how it works (typically 2–4 sentences).
- **Methods** documents the actual procedure, including sample sizes, tools and versions, filtering and classification logic, comparison design, statistical analyses, and parameters explicitly reported in the paper. "Not specified" means no setting is stated in the paper.
- **Results** links the unit to individual figure panels and summarizes the finding the panel supports.
- <Any paper-specific conventions: figure naming, panel qualifiers, correlational language, supplementary availability.>

## Chapter catalogue

1. [Chapter 1. <Title>](#chapter-1-<slug>) — <one-line description>.
2. [Chapter 2. <Title>](#chapter-2-<slug>) — <one-line description>.
...
```

The catalogue anchors must resolve to the chapter headings. Use lowercase, hyphenated GitHub-style anchors.

## Chapter and unit structure

```
---

# Chapter 1. <Chapter title>

**Goal and principle.** <What this chapter establishes and why it is a dependency.>

## 1.1 <Unit title>

**Goal and principle.** <Why this operation is performed and how it works.>

**Methods**
- <Procedure or decision.>
- <Tool name and version>: <what it does>; `<flag>`; <parameters>.
- <Inputs, filters, thresholds, sample sizes, comparison design.>
- Not specified: <missing settings, if any>.

**Results**
- <What the evidence shows.>

![Figure 1A–B](<slug>.assets/figure01a-b.png)

**Figure 1A–B**: <Interpretation of the embedded panels.>

## 1.2 <Unit title>

...
```

### Unit requirements

- Heading level 2, numbered `N.M`.
- **Goal and principle.** present.
- **Methods** present; at least one bullet or paragraph.
- **Results** present; may be text-only if no panel is available, but explain why.
- If a figure is embedded, the caption label must be bold and followed by a colon.
- The caption label must match the embedded asset's panel set. A full figure is allowed only for a whole-figure citation or a figure with no panel structure.

### Methods bullets

Use one bullet per procedure, decision or parameter group. Preserve:

- tool name and version,
- exact flags and parameter values,
- sample sizes and cohort definitions,
- filtering logic and thresholds,
- statistical tests and correction methods,
- comparison design,
- data accessions.

Put literal machine-readable tokens in backticks. Put tool names in bold at first mention. Do not use inline code for gene names, units or ordinary numbers.

### Results blocks

A Results block is either:

1. **Panel-supported:**
   ```
   ![Figure 1A–B](assets/figure01a-b.png)

   **Figure 1A–B**: One to four sentences describing the embedded panels and the claim they support.
   ```
2. **Text-only:**
   ```
   **Results**
   - The main-text figures do not present a standalone panel for this unit; the output supplies the input to §5.3.
   ```

Panel grouping rules:

- One cited panel → one panel asset.
- A consecutive run such as `A–C` or `A` <br> `B` <br> `C` → one union-rectangle panel set.
- A citation gap such as `A`, `C`, `D` → `A` alone and `C–D` as one panel set.
- Uncited panels inside the rectangle are acceptable; do not fail them.
- Panels from different figures use separate image blocks.
- A full figure is used only for a whole-figure citation or a figure with no panel structure.

The caption label must list the cited panels embedded in the asset, for example `**Figure 1A–C**:`.

## End matter

```
# Reproducibility and implementation notes

## A. Minimal executable analysis order

<Numbered synthesis of dependencies. Label it as a synthesis, not an authors' script.>

## B. Resolution and key-threshold quick reference

| Analysis | Resolution or principal settings | Notes |
|---|---|---|
| ... | ... | ... |

## C. Methodological cautions when adapting this handbook

- <Denominator, recurrence, platform, causal-language or missing-parameter cautions.>

## D. Source-specific resources

- Article: [<citation>](<doi URL>).
- Data accessions: ...
- Code repositories: ...
- Supplementary items: ...
```

## Cross-references

- Use `§N.M` for related units.
- Use `Figure 1A`, `Figure S4`, `Table S6` in prose.
- Do not bold inline figure references.
- Do not create a second numbering system.

## Minimal example

```
## 2.3 Differential loop calling

**Goal and principle.** Identify loops whose probability differs between AML and normal samples. A mixture model separates true changes from background variability.

**Methods**
- **diffPeakachu**: compare each AML sample with each of four HSPC controls; calculate fold changes of Peakachu probabilities.
- Fit a Gaussian mixture model; FDR 0.05. Call gains/losses using the consensus of all four comparisons.
- Not specified: a universal probability cutoff beyond the two-model intersection.

**Results**
- Figure 2A shows the number of AML-specific loops per patient.

![Figure 2](assets/figure02.png)

**Figure 2**: AML and subtype-specific chromatin loops. (A) AML-specific loop counts. (B) APA validation.
```
