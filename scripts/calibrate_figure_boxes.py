"""Render calibration grids and detected image rectangles.

This is a drawing aid only. It never chooses panel boxes. Rendered pages and
embedded images are cached so figures sharing a page do not re-render it. Read
the generated grid image, then write exact coordinates into the manifest.
"""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from common import (
    figure_stem,
    manifest_paths,
    pixmap_to_image,
    read_json,
    save_png,
)


def draw_grid(
    image: Image.Image,
    step: int,
    scale: float,
    labels_in_source: bool = True,
    color_x=(220, 0, 0),
    color_y=(0, 70, 220),
) -> None:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    width, height = image.size
    x = 0
    while True:
        px = int(round(x * scale))
        if px >= width:
            break
        draw.line([(px, 0), (px, height)], fill=color_x, width=1)
        label = str(int(x))
        draw.text((px + 2, 2), label, fill=color_x, font=font)
        x += step
    y = 0
    while True:
        py = int(round(y * scale))
        if py >= height:
            break
        draw.line([(0, py), (width, py)], fill=color_y, width=1)
        label = str(int(y))
        draw.text((2, py + 1), label, fill=color_y, font=font)
        y += step


def draw_box(draw: ImageDraw.ImageDraw, box, scale: float, label: str, color, offset: float = 0.0) -> None:
    x0, y0, x1, y1 = (float(v) for v in box)
    rect = [int((x0 + offset) * scale), int((y0 + offset) * scale), int((x1 - offset) * scale), int((y1 - offset) * scale)]
    draw.rectangle(rect, outline=color, width=2)
    draw.text((rect[0] + 2, rect[1] + 2), label, fill=color, font=ImageFont.load_default())


def resolve_image_info(page: pymupdf.Page, figure: dict) -> dict | None:
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
    return max(infos, key=lambda info: int(info.get("width", 0)) * int(info.get("height", 0)))


def embedded_image(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    figure: dict,
    cache: OrderedDict[tuple[int, int], tuple[Image.Image, dict]] | None = None,
) -> tuple[Image.Image, dict] | tuple[None, None]:
    info = resolve_image_info(page, figure)
    if info is None:
        return None, None
    xref = int(info.get("xref", 0))
    if not xref:
        return None, None
    key = (page.number, xref)
    if cache is not None and key in cache:
        cache.move_to_end(key)
        return cache[key]
    try:
        pix = pymupdf.Pixmap(doc, xref)
        image = pixmap_to_image(pix)
    except Exception:
        return None, None
    if cache is not None:
        cache[key] = (image, info)
        while len(cache) > 2:
            cache.popitem(last=False)
    return image, info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--figures", nargs="*", help="figure ids; default all")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--step-pt", type=int, default=50)
    parser.add_argument("--step-px", type=int, default=100)
    parser.add_argument("--max-width", type=int, default=1600)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    manifest = read_json(manifest_path)
    paths = manifest_paths(manifest_path, manifest)
    if not paths["pdf"].exists():
        print(f"ERROR: PDF not found: {paths['pdf']}", file=sys.stderr)
        return 2
    out_dir = args.out or (manifest_path.parent / "_calibration")
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = set(args.figures) if args.figures else None
    figures = [fig for fig in manifest.get("figures", []) if wanted is None or fig.get("id") in wanted]
    if wanted:
        missing = wanted - {fig.get("id") for fig in figures}
        for fig_id in sorted(missing):
            print(f"WARNING: figure not found in manifest: {fig_id}")

    doc = pymupdf.open(str(paths["pdf"]))
    written = 0
    page_cache: OrderedDict[tuple[int, int], Image.Image] = OrderedDict()
    embedded_cache: OrderedDict[tuple[int, int], tuple[Image.Image, dict]] = OrderedDict()
    for figure in figures:
        fig_id = figure.get("id", "unknown")
        page_number = int(figure.get("page", 0))
        if page_number < 1 or page_number > doc.page_count:
            print(f"WARNING: {fig_id}: invalid page {page_number}")
            continue
        page = doc[page_number - 1]
        mode = figure.get("mode", "page-crop")
        stem = figure_stem(fig_id)
        out_path = out_dir / f"{manifest.get('slug', 'paper')}-{stem}-grid.png"

        if mode == "page-crop":
            cache_key = (page_number, args.dpi)
            if cache_key in page_cache:
                page_cache.move_to_end(cache_key)
                image = page_cache[cache_key].copy()
            else:
                pix = page.get_pixmap(dpi=args.dpi, alpha=False)
                base = pixmap_to_image(pix)
                page_cache[cache_key] = base
                while len(page_cache) > 4:
                    page_cache.popitem(last=False)
                image = base.copy()
            scale = args.dpi / 72.0
            draw_grid(image, args.step_pt, scale)
            draw = ImageDraw.Draw(image)
            for index, info in enumerate(page.get_image_info(xrefs=True)):
                bbox = info.get("bbox")
                if bbox:
                    draw_box(
                        draw,
                        bbox,
                        scale,
                        f"img{index} xref={info.get('xref', 0)} {info.get('width', 0)}x{info.get('height', 0)}",
                        (0, 150, 0),
                    )
            for panel_key, box in (figure.get("panels") or {}).items():
                draw_box(draw, box, scale, f"panel {panel_key or 'full'}", (200, 0, 160))
            save_png(image, out_path)
            print(f"{out_path}  page={page_number}  size_pt={page.rect.width:.1f}x{page.rect.height:.1f}")
            written += 1
        elif mode in {"embedded-panel", "embedded-full"}:
            image, info = embedded_image(doc, page, figure, embedded_cache)
            if image is None:
                print(
                    f"WARNING: {fig_id}: no embedded image on page {page_number}; "
                    "use page-crop mode or set image_xref/image_index"
                )
                continue
            preview_scale = min(1.0, args.max_width / image.width)
            preview = image.resize(
                (max(1, int(image.width * preview_scale)), max(1, int(image.height * preview_scale)))
            )
            draw_grid(preview, args.step_px, preview_scale)
            draw = ImageDraw.Draw(preview)
            for panel_key, box in (figure.get("panels") or {}).items():
                draw_box(draw, box, preview_scale, f"panel {panel_key or 'full'}", (200, 0, 160))
            save_png(preview, out_path)
            print(
                f"{out_path}  page={page_number}  image_px={image.width}x{image.height}  "
                f"xref={info.get('xref', 0)}"
            )
            written += 1
        else:
            print(f"WARNING: {fig_id}: unknown mode {mode}")
    doc.close()
    print(f"grids_written={written}")
    print(f"output={out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
