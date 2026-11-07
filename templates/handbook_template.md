# {{HANDBOOK_TITLE}}

Source paper: {{AUTHORS}}. *{{PAPER_TITLE}}.* {{JOURNAL}} {{VOLUME}}, {{PAGES}} ({{YEAR}}). DOI: [{{DOI}}](https://doi.org/{{DOI}}).

Scope: {{SCOPE_PARAGRAPH}} The handbook is source-grounded: "Not specified" means the paper does not state a setting, not that a default is recommended. Main-text figures are embedded; Supplementary Figures and Tables are cited by label where the main PDF does not contain them.

## Reading conventions

- **Goal and principle** briefly explains why the analysis is performed and how it works (typically 2–4 sentences).
- **Methods** documents the actual procedure, including sample sizes, tools and versions, filtering and classification logic, comparison design, statistical analyses, and parameters explicitly reported in the paper. "Not specified" means no setting is stated in the paper.
- **Results** links the unit to individual figure panels and summarizes the finding the panel supports.
- {{PAPER_SPECIFIC_CONVENTION}}

## Chapter catalogue

1. [Chapter 1. {{CHAPTER_1_TITLE}}](#chapter-1-{{CHAPTER_1_SLUG}}) — {{CHAPTER_1_ONE_LINE}}.
2. [Chapter 2. {{CHAPTER_2_TITLE}}](#chapter-2-{{CHAPTER_2_SLUG}}) — {{CHAPTER_2_ONE_LINE}}.

---

# Chapter 1. {{CHAPTER_1_TITLE}}

**Goal and principle.** {{CHAPTER_1_GOAL}}

## 1.1 {{UNIT_1_1_TITLE}}

**Goal and principle.** {{UNIT_1_1_GOAL}}

**Methods**
- {{PROCEDURE_OR_DECISION}}
- **{{TOOL_NAME_VERSION}}**: {{WHAT_IT_DOES}}; `{{FLAG_OR_PARAMETER}}`; {{FILTERS_AND_THRESHOLDS}}.
- {{INPUTS_OUTPUTS_SAMPLE_SIZES}}
- Not specified: {{MISSING_SETTINGS}}.

**Results**
- {{WHAT_THE_EVIDENCE_SHOWS}}

![Figure 1A–B]({{SLUG}}.assets/figure01a-b.png)

**Figure 1A–B**: {{PANEL_LEVEL_INTERPRETATION}}

## 1.2 {{UNIT_1_2_TITLE}}

**Goal and principle.** {{UNIT_1_2_GOAL}}

**Methods**
- {{PROCEDURE_OR_DECISION}}

**Results**
- {{TEXT_ONLY_RESULT_IF_NO_PANEL}}

---

# Reproducibility notes

## A. Minimal executable analysis order

The following is an implementation synthesis of the dependencies documented above, not a command script supplied by the authors:

1. {{STEP_1}}
2. {{STEP_2}}

## B. Key parameters and thresholds

| Analysis | Key parameters or settings | Notes |
|---|---|---|
| {{ANALYSIS}} | {{SETTINGS}} | {{NOTES}} |

## C. Methodological cautions when adapting this handbook

- {{CAUTION}}

## D. Source-specific resources

- Article: [{{SHORT_CITATION}}]({{DOI_URL}}).
- Data accessions: {{ACCESSIONS}}.
- Code repositories: {{REPOSITORIES}}.
- Supplementary items: {{SUPPLEMENTARY_ITEMS}}.

*End of handbook.*
