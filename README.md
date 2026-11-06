# Paper to Method Handbook

Turn a published paper PDF into a source-grounded, method-centered Markdown handbook.

## What it does

- Reconstructs a paper's methods as reproducible analytical units ordered by data dependency, not paper chronology.
- Records tool names, versions, flags, filters, sample sizes and statistical tests.
- Crops and embeds the figure panels cited in each Results section.
- Produces a single Markdown handbook, figure assets, source inventory, working units and a QA report.
- Supports complete-methods-based reconstruction, or a scoped workflow.

It is not a paper summary, a peer-review tool, or a results-only digest.

## Install

Requires Node.js 22.20+ for the skills CLI.

```bash
npx skills add hongpan-z/paper-to-method-handbook --skill paper-to-method-handbook -a opencode --copy
```

Global install:

```bash
npx skills add hongpan-z/paper-to-method-handbook --skill paper-to-method-handbook -a opencode -g --copy -y
```

### Manual install

Clone the repository and copy the skill into your OpenCode skills directory.

macOS / Linux:

```bash
git clone https://github.com/hongpan-z/paper-to-method-handbook.git
mkdir -p .opencode/skills
cp -R paper-to-method-handbook .opencode/skills/
```

Windows PowerShell:

```powershell
git clone https://github.com/hongpan-z/paper-to-method-handbook.git
New-Item -ItemType Directory -Force -Path ".opencode\skills" | Out-Null
Copy-Item -Recurse ".\paper-to-method-handbook" ".opencode\skills\paper-to-method-handbook"
```

Project skills live in `.opencode/skills/paper-to-method-handbook/`; global skills live in `~/.config/opencode/skills/paper-to-method-handbook/`. Restart OpenCode after installing.

### Python dependencies

```bash
python -m pip install -r scripts/requirements.txt
```

Requires Python 3.10+ with PyMuPDF and Pillow.

## Use

Ask your agent:

> Build a complete methods handbook from this paper PDF.

Or scope it:

> Extract only the computational data-analysis workflow from this paper and keep the necessary experimental background.

The skill writes:

```text
<output>/
├── <slug>.md
├── <slug>.assets/
├── source/
├── working/
├── qa_report.md
└── qa_report.json
```

## Figure handling

Figures are extracted at panel level by default. A single cited panel is cropped alone; consecutive cited panels are cropped as one union rectangle. A citation gap splits the crop. Uncited panels inside a rectangle are acceptable. Different figures use separate image blocks. Full figures are used only for whole-figure citations or figures without panels.

## Design

Deterministic scripts handle PDF inventory, figure cropping, Markdown formatting and verification. The agent handles scope, unit decomposition, interpretation and scientific judgment.

## License

MIT. See [LICENSE](LICENSE).
