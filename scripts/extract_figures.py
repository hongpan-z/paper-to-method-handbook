"""Extract figure panels, consecutive-run panel sets and custom groups.

All cropping is driven by the explicit per-paper manifest. The script does not
detect panels or decide which figure belongs to which analytical unit. It also
writes asset_index.json so the verifier can match captions to panel sets.
"""

from __future__ import annotations

import argparse
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image

from common import (
    asset_filename,
    group_filename,
    manifest_asset_index,
    manifest_paths,
    panel_set_filename,
    parse_figure_label,
    pixmap_to_image,
    read_json,
    save_jpeg,
    save_png,
    write_json,
)

Image.MAX_IMAGE_PIXELS = None


def load_embedded_image(doc: pymupdf.Document, page: pymupdf.Page, figure: dict[str, Any]) -> tuple[Image.Image | None, dict | None]:
    infos = page.get_image_info(xrefs=True)
    if not infos:
        return None, None
    xref = figure.get("image_xref")
    info = None
    if xref is not None:
        info = next((item for item in infos if int(item.get("xref", 0)) == int(xref)), None)
    if info is None:
        index = int(figure.get("image_index", 0) or 0)
        if 0 <= index < len(infos):
            info = infos[index]
    if info is None:
        info = max(infos, key=lambda item: int(item.get("width", 0)) * int(item.get("height", 0)))
    xref = int(info.get("xref", 0))
    if not xref:
        return None, info
    try:
        pix = pymupdf.Pixmap(doc, xref)
        return pixmap_to_image(pix), info
    except Exception:
        try:
            data = doc.extract_image(xref)
            return Image.open(BytesIO(data["image"])).convert("RGB"), info
        except Exception:
            return None, info


def clamp_box(box, width: float, height: float) -> tuple[tuple[float, float, float, float], bool]:
    x0, y0, x1, y1 = (float(v) for v in box)
    clamped = (max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1))
    return clamped, clamped != (x0, y0, x1, y1)


def crop_page_panel(page: pymupdf.Page, box, padding: float, dpi: int) -> tuple[Image.Image, bool]:
    x0, y0, x1, y1 = (float(v) for v in box)
    x0 -= padding
    y0 -= padding
    x1 += padding
    y1 += padding
    (x0, y0, x1, y1), changed = clamp_box((x0, y0, x1, y1), page.rect.width, page.rect.height)
    rect = pymupdf.Rect(x0, y0, x1, y1)
    pix = page.get_pixmap(clip=rect, dpi=dpi, alpha=False)
    return pixmap_to_image(pix), changed


def crop_image_panel(image: Image.Image, box, padding: int) -> tuple[Image.Image, bool]:
    x0, y0, x1, y1 = (float(v) for v in box)
    x0 -= padding
    y0 -= padding
    x1 += padding
    y1 += padding
    (x0, y0, x1, y1), changed = clamp_box((x0, y0, x1, y1), image.width, image.height)
    return image.crop((int(x0), int(y0), int(x1), int(y1))), changed


def concat_images(images: list[Image.Image], layout: str, gap: int) -> Image.Image:
    if layout == "auto":
        layout = "horizontal"
    if layout == "vertical":
        width = max(image.width for image in images)
        height = sum(image.height for image in images) + gap * (len(images) - 1)
        canvas = Image.new("RGB", (width, height), "white")
        y = 0
        for image in images:
            canvas.paste(image, ((width - image.width) // 2, y))
            y += image.height + gap
        return canvas
    width = sum(image.width for image in images) + gap * (len(images) - 1)
    height = max(image.height for image in images)
    canvas = Image.new("RGB", (width, height), "white")
    x = 0
    for image in images:
        canvas.paste(image, (x, (height - image.height) // 2))
        x += image.width + gap
    return canvas


def resolve_source(
    source: str,
    figures: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    if source in figures:
        figure = figures[source]
        panels = figure.get("panels") or {}
        if len(panels) == 1:
            return figure, next(iter(panels))
        return figure, None
    parsed = parse_figure_label(source)
    if not parsed:
        return None, None
    for figure in figures.values():
        candidate = parse_figure_label(figure.get("id", ""))
        if (
            candidate
            and candidate["prefix"] == parsed["prefix"]
            and candidate["number"] == parsed["number"]
        ):
            panels = figure.get("panels") or {}
            raw = parsed["panels_raw"]
            if raw:
                lookup = {str(key).lower(): key for key in panels}
                key = lookup.get(raw.lower())
                if key is not None:
                    return figure, key
                return None, None
            if len(panels) == 1:
                return figure, next(iter(panels))
            return figure, None
    return None, None


def find_panel_key(figure: dict[str, Any], panel: str | None) -> str | None:
    panels = figure.get("panels") or {}
    if panel is None:
        return None
    if panel in panels:
        return panel
    lookup = {str(key).lower(): key for key in panels}
    return lookup.get(str(panel).lower())


def union_box(boxes: list) -> tuple[float, float, float, float]:
    x0 = min(float(box[0]) for box in boxes)
    y0 = min(float(box[1]) for box in boxes)
    x1 = max(float(box[2]) for box in boxes)
    y1 = max(float(box[3]) for box in boxes)
    return x0, y0, x1, y1


def crop_union_for_figure(
    doc: pymupdf.Document,
    figure: dict[str, Any],
    panel_keys: list[str],
    default_dpi: int,
    default_padding_pt: float,
    default_padding_px: int,
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    page_number = int(figure.get("page", 0))
    page = doc[page_number - 1]
    mode = figure.get("mode", "page-crop")
    panels = figure.get("panels") or {}
    boxes = [panels[key] for key in panel_keys]
    union = union_box(boxes)
    if mode == "page-crop":
        padding = float(figure.get("padding_pt", default_padding_pt))
        image, _ = crop_page_panel(page, union, padding, int(figure.get("dpi", default_dpi)))
    else:
        source_image, _ = load_embedded_image(doc, page, figure)
        if source_image is None:
            raise ValueError(f"{figure.get('id')}: no embedded image source")
        padding = int(figure.get("padding_px", default_padding_px))
        image, _ = crop_image_panel(source_image, union, padding)
    return image, union


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--only", nargs="*", help="figure or group ids to process")
    parser.add_argument("--assets-dir", type=Path, help="override output assets directory")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--index-only", action="store_true", help="write asset_index.json without cropping")
    parser.add_argument("--previews", action="store_true", help="write JPEG QA previews")
    parser.add_argument("--previews-all", action="store_true", help="preview every PNG in the assets directory")
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--preview-max-px", type=int, default=900)
    parser.add_argument("--preview-quality", type=int, default=82)
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
    assets_dir = (args.assets_dir.resolve() if args.assets_dir else paths["assets"])
    assets_dir.mkdir(parents=True, exist_ok=True)
    if args.index_only:
        index = manifest_asset_index(manifest)
        index_path = assets_dir / "asset_index.json"
        write_json(index_path, index)
        print(f"asset_index={index_path}")
        print(f"assets_indexed={len(index)}")
        return 0
    default_dpi = int(manifest.get("default_dpi", 300))
    output_dpi = int(manifest.get("output_dpi", 300))
    default_padding_pt = float(manifest.get("padding_pt", 0))
    default_padding_px = int(manifest.get("padding_px", 0))

    wanted = set(args.only) if args.only else None
    figures = {str(figure.get("id")): figure for figure in manifest.get("figures", [])}
    panel_sets = {str(panel_set.get("id")): panel_set for panel_set in manifest.get("panel_sets", [])}
    groups = {str(group.get("id")): group for group in manifest.get("groups", [])}
    if wanted:
        missing = wanted - set(figures) - set(panel_sets) - set(groups)
        for item in sorted(missing):
            print(f"WARNING: not found in manifest: {item}")

    doc = pymupdf.open(str(paths["pdf"]))
    written: list[Path] = []
    skipped: list[str] = []
    warnings: list[str] = []
    asset_index: dict[str, dict[str, Any]] = {}

    written_assets: dict[tuple[str, str | None], Path] = {}

    for fig_id, figure in figures.items():
        if wanted is not None and fig_id not in wanted:
            continue
        page_number = int(figure.get("page", 0))
        mode = figure.get("mode", "page-crop")
        panels = figure.get("panels") or {}
        if not isinstance(panels, dict) or not panels:
            warnings.append(f"{fig_id}: no panels")
            continue
        page = doc[page_number - 1] if 1 <= page_number <= doc.page_count else None
        if page is None:
            warnings.append(f"{fig_id}: invalid page {page_number}")
            continue
        dpi = int(figure.get("dpi", default_dpi))
        padding_pt = float(figure.get("padding_pt", default_padding_pt))
        padding_px = int(figure.get("padding_px", default_padding_px))

        if mode == "page-crop":
            for panel_key, box in panels.items():
                out_path = assets_dir / asset_filename(fig_id, panel_key if panel_key else None)
                asset_index[out_path.name] = {
                    "kind": "full" if panel_key == "" else "panel",
                    "figure": fig_id,
                    "panels": [""] if panel_key == "" else [str(panel_key).upper()],
                    "mode": mode,
                    "page": page_number,
                    "box": [float(value) for value in box],
                }
                if out_path.exists() and not args.force:
                    skipped.append(out_path.name)
                    written_assets[(fig_id, panel_key)] = out_path
                    continue
                image, clamped = crop_page_panel(page, box, padding_pt, dpi)
                if clamped:
                    warnings.append(f"{fig_id} panel {panel_key!r}: box clamped to page bounds")
                if args.dry_run:
                    print(f"DRY {out_path.name} {image.width}x{image.height}")
                else:
                    save_png(image, out_path, dpi=dpi)
                    print(f"{out_path.name} {image.width}x{image.height}")
                written.append(out_path)
                written_assets[(fig_id, panel_key)] = out_path
        elif mode in {"embedded-panel", "embedded-full"}:
            source_image, info = load_embedded_image(doc, page, figure)
            if source_image is None:
                warnings.append(f"{fig_id}: no embedded image on page {page_number}")
                continue
            for panel_key, box in panels.items():
                out_path = assets_dir / asset_filename(fig_id, panel_key if panel_key else None)
                asset_index[out_path.name] = {
                    "kind": "full" if panel_key == "" else "panel",
                    "figure": fig_id,
                    "panels": [""] if panel_key == "" else [str(panel_key).upper()],
                    "mode": mode,
                    "page": page_number,
                    "box": [float(value) for value in box],
                }
                if out_path.exists() and not args.force:
                    skipped.append(out_path.name)
                    written_assets[(fig_id, panel_key)] = out_path
                    continue
                if mode == "embedded-full":
                    image = source_image
                    clamped = False
                else:
                    image, clamped = crop_image_panel(source_image, box, padding_px)
                if clamped:
                    warnings.append(f"{fig_id} panel {panel_key!r}: box clamped to image bounds")
                if args.dry_run:
                    print(f"DRY {out_path.name} {image.width}x{image.height}")
                else:
                    save_png(image, out_path, dpi=output_dpi)
                    print(f"{out_path.name} {image.width}x{image.height}")
                written.append(out_path)
                written_assets[(fig_id, panel_key)] = out_path
        else:
            warnings.append(f"{fig_id}: unknown mode {mode}")

    for set_id, panel_set in panel_sets.items():
        if wanted is not None and set_id not in wanted:
            continue
        figure_id = str(panel_set.get("figure", ""))
        figure = figures.get(figure_id)
        if figure is None:
            warnings.append(f"{set_id}: unknown figure {figure_id!r}")
            continue
        requested = panel_set.get("panels") or []
        keys: list[str] = []
        for panel in requested:
            key = find_panel_key(figure, str(panel))
            if key is None:
                warnings.append(f"{set_id}: panel {panel!r} not found in {figure_id}")
                keys = []
                break
            keys.append(key)
        if not keys or len(keys) != len(requested):
            continue
        filename = panel_set.get("filename") or panel_set_filename(figure_id, keys)
        out_path = assets_dir / filename
        boxes = [figure["panels"][key] for key in keys]
        union = union_box(boxes)
        asset_index[filename] = {
            "kind": "panel-set",
            "figure": figure_id,
            "panels": [str(key).upper() for key in keys],
            "mode": figure.get("mode", "page-crop"),
            "page": int(figure.get("page", 0)),
            "box": [float(value) for value in union],
        }
        if out_path.exists() and not args.force:
            skipped.append(out_path.name)
            continue
        try:
            image, _ = crop_union_for_figure(
                doc, figure, keys, default_dpi, default_padding_pt, default_padding_px
            )
        except Exception as exc:
            warnings.append(f"{set_id}: {exc}")
            continue
        if args.dry_run:
            print(f"DRY {out_path.name} {image.width}x{image.height}")
        else:
            dpi = int(figure.get("dpi", default_dpi)) if figure.get("mode") == "page-crop" else output_dpi
            save_png(image, out_path, dpi=dpi)
            print(f"{out_path.name} {image.width}x{image.height}")
        written.append(out_path)

    for group_id, group in groups.items():
        if wanted is not None and group_id not in wanted:
            continue
        filename = group.get("filename") or group_filename(group_id)
        out_path = assets_dir / filename
        mode = group.get("mode", "concat")
        sources = group.get("from") or []
        resolved: list[tuple[dict[str, Any], str | None]] = []
        for source in sources:
            figure, panel = resolve_source(str(source), figures)
            if figure is None:
                warnings.append(f"{group_id}: cannot resolve source {source!r}")
                resolved = []
                break
            resolved.append((figure, panel))
        if not resolved:
            continue
        same_figure = all(
            str(figure.get("id")) == str(resolved[0][0].get("id")) for figure, _ in resolved
        )
        group_panels = []
        if same_figure:
            for figure, panel in resolved:
                key = find_panel_key(figure, panel)
                if key:
                    group_panels.append(str(key).upper())
        asset_index[filename] = {
            "kind": "group",
            "figure": str(resolved[0][0].get("id")) if same_figure else "",
            "panels": group_panels,
            "mode": mode,
            "sources": [str(source) for source in sources],
        }
        if out_path.exists() and not args.force:
            skipped.append(out_path.name)
            continue
        try:
            if mode == "union-crop":
                first_figure, _ = resolved[0]
                page_number = int(first_figure.get("page", 0))
                page = doc[page_number - 1]
                source_mode = first_figure.get("mode", "page-crop")
                boxes = []
                for figure, panel in resolved:
                    key = find_panel_key(figure, panel)
                    if key is None:
                        raise ValueError(f"{group_id}: source {panel!r} is ambiguous")
                    boxes.append(figure["panels"][key])
                x0 = min(float(box[0]) for box in boxes)
                y0 = min(float(box[1]) for box in boxes)
                x1 = max(float(box[2]) for box in boxes)
                y1 = max(float(box[3]) for box in boxes)
                if source_mode == "page-crop":
                    padding_pt = float(first_figure.get("padding_pt", default_padding_pt))
                    image, _ = crop_page_panel(page, (x0, y0, x1, y1), padding_pt, int(first_figure.get("dpi", default_dpi)))
                else:
                    source_image, _ = load_embedded_image(doc, page, first_figure)
                    if source_image is None:
                        raise ValueError(f"{group_id}: no embedded image source")
                    padding_px = int(first_figure.get("padding_px", default_padding_px))
                    image, _ = crop_image_panel(source_image, (x0, y0, x1, y1), padding_px)
            elif mode == "concat":
                images = []
                for figure, panel in resolved:
                    key = find_panel_key(figure, panel)
                    if key is None:
                        raise ValueError(f"{group_id}: source {panel!r} is ambiguous")
                    fig_id = str(figure.get("id"))
                    asset = written_assets.get((fig_id, key))
                    if asset is None:
                        asset = assets_dir / asset_filename(fig_id, key if key else None)
                    if not asset.exists():
                        raise ValueError(f"{group_id}: missing source asset {asset.name}")
                    with Image.open(asset) as opened:
                        images.append(opened.convert("RGB"))
                image = concat_images(images, group.get("layout", "auto"), int(group.get("gap", 24)))
            else:
                raise ValueError(f"{group_id}: unknown group mode {mode}")
        except Exception as exc:
            warnings.append(str(exc))
            continue
        if args.dry_run:
            print(f"DRY {out_path.name} {image.width}x{image.height}")
        else:
            save_png(image, out_path, dpi=output_dpi if mode != "union-crop" else default_dpi)
            print(f"{out_path.name} {image.width}x{image.height}")
        written.append(out_path)

    doc.close()

    if not args.dry_run:
        index_path = assets_dir / "asset_index.json"
        write_json(index_path, asset_index)
        print(f"asset_index={index_path}")

    if args.previews or args.previews_all:
        preview_dir = args.preview_dir or (manifest_path.parent / "_qa" / "previews")
        preview_dir.mkdir(parents=True, exist_ok=True)
        targets = list(assets_dir.glob("*.png")) if args.previews_all else [path for path in written if path.exists()]
        for path in targets:
            try:
                with Image.open(path) as image:
                    image = image.convert("RGB")
                    scale = min(1.0, args.preview_max_px / max(image.width, image.height))
                    if scale < 1.0:
                        image = image.resize(
                            (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
                        )
                    save_jpeg(image, preview_dir / f"{path.stem}.jpg", quality=args.preview_quality)
            except Exception as exc:
                warnings.append(f"preview failed for {path.name}: {exc}")

    print(f"written={len(written)}")
    print(f"skipped={len(skipped)}")
    print(f"warnings={len(warnings)}")
    for message in warnings:
        print(f"WARNING: {message}")
    print(f"assets_dir={assets_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
