# Paper to Method Handbook

Turn a published paper PDF into a source-grounded, method-centered Markdown handbook.

## What it does

- Reconstructs a paper's methods as reproducible analytical units ordered by data dependency, not paper chronology.
- Records tool names, versions, flags, filters, sample sizes and statistical tests.
- Crops and embeds the figure panels cited in each Results section.
- Produces a single Markdown handbook plus its figure assets.
- Supports complete-methods-based reconstruction, or a scoped workflow.

It is not a paper summary, a peer-review tool, or a results-only digest.

## Install

Requires Node.js 22.20+ for the skills CLI.

```bash
npx skills add hongpan-z/paper-to-method-handbook --skill paper-to-method-handbook -a opencode --copy
```

Restart OpenCode after installing.

## Use

Ask your agent:

> Build a complete methods handbook from this paper PDF.

Or scope it:

> Extract only the computational data-analysis workflow from this paper and keep the necessary experimental background.

Or generate a text-only handbook:

> Build a methods handbook from this paper without extracting figures; mark it text-only and record the limitation.

The skill writes:

```text
<output>/
├── <slug>.md
└── <slug>.assets/
```

A text-only handbook contains only `<slug>.md`. Working files are temporary and removed after verification.

## Design

- **What the handbook looks like.** The handbook starts with the paper citation and scope, then moves through chapters and smaller units in a logical analysis order. Each chapter states its goal, and each unit explains what it does, how it is done, and what evidence supports it. It ends with reproducibility notes covering the analysis order, important settings, cautions, and source resources.
- **What the scripts do.** Scripts handle the mechanical work: reading the PDF, organizing and cropping figures, formatting the Markdown, checking the result, and removing temporary work files. They rely on PyMuPDF and Pillow for PDF and image handling. Users do not need to install anything manually; the agent checks the environment and handles setup with permission.
- **What the agent handles.** The agent decides the scope, how the methods are broken into units and ordered, how the paper is interpreted, and which figures support each claim. It also performs the final accuracy and plausibility review.
- **How figures are handled.** Figures come from the panels cited in each Results section. A single panel is cropped on its own; consecutive panels are grouped into one image; gaps in a citation remain separate. Whole figures are used only when the citation refers to the whole figure. Assets are capped at 1600 px on the long edge and saved as optimized PNG, and only changed figures are re-cropped. A text-only handbook is also supported.

## License

MIT. See [LICENSE](LICENSE).
