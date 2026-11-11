"""Create and validate a per-paper figure manifest.

The manifest is the single source of truth for figure pages, panel boxes,
consecutive panel sets, asset names and custom groups. It contains no semantic
guesses: panel boxes are calibrated by the agent, and panel sets are validated
for consecutive panel letters.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import pymupdf

from common import (
    asset_filename,
    expand_panel_letters,
    group_filename,
    panel_set_filename,
    parse_figure_label,
    read_json,
    safe_stem,
    split_consecutive_runs,
    valid_box,
    write_json,
)

MODES = {"page-crop", "embedded-panel", "embedded-full"}
UNITS = {"pt", "px"}
GROUP_MODES = {"concat", "union-crop"}
LAYOUTS = {"horizontal", "vertical", "auto"}


def issue(errors: list[str], warnings: list[str], message: str, strict: bool = False) -> None:
    (errors if strict else warnings).append(message)


def resolve_embedded_image(page: pymupdf.Page, figure: dict[str, Any]) -> dict[str, Any] | None:
    infos = page.get_image_info(xrefs=True)
    if not infos:
        return None
    xref = figure.get("image_xref")
    if xref is not None:
        for info in infos:
            if int(info.get("xref", 0)) == int(xref):
                return info
        return None
    index = int(figure.get("image_index", 0) or 0)
    if 0 <= index < len(infos):
        return infos[index]
    return None


def largest_embedded_image(page: pymupdf.Page) -> dict[str, Any] | None:
    infos = page.get_image_info(xrefs=True)
    if not infos:
        return None
    return max(infos, key=lambda info: int(info.get("width", 0)) * int(info.get("height", 0)))


def validate_manifest(
    manifest_path: Path,
    strict: bool = False,
    check_pdf: bool = True,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not manifest_path.exists():
        return [f"manifest not found: {manifest_path}"], warnings
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        return [f"invalid JSON: {exc}"], warnings
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"], warnings

    base = manifest_path.resolve().parent
    slug = manifest.get("slug")
    if not slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(slug)):
        errors.append("slug must be kebab-case (a-z, 0-9, hyphens)")

    paper = manifest.get("paper")
    if not isinstance(paper, dict) or not paper.get("pdf"):
        errors.append("paper.pdf is required")
        paper = {}

    handbook = manifest.get("handbook")
    if not handbook:
        errors.append("handbook is required")
    assets_dir = manifest.get("assets_dir")
    if not assets_dir:
        errors.append("assets_dir is required")

    output_max_px = manifest.get("output_max_px")
    if output_max_px is not None and (
        not isinstance(output_max_px, int) or output_max_px < 1
    ):
        errors.append("output_max_px must be a positive integer")
    asset_format = manifest.get("asset_format")
    if asset_format is not None and str(asset_format).lower() != "png":
        errors.append("asset_format must be 'png'")
    png_compress_level = manifest.get("png_compress_level")
    if png_compress_level is not None and (
        not isinstance(png_compress_level, int)
        or png_compress_level < 0
        or png_compress_level > 9
    ):
        errors.append("png_compress_level must be an integer between 0 and 9")

    figures = manifest.get("figures")
    if not isinstance(figures, list):
        errors.append("figures must be an array")
        figures = []
    panel_sets = manifest.get("panel_sets", [])
    if not isinstance(panel_sets, list):
        errors.append("panel_sets must be an array")
        panel_sets = []
    groups = manifest.get("groups", [])
    if not isinstance(groups, list):
        errors.append("groups must be an array")
        groups = []

    pdf_path = Path(paper.get("pdf", ""))
    if paper.get("pdf") and not pdf_path.is_absolute():
        pdf_path = (base / pdf_path).resolve()
    doc = None
    if check_pdf and paper.get("pdf"):
        if not pdf_path.exists():
            errors.append(f"paper.pdf not found: {pdf_path}")
        else:
            try:
                doc = pymupdf.open(str(pdf_path))
            except Exception as exc:
                errors.append(f"cannot open paper.pdf: {exc}")

    seen_ids: set[str] = set()
    seen_assets: set[str] = set()
    figure_index: dict[str, dict[str, Any]] = {}

    for index, figure in enumerate(figures):
        prefix = f"figures[{index}]"
        if not isinstance(figure, dict):
            errors.append(f"{prefix} must be an object")
            continue
        fig_id = figure.get("id")
        if not fig_id:
            errors.append(f"{prefix}.id is required")
            continue
        if fig_id in seen_ids:
            errors.append(f"duplicate figure id: {fig_id}")
        seen_ids.add(fig_id)
        figure_index[fig_id] = figure

        page_number = figure.get("page")
        if not isinstance(page_number, int) or page_number < 1:
            errors.append(f"{fig_id}: page must be a positive integer")
        elif doc is not None and page_number > doc.page_count:
            errors.append(f"{fig_id}: page {page_number} exceeds PDF page count {doc.page_count}")

        mode = figure.get("mode")
        if mode not in MODES:
            errors.append(f"{fig_id}: mode must be one of {sorted(MODES)}")
        units = figure.get("units")
        if units not in UNITS:
            errors.append(f"{fig_id}: units must be one of {sorted(UNITS)}")
        elif mode == "page-crop" and units != "pt":
            errors.append(f"{fig_id}: page-crop requires units='pt'")
        elif mode in {"embedded-panel", "embedded-full"} and units != "px":
            errors.append(f"{fig_id}: {mode} requires units='px'")

        max_px = figure.get("max_px")
        if max_px is not None and (not isinstance(max_px, int) or max_px < 1):
            errors.append(f"{fig_id}: max_px must be a positive integer")

        panels = figure.get("panels")
        if not isinstance(panels, dict) or not panels:
            errors.append(f"{fig_id}: panels must be a non-empty object")
            panels = {}
        for panel_key, box in panels.items():
            if not valid_box(box):
                errors.append(f"{fig_id} panel {panel_key!r}: box must be [x0,y0,x1,y1] with x1>x0 and y1>y0")
                continue
            asset = asset_filename(fig_id, panel_key if panel_key else None)
            if asset in seen_assets:
                warnings.append(f"duplicate generated asset name: {asset}")
            seen_assets.add(asset)

        if doc is not None and isinstance(page_number, int) and 1 <= page_number <= doc.page_count:
            page = doc[page_number - 1]
            if mode == "page-crop":
                page_w, page_h = page.rect.width, page.rect.height
                for panel_key, box in panels.items():
                    if not valid_box(box):
                        continue
                    x0, y0, x1, y1 = (float(v) for v in box)
                    if x0 < -2 or y0 < -2 or x1 > page_w + 2 or y1 > page_h + 2:
                        warnings.append(
                            f"{fig_id} panel {panel_key!r}: box {box} is outside page "
                            f"{page_w:.1f}x{page_h:.1f} pt"
                        )
            elif mode in {"embedded-panel", "embedded-full"}:
                info = resolve_embedded_image(page, figure)
                if info is None:
                    errors.append(
                        f"{fig_id}: no embedded image found on page {page_number} "
                        f"(set image_xref or image_index, or use page-crop)"
                    )
                else:
                    iw, ih = int(info.get("width", 0)), int(info.get("height", 0))
                    for panel_key, box in panels.items():
                        if not valid_box(box):
                            continue
                        x0, y0, x1, y1 = (float(v) for v in box)
                        if x0 < 0 or y0 < 0 or x1 > iw or y1 > ih:
                            warnings.append(
                                f"{fig_id} panel {panel_key!r}: box {box} is outside "
                                f"embedded image {iw}x{ih} px"
                            )

    seen_panel_set_ids: set[str] = set()
    for index, panel_set in enumerate(panel_sets):
        prefix = f"panel_sets[{index}]"
        if not isinstance(panel_set, dict):
            errors.append(f"{prefix} must be an object")
            continue
        set_id = panel_set.get("id")
        if not set_id:
            errors.append(f"{prefix}.id is required")
            continue
        if set_id in seen_panel_set_ids:
            errors.append(f"duplicate panel_set id: {set_id}")
        seen_panel_set_ids.add(set_id)
        max_px = panel_set.get("max_px")
        if max_px is not None and (not isinstance(max_px, int) or max_px < 1):
            errors.append(f"{set_id}: max_px must be a positive integer")
        figure_id = panel_set.get("figure")
        figure = figure_index.get(str(figure_id)) if figure_id else None
        if figure is None:
            errors.append(f"{set_id}: unknown figure {figure_id!r}")
            continue
        requested = panel_set.get("panels")
        if not isinstance(requested, list) or len(requested) < 2:
            errors.append(f"{set_id}: panels must be a list of at least two panels")
            continue
        lookup = {str(key).upper(): key for key in (figure.get("panels") or {}) if str(key)}
        upper_requested = [str(panel).upper() for panel in requested]
        missing = [panel for panel in upper_requested if panel not in lookup]
        if missing:
            errors.append(f"{set_id}: panels not found in {figure_id}: {missing}")
            continue
        ordered = sorted(lookup.keys())
        indices = sorted({ordered.index(panel) for panel in upper_requested})
        if indices != list(range(indices[0], indices[-1] + 1)):
            errors.append(f"{set_id}: panels must form one consecutive run in {figure_id}")
        filename = panel_set.get("filename") or panel_set_filename(str(figure_id), upper_requested)
        if filename in seen_assets:
            warnings.append(f"duplicate generated asset name: {filename}")
        seen_assets.add(filename)

    def resolve_group_source(label: str) -> tuple[dict[str, Any] | None, str | None]:
        if label in figure_index:
            figure = figure_index[label]
            panels = figure.get("panels", {})
            if len(panels) == 1:
                panel_key = next(iter(panels))
                return figure, panel_key
            return figure, None
        parsed = parse_figure_label(label)
        if not parsed:
            return None, None
        for fig_id, figure in figure_index.items():
            candidate = parse_figure_label(fig_id)
            if (
                candidate
                and candidate["prefix"] == parsed["prefix"]
                and candidate["number"] == parsed["number"]
            ):
                panels = figure.get("panels", {})
                panel = parsed["panels_raw"] or (next(iter(panels)) if len(panels) == 1 else None)
                if panel and panel not in panels and panel.lower() not in panels:
                    return None, None
                return figure, panel
        return None, None

    for index, group in enumerate(groups):
        prefix = f"groups[{index}]"
        if not isinstance(group, dict):
            errors.append(f"{prefix} must be an object")
            continue
        group_id = group.get("id")
        if not group_id:
            errors.append(f"{prefix}.id is required")
            continue
        max_px = group.get("max_px")
        if max_px is not None and (not isinstance(max_px, int) or max_px < 1):
            errors.append(f"{group_id}: max_px must be a positive integer")
        filename = group.get("filename") or group_filename(group_id)
        if filename in seen_assets:
            warnings.append(f"duplicate generated asset name: {filename}")
        seen_assets.add(filename)
        sources = group.get("from")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{group_id}: from must be a non-empty array")
            continue
        mode = group.get("mode", "concat")
        if mode not in GROUP_MODES:
            errors.append(f"{group_id}: group mode must be one of {sorted(GROUP_MODES)}")
        layout = group.get("layout", "auto")
        if layout not in LAYOUTS:
            errors.append(f"{group_id}: layout must be one of {sorted(LAYOUTS)}")
        resolved = []
        for source in sources:
            figure, panel = resolve_group_source(str(source))
            if figure is None:
                errors.append(f"{group_id}: cannot resolve source {source!r}")
            else:
                resolved.append((figure, panel))
        if mode == "union-crop" and len(resolved) > 1:
            pages = {figure.get("page") for figure, _ in resolved}
            modes = {figure.get("mode") for figure, _ in resolved}
            if len(pages) != 1 or len(modes) != 1:
                errors.append(f"{group_id}: union-crop sources must share a page and mode")

    if doc is not None:
        doc.close()
    return errors, warnings


def cmd_init(args: argparse.Namespace) -> int:
    pdf_path: Path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2
    out_path = args.out or (pdf_path.parent / f"{pdf_path.stem}.paper_manifest.json")
    out_path = out_path.resolve()
    if out_path.exists() and not args.force:
        print(f"ERROR: manifest exists: {out_path} (use --force)", file=sys.stderr)
        return 2
    slug = args.slug or safe_stem(pdf_path.stem)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        print("ERROR: slug must be kebab-case", file=sys.stderr)
        return 2
    try:
        doc = pymupdf.open(str(pdf_path))
        title = args.title or (doc.metadata or {}).get("title", "")
        page_count = doc.page_count
        doc.close()
    except Exception as exc:
        print(f"ERROR: cannot open PDF: {exc}", file=sys.stderr)
        return 2
    relative_pdf = os.path.relpath(pdf_path, out_path.parent).replace("\\", "/")
    manifest = {
        "slug": slug,
        "paper": {
            "title": title,
            "doi": args.doi or "",
            "pdf": relative_pdf,
            "page_count": page_count,
        },
        "handbook": args.handbook or f"{slug}.md",
        "assets_dir": args.assets_dir or f"{slug}.assets",
        "figure_rights": "user-confirmed",
        "default_dpi": 300,
        "output_dpi": 300,
        "output_max_px": 1600,
        "asset_format": "png",
        "png_compress_level": 9,
        "padding_pt": 0,
        "padding_px": 0,
        "figures": [],
        "panel_sets": [],
        "groups": [],
    }
    write_json(out_path, manifest)
    print(f"created={out_path}")
    print(f"slug={slug}")
    print(f"pages={page_count}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    errors, warnings = validate_manifest(args.manifest.resolve(), strict=args.strict)
    if args.json_out:
        write_json(args.json_out, {"errors": errors, "warnings": warnings})
    print(f"errors={len(errors)}")
    print(f"warnings={len(warnings)}")
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    if errors or (args.strict and warnings):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="create an empty manifest skeleton")
    init_parser.add_argument("--pdf", required=True, type=Path)
    init_parser.add_argument("--out", type=Path)
    init_parser.add_argument("--slug")
    init_parser.add_argument("--handbook")
    init_parser.add_argument("--assets-dir")
    init_parser.add_argument("--title")
    init_parser.add_argument("--doi")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=cmd_init)

    validate_parser = sub.add_parser("validate", help="validate a manifest")
    validate_parser.add_argument("--manifest", required=True, type=Path)
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.add_argument("--json-out", type=Path)
    validate_parser.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
