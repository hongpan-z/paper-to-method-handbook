# PDF figure pipeline

The pipeline is manifest-driven. Scripts crop, render and validate; the LLM chooses figure pages, panel boxes and which panels support which claim.

## Default figure policy

Extract **panels**, not whole figures:

1. For each Results section, collect the cited panels per figure.
2. Sort by panel letter.
3. Split into maximal consecutive runs.
4. One panel → single-panel crop.
5. Two or more consecutive panels → one union-rectangle crop.
6. A citation gap splits the crop. `2a, 2c, 2d` becomes `2a` alone and `2c–d` as one rectangle.
7. Uncited panels inside a union rectangle are acceptable.
8. Panels from different figures use separate image blocks.
9. A full figure is used only for a whole-figure citation or a figure with no panel structure.

Examples:

| Citations in one Results section | Output |
|---|---|
| `Fig. 2a–c` | `2a–c` union rectangle |
| `Fig. 2a` <br> `Fig. 2b` <br> `Fig. 2c` | `2a–c` union rectangle |
| `Fig. 2a`, `Fig. 2c`, `Fig. 2d` | `2a`; `2c–d` |
| `Fig. 2a`, `Fig. 2b`, `Fig. 2d` | `2a–b`; `2d` |
| `Fig. 2a` only | `2a` |

## Manifest schema

```json
{
  "slug": "paper-2026",
  "paper": {
    "title": "...",
    "doi": "...",
    "pdf": "../papers/paper.pdf",
    "page_count": 33
  },
  "handbook": "paper-2026.md",
  "assets_dir": "paper-2026.assets",
  "figure_rights": "user-confirmed",
  "default_dpi": 300,
  "padding_pt": 6,
  "padding_px": 15,
  "figures": [],
  "panel_sets": [],
  "groups": []
}
```

### Figure entries

```json
{
  "id": "Figure 1",
  "page": 4,
  "mode": "page-crop",
  "units": "pt",
  "panels": {
    "A": [85, 95, 320, 230],
    "B": [324, 95, 562, 230],
    "C": [85, 270, 160, 455]
  }
}
```

- `units`: `pt` for PDF page coordinates, `px` for embedded-image pixels. Do not mix units inside a figure.
- `image_index` or `image_xref` selects an embedded image for `embedded-panel` mode. If omitted, the largest image on the page is used.
- `dpi` overrides `default_dpi` for page crops.
- `padding_pt` / `padding_px` override the manifest defaults.
- `panels` keys are letters (`A`, `B`, `a`, `b`) or `""` for a full figure. Asset names are derived from the figure id and panel.

### Panel sets

A panel set is a consecutive run of cited panels, cropped as one union rectangle:

```json
{
  "id": "Figure 3F-H",
  "figure": "Figure 3",
  "panels": ["F", "G", "H"],
  "filename": "figure03f-h.png"
}
```

- `panels` must be a list of at least two consecutive panel letters from the same figure.
- The extractor computes the union of the panel boxes and crops once. Uncited panels inside the rectangle are allowed.
- A non-consecutive set such as `["A","C"]` is invalid. Split it into separate sets or single panels.
- `filename` is optional; if omitted it is derived from the figure and run.
- `build_panel_sets.py` can generate these entries from structured unit citations.

### Custom groups

Custom concatenation or cross-panel layouts are an explicit fallback, not the default:

```json
{
  "id": "Figure 1A-C",
  "from": ["Figure 1A", "Figure 1B", "Figure 1C"],
  "mode": "concat",
  "layout": "horizontal",
  "gap": 24,
  "filename": "figure01a-c.png"
}
```

`union-crop` is also available, but `panel_sets` is preferred because it records the cited run explicitly.

## Asset index

`extract_figures.py` writes `asset_index.json` next to the assets:

```json
{
  "figure03f-h.png": {
    "kind": "panel-set",
    "figure": "Figure 3",
    "panels": ["F", "G", "H"],
    "mode": "page-crop",
    "page": 7,
    "box": [88, 462, 562, 548]
  }
}
```

Kinds are `panel`, `panel-set`, `full` and `group`. The verifier uses the index to check that a caption label matches the embedded set and that a full figure is not used for a panel claim.

## Calibration workflow

1. Create an empty manifest with `paper_manifest.py init`.
2. Add figure entries with page numbers and panel boxes.
3. Run `calibrate_figure_boxes.py` to render a coordinate grid and detected image rectangles.
4. Read the grid image. Note the coordinates of each panel boundary.
5. Write the panel boxes into the manifest. Run calibration again to confirm.
6. Record cited panels in `units.json`.
7. Run `build_panel_sets.py --write --backup`.
8. Run `extract_figures.py --previews`.
9. Inspect `_qa/previews/`. Re-crop if a header, caption or panel is cut off.

The calibration script never guesses boxes. If a figure has no embedded image and is vector-rendered, use `page-crop`.

## Choosing a mode

| Situation | Mode |
|---|---|
| Multi-panel Nature-style figure with vector elements | `page-crop` with panel boxes |
| Cell Press figure with a page-spanning image | `page-crop` or `embedded-panel` |
| Full-page raster figure with a caption | `page-crop` (exclude caption) |
| Figure assembled from many small raster images | `page-crop` or `embedded-panel` per panel |
| Consecutive cited panels | `panel_sets` (union rectangle) |
| Non-rectangular custom layout | `groups` with `concat` as an explicit fallback |

## Coordinate units and clamping

- Page crops use PDF points: the page width/height from `page.rect`.
- Embedded panels use image pixels: the width/height from `get_image_info`.
- The extractor clamps boxes to page/image bounds and prints a warning. Fix the manifest rather than relying on clamping.
- White margins are not removed automatically. Use padding and explicit boxes.

## Non-ASCII paths

The PDF may have accents or spaces in its filename. Keep the manifest path as UTF-8 and use a slug for the output directory and assets. Do not derive filenames from the raw PDF stem.

## Fallbacks

- No embedded image: use `page-crop`.
- Caption/header inside the crop: reduce the box using the caption bounding box from `captions.json`.
- Panel boundaries unclear: crop the whole figure and state that panel-level extraction was not possible; record the reason in the QA report.
- A supplementary figure is not in the PDF: cite it by label and state that it was not reproduced.
- Figure extraction fails: keep a textual Results reference and record the failure in the QA report; do not block the handbook.
- A scoped handbook shares assets with a full handbook: verify with `--reference-handbook full-handbook.md` so the unreferenced-asset check uses the union.
