"""Extract figure panels, consecutive-run panel sets and custom groups.

All cropping is driven by the explicit per-paper manifest. The script does not
detect panels or decide which figure belongs to which analytical unit. It
supports targeted incremental re-cropping, page-render caching and compressed
PNG output. It also writes asset_index.json so the verifier can match captions
to panel sets and so later runs can detect changed geometry.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import OrderedDict
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
    resize_to_max_px,
    save_jpeg,
    save_png,
    write_json,
)

Image.MAX_IMAGE_PIXELS = None


class PageImageCache:
    def __init__(
        self,
        counts: dict[tuple[int, int], int] | None = None,
        max_entries: int = 2,
        max_pixels: int = 40_000_000,
    ) -> None:
        self.counts = counts or {}
        self.max_entries = max_entries
        self.max_pixels = max_pixels
        self.cache: OrderedDict[tuple[int, int], Image.Image] = OrderedDict()

    def get(self, page: pymupdf.Page, dpi: int) -> Image.Image | None:
        key = (page.number + 1, dpi)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if self.counts.get(key, 0) <= 1:
            return None
        if page.rotation:
            return None
        scale = dpi / 72.0
        pixels = int(page.rect.width * scale) * int(page.rect.height * scale)
        if pixels > self.max_pixels:
            return None
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        image = pixmap_to_image(pix)
        self.cache[key] = image
        while len(self.cache) > self.max_entries:
            self.cache.popitem(last=False)
        return image


def load_embedded_image(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    figure: dict[str, Any],
    cache: OrderedDict[tuple[int, int], tuple[Image.Image, dict]] | None = None,
) -> tuple[Image.Image | None, dict | None]:
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
    key = (page.number, xref)
    if cache is not None and key in cache:
        cache.move_to_end(key)
        return cache[key]
    try:
        pix = pymupdf.Pixmap(doc, xref)
        image = pixmap_to_image(pix)
    except Exception:
        try:
            data = doc.extract_image(xref)
            image = Image.open(BytesIO(data["image"])).convert("RGB")
        except Exception:
            return None, info
    if cache is not None:
        cache[key] = (image, info)
        while len(cache) > 2:
            cache.popitem(last=False)
    return image, info


def clamp_box(box, width: float, height: float) -> tuple[tuple[float, float, float, float], bool]:
    x0, y0, x1, y1 = (float(v) for v in box)
    clamped = (max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1))
    return clamped, clamped != (x0, y0, x1, y1)


def crop_page_panel(
    page: pymupdf.Page,
    box,
    padding: float,
    dpi: int,
    page_cache: PageImageCache | None = None,
) -> tuple[Image.Image, bool]:
    x0, y0, x1, y1 = (float(v) for v in box)
    x0 -= padding
    y0 -= padding
    x1 += padding
    y1 += padding
    (x0, y0, x1, y1), changed = clamp_box((x0, y0, x1, y1), page.rect.width, page.rect.height)
    if page_cache is not None:
        full_page = page_cache.get(page, dpi)
        if full_page is not None:
            scale = dpi / 72.0
            left = max(0, min(full_page.width, math.floor(x0 * scale)))
            top = max(0, min(full_page.height, math.floor(y0 * scale)))
            right = max(0, min(full_page.width, math.ceil(x1 * scale)))
            bottom = max(0, min(full_page.height, math.ceil(y1 * scale)))
            if right > left and bottom > top:
                return full_page.crop((left, top, right, bottom)), changed
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
    page_cache: PageImageCache | None = None,
    embedded_cache: OrderedDict[tuple[int, int], tuple[Image.Image, dict]] | None = None,
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    page_number = int(figure.get("page", 0))
    page = doc[page_number - 1]
    mode = figure.get("mode", "page-crop")
    panels = figure.get("panels") or {}
    boxes = [panels[key] for key in panel_keys]
    union = union_box(boxes)
    if mode == "page-crop":
        padding = float(figure.get("padding_pt", default_padding_pt))
        image, _ = crop_page_panel(
            page,
            union,
            padding,
            int(figure.get("dpi", default_dpi)),
            page_cache,
        )
    else:
        source_image, _ = load_embedded_image(doc, page, figure, embedded_cache)
        if source_image is None:
            raise ValueError(f"{figure.get('id')}: no embedded image source")
        padding = int(figure.get("padding_px", default_padding_px))
        image, _ = crop_image_panel(source_image, union, padding)
    return image, union


SIGNATURE_KEYS = (
    "kind",
    "figure",
    "panels",
    "mode",
    "page",
    "box",
    "sources",
    "source_assets",
    "dpi",
    "padding_pt",
    "padding_px",
    "image_xref",
    "image_index",
    "max_px",
    "compress_level",
)


def normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(value[key]) for key in sorted(value)}
    return value


def entry_signature(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: normalize_value(entry.get(key)) for key in SIGNATURE_KEYS}


def should_rebuild(
    out_path: Path,
    desired: dict[str, Any],
    existing_index: dict[str, dict[str, Any]],
    force: bool,
) -> bool:
    if force or not out_path.exists():
        return True
    old = existing_index.get(out_path.name)
    if old is None:
        return True
    return entry_signature(old) != entry_signature(desired)


def file_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
        "format": path.suffix.lstrip(".").lower() or "png",
    }


def resolved_options(
    item: dict[str, Any],
    default_max_px: int,
    default_compress_level: int,
) -> tuple[int, int]:
    max_px = item.get("max_px")
    max_px = default_max_px if max_px is None else int(max_px)
    compress_level = item.get("png_compress_level")
    compress_level = (
        default_compress_level if compress_level is None else int(compress_level)
    )
    return max_px, compress_level


def save_asset(
    image: Image.Image,
    out_path: Path,
    dpi: int,
    max_px: int,
    compress_level: int,
    dry_run: bool,
) -> tuple[Image.Image, dict[str, Any] | None]:
    image = resize_to_max_px(image, max_px)
    if dry_run:
        print(f"DRY {out_path.name} {image.width}x{image.height}")
        return image, None
    save_png(
        image,
        out_path,
        dpi=dpi,
        optimize=True,
        compress_level=compress_level,
    )
    print(f"{out_path.name} {image.width}x{image.height}")
    return image, {
        "width": image.width,
        "height": image.height,
        "bytes": out_path.stat().st_size,
        "format": "png",
    }


def source_asset_metadata(
    name: str,
    assets_dir: Path,
    asset_index: dict[str, dict[str, Any]],
    existing_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    entry = asset_index.get(name) or existing_index.get(name)
    path = assets_dir / name
    if entry and "width" in entry and "height" in entry:
        return {
            "filename": name,
            "width": int(entry["width"]),
            "height": int(entry["height"]),
            "bytes": int(entry.get("bytes", path.stat().st_size if path.exists() else 0)),
        }
    if not path.exists():
        return None
    metadata = file_metadata(path)
    return {
        "filename": name,
        "width": metadata["width"],
        "height": metadata["height"],
        "bytes": metadata["bytes"],
    }


def group_figure_ids(resolved: list[tuple[dict[str, Any], str | None]]) -> set[str]:
    return {str(figure.get("id")) for figure, _ in resolved}


def resolve_group_sources(
    group: dict[str, Any],
    figures: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], str | None]]:
    resolved: list[tuple[dict[str, Any], str | None]] = []
    for source in group.get("from") or []:
        figure, panel = resolve_source(str(source), figures)
        if figure is None:
            return []
        resolved.append((figure, panel))
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--only", nargs="*", help="figure, panel-set or group ids to process")
    parser.add_argument("--assets-dir", type=Path, help="override output assets directory")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--index-only", action="store_true", help="write asset_index.json without cropping")
    parser.add_argument("--previews", action="store_true", help="write JPEG QA previews")
    parser.add_argument("--previews-all", action="store_true", help="preview every PNG in the assets directory")
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--preview-max-px", type=int, default=900)
    parser.add_argument("--preview-quality", type=int, default=82)
    parser.add_argument("--max-px", type=int, help="override manifest output_max_px")
    parser.add_argument("--png-compress-level", type=int, help="override manifest png_compress_level")
    parser.add_argument("--asset-format", help="output format; currently only png")
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
    default_max_px = int(
        args.max_px if args.max_px is not None else manifest.get("output_max_px", 1600)
    )
    default_compress_level = int(
        args.png_compress_level
        if args.png_compress_level is not None
        else manifest.get("png_compress_level", 9)
    )
    asset_format = (args.asset_format or manifest.get("asset_format", "png")).lower()
    if asset_format != "png":
        print("ERROR: only png assets are supported", file=sys.stderr)
        return 2

    figures = {str(figure.get("id")): figure for figure in manifest.get("figures", [])}
    panel_sets = {str(panel_set.get("id")): panel_set for panel_set in manifest.get("panel_sets", [])}
    groups = {str(group.get("id")): group for group in manifest.get("groups", [])}

    requested = set(args.only) if args.only else None
    requested_figures: set[str] = set()
    requested_panel_sets: set[str] = set()
    requested_groups: set[str] = set()
    if requested is None:
        requested_figures = set(figures)
        requested_panel_sets = set(panel_sets)
        requested_groups = set(groups)
    else:
        for item in requested:
            if item in figures:
                requested_figures.add(item)
            elif item in panel_sets:
                requested_panel_sets.add(item)
            elif item in groups:
                requested_groups.add(item)
            else:
                print(f"WARNING: not found in manifest: {item}")

    def process_panel_set(set_id: str, figure_id: str) -> bool:
        return (
            requested is None
            or set_id in requested_panel_sets
            or figure_id in requested_figures
        )

    page_crop_counts: dict[tuple[int, int], int] = {}

    def add_page_crop(page_number: int, dpi: int, amount: int = 1) -> None:
        if page_number > 0:
            key = (page_number, dpi)
            page_crop_counts[key] = page_crop_counts.get(key, 0) + amount

    for fig_id in requested_figures:
        figure = figures.get(fig_id)
        if figure is None or figure.get("mode", "page-crop") != "page-crop":
            continue
        panels = figure.get("panels") or {}
        add_page_crop(
            int(figure.get("page", 0)),
            int(figure.get("dpi", default_dpi)),
            len(panels),
        )
    for set_id, panel_set in panel_sets.items():
        figure_id = str(panel_set.get("figure", ""))
        figure = figures.get(figure_id)
        if figure is None or figure.get("mode", "page-crop") != "page-crop":
            continue
        if process_panel_set(set_id, figure_id):
            add_page_crop(
                int(figure.get("page", 0)),
                int(figure.get("dpi", default_dpi)),
            )
    for group_id, group in groups.items():
        if group.get("mode", "concat") != "union-crop":
            continue
        resolved = resolve_group_sources(group, figures)
        if not resolved:
            continue
        source_figures = group_figure_ids(resolved)
        if (
            requested is not None
            and group_id not in requested_groups
            and not (source_figures & requested_figures)
        ):
            continue
        first_figure = resolved[0][0]
        if first_figure.get("mode", "page-crop") == "page-crop":
            add_page_crop(
                int(first_figure.get("page", 0)),
                int(first_figure.get("dpi", default_dpi)),
            )

    page_cache = PageImageCache(page_crop_counts)
    embedded_cache: OrderedDict[tuple[int, int], tuple[Image.Image, dict]] = OrderedDict()

    index_path = assets_dir / "asset_index.json"
    existing_index: dict[str, dict[str, Any]] = {}
    if index_path.exists():
        try:
            loaded = read_json(index_path)
            if isinstance(loaded, dict):
                existing_index = loaded
        except Exception as exc:
            print(f"WARNING: cannot read asset index: {exc}")
    asset_index: dict[str, dict[str, Any]] = dict(existing_index)

    def record_entry(
        name: str,
        desired: dict[str, Any],
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = dict(existing_index.get(name, {}))
        entry.update(desired)
        if metadata:
            entry.update(metadata)
        elif path.exists() and ("width" not in entry or "height" not in entry):
            try:
                entry.update(file_metadata(path))
            except Exception:
                pass
        asset_index[name] = entry

    doc = pymupdf.open(str(paths["pdf"]))
    written: list[Path] = []
    skipped: list[str] = []
    warnings: list[str] = []
    written_assets: dict[tuple[str, str | None], Path] = {}

    for fig_id, figure in figures.items():
        if requested is not None and fig_id not in requested_figures:
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
        max_px, compress_level = resolved_options(
            figure, default_max_px, default_compress_level
        )

        if mode == "page-crop":
            for panel_key, box in panels.items():
                out_path = assets_dir / asset_filename(fig_id, panel_key if panel_key else None)
                desired = {
                    "kind": "full" if panel_key == "" else "panel",
                    "figure": fig_id,
                    "panels": [""] if panel_key == "" else [str(panel_key).upper()],
                    "mode": mode,
                    "page": page_number,
                    "box": [float(value) for value in box],
                    "dpi": dpi,
                    "padding_pt": padding_pt,
                    "padding_px": None,
                    "image_xref": figure.get("image_xref"),
                    "image_index": figure.get("image_index"),
                    "max_px": max_px,
                    "compress_level": compress_level,
                }
                written_assets[(fig_id, panel_key)] = out_path
                if not should_rebuild(out_path, desired, existing_index, args.force):
                    skipped.append(out_path.name)
                    record_entry(out_path.name, desired, out_path)
                    continue
                image, clamped = crop_page_panel(
                    page, box, padding_pt, dpi, page_cache
                )
                if clamped:
                    warnings.append(f"{fig_id} panel {panel_key!r}: box clamped to page bounds")
                _, metadata = save_asset(
                    image, out_path, dpi, max_px, compress_level, args.dry_run
                )
                written.append(out_path)
                record_entry(out_path.name, desired, out_path, metadata)
        elif mode in {"embedded-panel", "embedded-full"}:
            source_image, _ = load_embedded_image(
                doc, page, figure, embedded_cache
            )
            if source_image is None:
                warnings.append(f"{fig_id}: no embedded image on page {page_number}")
                continue
            for panel_key, box in panels.items():
                out_path = assets_dir / asset_filename(fig_id, panel_key if panel_key else None)
                desired = {
                    "kind": "full" if panel_key == "" else "panel",
                    "figure": fig_id,
                    "panels": [""] if panel_key == "" else [str(panel_key).upper()],
                    "mode": mode,
                    "page": page_number,
                    "box": [float(value) for value in box],
                    "dpi": output_dpi,
                    "padding_pt": None,
                    "padding_px": padding_px,
                    "image_xref": figure.get("image_xref"),
                    "image_index": figure.get("image_index"),
                    "max_px": max_px,
                    "compress_level": compress_level,
                }
                written_assets[(fig_id, panel_key)] = out_path
                if not should_rebuild(out_path, desired, existing_index, args.force):
                    skipped.append(out_path.name)
                    record_entry(out_path.name, desired, out_path)
                    continue
                if mode == "embedded-full":
                    image = source_image
                    clamped = False
                else:
                    image, clamped = crop_image_panel(source_image, box, padding_px)
                if clamped:
                    warnings.append(f"{fig_id} panel {panel_key!r}: box clamped to image bounds")
                _, metadata = save_asset(
                    image, out_path, output_dpi, max_px, compress_level, args.dry_run
                )
                written.append(out_path)
                record_entry(out_path.name, desired, out_path, metadata)
        else:
            warnings.append(f"{fig_id}: unknown mode {mode}")

    for set_id, panel_set in panel_sets.items():
        figure_id = str(panel_set.get("figure", ""))
        if not process_panel_set(set_id, figure_id):
            continue
        figure = figures.get(figure_id)
        if figure is None:
            warnings.append(f"{set_id}: unknown figure {figure_id!r}")
            continue
        requested_panels = panel_set.get("panels") or []
        keys: list[str] = []
        for panel in requested_panels:
            key = find_panel_key(figure, str(panel))
            if key is None:
                warnings.append(f"{set_id}: panel {panel!r} not found in {figure_id}")
                keys = []
                break
            keys.append(key)
        if not keys or len(keys) != len(requested_panels):
            continue
        filename = panel_set.get("filename") or panel_set_filename(figure_id, keys)
        out_path = assets_dir / filename
        boxes = [figure["panels"][key] for key in keys]
        union = union_box(boxes)
        max_px, compress_level = resolved_options(
            panel_set, default_max_px, default_compress_level
        )
        dpi = (
            int(figure.get("dpi", default_dpi))
            if figure.get("mode", "page-crop") == "page-crop"
            else output_dpi
        )
        desired = {
            "kind": "panel-set",
            "figure": figure_id,
            "panels": [str(key).upper() for key in keys],
            "mode": figure.get("mode", "page-crop"),
            "page": int(figure.get("page", 0)),
            "box": [float(value) for value in union],
            "dpi": dpi,
            "padding_pt": (
                float(figure.get("padding_pt", default_padding_pt))
                if figure.get("mode", "page-crop") == "page-crop"
                else None
            ),
            "padding_px": (
                int(figure.get("padding_px", default_padding_px))
                if figure.get("mode", "page-crop") != "page-crop"
                else None
            ),
            "image_xref": figure.get("image_xref"),
            "image_index": figure.get("image_index"),
            "max_px": max_px,
            "compress_level": compress_level,
        }
        if not should_rebuild(out_path, desired, existing_index, args.force):
            skipped.append(out_path.name)
            record_entry(out_path.name, desired, out_path)
            continue
        try:
            image, _ = crop_union_for_figure(
                doc,
                figure,
                keys,
                default_dpi,
                default_padding_pt,
                default_padding_px,
                page_cache,
                embedded_cache,
            )
        except Exception as exc:
            warnings.append(f"{set_id}: {exc}")
            continue
        _, metadata = save_asset(
            image, out_path, dpi, max_px, compress_level, args.dry_run
        )
        written.append(out_path)
        record_entry(out_path.name, desired, out_path, metadata)

    for group_id, group in groups.items():
        filename = group.get("filename") or group_filename(group_id)
        out_path = assets_dir / filename
        mode = group.get("mode", "concat")
        sources = group.get("from") or []
        resolved = resolve_group_sources(group, figures)
        if not resolved:
            warnings.append(f"{group_id}: cannot resolve one or more sources")
            continue
        source_figures = group_figure_ids(resolved)
        if (
            requested is not None
            and group_id not in requested_groups
            and not (source_figures & requested_figures)
        ):
            continue
        same_figure = all(
            str(figure.get("id")) == str(resolved[0][0].get("id"))
            for figure, _ in resolved
        )
        group_panels = []
        if same_figure:
            for figure, panel in resolved:
                key = find_panel_key(figure, panel)
                if key:
                    group_panels.append(str(key).upper())
        max_px, compress_level = resolved_options(
            group, default_max_px, default_compress_level
        )
        source_assets: list[dict[str, Any]] = []
        if mode == "concat":
            for figure, panel in resolved:
                key = find_panel_key(figure, panel)
                if key is None:
                    warnings.append(f"{group_id}: source {panel!r} is ambiguous")
                    source_assets = []
                    break
                name = asset_filename(
                    str(figure.get("id")), key if key else None
                )
                metadata = source_asset_metadata(
                    name, assets_dir, asset_index, existing_index
                )
                if metadata is None:
                    warnings.append(f"{group_id}: missing source asset {name}")
                    source_assets = []
                    break
                source_assets.append(metadata)
            if not source_assets:
                continue
        desired: dict[str, Any] = {
            "kind": "group",
            "figure": str(resolved[0][0].get("id")) if same_figure else "",
            "panels": group_panels,
            "mode": mode,
            "sources": [str(source) for source in sources],
            "source_assets": source_assets,
            "max_px": max_px,
            "compress_level": compress_level,
        }
        if mode == "union-crop":
            first_figure, _ = resolved[0]
            boxes = []
            for figure, panel in resolved:
                key = find_panel_key(figure, panel)
                if key is None:
                    boxes = []
                    break
                boxes.append(figure["panels"][key])
            if not boxes:
                warnings.append(f"{group_id}: source panel is ambiguous")
                continue
            source_mode = first_figure.get("mode", "page-crop")
            dpi = (
                int(first_figure.get("dpi", default_dpi))
                if source_mode == "page-crop"
                else output_dpi
            )
            desired.update(
                {
                    "box": [float(value) for value in union_box(boxes)],
                    "dpi": dpi,
                    "padding_pt": (
                        float(first_figure.get("padding_pt", default_padding_pt))
                        if source_mode == "page-crop"
                        else None
                    ),
                    "padding_px": (
                        int(first_figure.get("padding_px", default_padding_px))
                        if source_mode != "page-crop"
                        else None
                    ),
                    "image_xref": first_figure.get("image_xref"),
                    "image_index": first_figure.get("image_index"),
                }
            )
        else:
            desired["dpi"] = output_dpi
        if not should_rebuild(out_path, desired, existing_index, args.force):
            skipped.append(out_path.name)
            record_entry(out_path.name, desired, out_path)
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
                    image, _ = crop_page_panel(
                        page,
                        (x0, y0, x1, y1),
                        padding_pt,
                        int(first_figure.get("dpi", default_dpi)),
                        page_cache,
                    )
                else:
                    source_image, _ = load_embedded_image(
                        doc, page, first_figure, embedded_cache
                    )
                    if source_image is None:
                        raise ValueError(f"{group_id}: no embedded image source")
                    padding_px = int(first_figure.get("padding_px", default_padding_px))
                    image, _ = crop_image_panel(source_image, (x0, y0, x1, y1), padding_px)
                save_dpi = int(first_figure.get("dpi", default_dpi)) if source_mode == "page-crop" else output_dpi
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
                image = concat_images(
                    images, group.get("layout", "auto"), int(group.get("gap", 24))
                )
                save_dpi = output_dpi
            else:
                raise ValueError(f"{group_id}: unknown group mode {mode}")
        except Exception as exc:
            warnings.append(str(exc))
            continue
        _, metadata = save_asset(
            image, out_path, save_dpi, max_px, compress_level, args.dry_run
        )
        written.append(out_path)
        record_entry(out_path.name, desired, out_path, metadata)

    doc.close()

    if not args.dry_run:
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
