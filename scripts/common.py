"""Shared deterministic helpers for the paper-to-method-handbook skill."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    import pymupdf
    from PIL import Image

FIGURE_LABEL_RE = re.compile(
    r"^\s*(?P<prefix>Extended\s+Data\s+Fig\.?|ED\s+Fig\.?|Supplementary\s+Fig\.?|Suppl\.?\s+Fig\.?|Fig\.?|Figure)\s*"
    r"(?P<num>\d+)\s*"
    r"(?P<panels>[A-Za-z](?:\s*(?:[\u2013-]|,)\s*[A-Za-z])*)?\s*"
    r"(?P<qual>\([^)]*\))?\s*$",
    re.IGNORECASE,
)

INLINE_FIGURE_RE = re.compile(
    r"(?<!!)\b(?P<prefix>Extended\s+Data\s+Fig\.?|ED\s+Fig\.?|Supplementary\s+Fig\.?|Suppl\.?\s+Fig\.?|Fig\.?|Figure)\s*"
    r"(?P<num>\d+)(?P<rest>[A-Za-z]?(?:\s*(?:[\u2013-]|,)\s*[A-Za-z])?(?:\s*\([^)]*\))?)?",
    re.IGNORECASE,
)

NUMBER_RE = re.compile(
    r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?(?:\s?(?:%|kb|Mb|Gb|bp|kb|µm|μm|nm|mm|cm|ml|µl|μl|h|min|days?|weeks?|months?|×|x))?(?![\w])",
    re.IGNORECASE,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_path(base: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def manifest_paths(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    base = manifest_path.resolve().parent
    return {
        "base": base,
        "pdf": resolve_path(base, manifest["paper"]["pdf"]),
        "handbook": resolve_path(base, manifest["handbook"]),
        "assets": resolve_path(base, manifest["assets_dir"]),
    }


def prefix_key(prefix: str) -> str:
    normalized = re.sub(r"\s+", " ", prefix.strip().lower())
    if normalized.startswith("extended data") or normalized.startswith("ed fig"):
        return "edfig"
    if normalized.startswith("supplementary") or normalized.startswith("suppl"):
        return "sfig"
    if normalized.startswith("figure"):
        return "figure"
    return "fig"


def parse_figure_label(label: str) -> dict[str, Any] | None:
    match = FIGURE_LABEL_RE.match(label.strip())
    if not match:
        return None
    panels_raw = match.group("panels") or ""
    panels_raw = re.sub(r"\s+", "", panels_raw).replace("\u2013", "-")
    return {
        "prefix": prefix_key(match.group("prefix")),
        "number": int(match.group("num")),
        "panels_raw": panels_raw,
        "qualifier": (match.group("qual") or "").strip(),
    }


def _panel_token(panel: str | None) -> str:
    if not panel:
        return ""
    token = panel.strip().lower().replace("\u2013", "-").replace(" ", "")
    token = re.sub(r"[^a-z0-9,\-]", "", token)
    return token


def figure_stem(label: str, panel: str | None = None) -> str:
    parsed = parse_figure_label(label)
    if not parsed:
        cleaned = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        return cleaned or "figure"
    stem = f"{parsed['prefix']}{parsed['number']:02d}"
    token = _panel_token(panel)
    if panel is None and parsed["panels_raw"]:
        token = _panel_token(parsed["panels_raw"])
    return f"{stem}{token}"


def asset_filename(label: str, panel: str | None = None) -> str:
    return f"{figure_stem(label, panel)}.png"


def group_filename(label: str) -> str:
    return f"{figure_stem(label)}.png"


def expand_panel_letters(panels_raw: str) -> list[str]:
    if not panels_raw:
        return []
    letters: list[str] = []
    for part in re.split(r",", panels_raw.replace(" ", "")):
        if not part:
            continue
        if re.search(r"[\u2013-]", part):
            bounds = re.split(r"[\u2013-]", part)
            if len(bounds) >= 2 and len(bounds[0]) == 1 and len(bounds[1]) == 1:
                start, end = ord(bounds[0].upper()), ord(bounds[1].upper())
                if start <= end:
                    letters.extend(chr(code) for code in range(start, end + 1))
                else:
                    letters.extend(chr(code) for code in range(end, start + 1))
        else:
            letters.extend(ch for ch in part if ch.isalpha())
    return sorted({letter.upper() for letter in letters})


def panel_run_string(panels: Iterable[str]) -> str:
    ordered = sorted({str(panel).upper() for panel in panels if str(panel)})
    if not ordered:
        return ""
    if len(ordered) == 1:
        return ordered[0].lower()
    return f"{ordered[0].lower()}-{ordered[-1].lower()}"


def panel_set_filename(figure_id: str, panels: Iterable[str]) -> str:
    parsed = parse_figure_label(figure_id)
    run = panel_run_string(panels)
    if not parsed:
        return f"{safe_stem(figure_id)}-{run}.png"
    return f"{parsed['prefix']}{parsed['number']:02d}{run}.png"


def manifest_asset_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    figures = {str(figure.get("id")): figure for figure in manifest.get("figures", [])}
    for figure in figures.values():
        figure_id = str(figure.get("id"))
        panels = figure.get("panels") or {}
        for panel_key, box in panels.items():
            filename = asset_filename(figure_id, panel_key if panel_key else None)
            index[filename] = {
                "kind": "full" if panel_key == "" else "panel",
                "figure": figure_id,
                "panels": [""] if panel_key == "" else [str(panel_key).upper()],
                "mode": figure.get("mode", "page-crop"),
                "page": int(figure.get("page", 0)),
                "box": [float(value) for value in box],
            }
    for panel_set in manifest.get("panel_sets", []):
        figure_id = str(panel_set.get("figure", ""))
        figure = figures.get(figure_id)
        if figure is None:
            continue
        panels = [str(panel).upper() for panel in panel_set.get("panels", [])]
        lookup = {str(key).upper(): key for key in (figure.get("panels") or {})}
        keys = [lookup[panel] for panel in panels if panel in lookup]
        if len(keys) != len(panels):
            continue
        filename = panel_set.get("filename") or panel_set_filename(figure_id, keys)
        boxes = [figure["panels"][key] for key in keys]
        index[filename] = {
            "kind": "panel-set",
            "figure": figure_id,
            "panels": panels,
            "mode": figure.get("mode", "page-crop"),
            "page": int(figure.get("page", 0)),
            "box": [float(value) for value in union_box_values(boxes)],
        }
    for group in manifest.get("groups", []):
        group_id = str(group.get("id", ""))
        filename = group.get("filename") or group_filename(group_id)
        sources = [str(source) for source in group.get("from", [])]
        resolved: list[tuple[dict[str, Any], str | None]] = []
        for source in sources:
            figure = figures.get(source)
            panel = None
            if figure is None:
                parsed = parse_figure_label(source)
                if parsed:
                    for candidate in figures.values():
                        candidate_parsed = parse_figure_label(str(candidate.get("id")))
                        if (
                            candidate_parsed
                            and candidate_parsed["prefix"] == parsed["prefix"]
                            and candidate_parsed["number"] == parsed["number"]
                        ):
                            figure = candidate
                            panel = parsed["panels_raw"] or None
                            break
            if figure is None:
                resolved = []
                break
            resolved.append((figure, panel))
        same_figure = bool(resolved) and all(
            str(figure.get("id")) == str(resolved[0][0].get("id")) for figure, _ in resolved
        )
        group_panels: list[str] = []
        if same_figure:
            for figure, panel in resolved:
                panels = figure.get("panels") or {}
                lookup = {str(key).lower(): key for key in panels}
                key = lookup.get(str(panel).lower()) if panel else None
                if key:
                    group_panels.append(str(key).upper())
        index[filename] = {
            "kind": "group",
            "figure": str(resolved[0][0].get("id")) if same_figure else "",
            "panels": group_panels,
            "mode": group.get("mode", "concat"),
            "sources": sources,
        }
    return index


def union_box_values(boxes: Iterable[Iterable[float]]) -> tuple[float, float, float, float]:
    values = [list(box) for box in boxes]
    return (
        min(float(box[0]) for box in values),
        min(float(box[1]) for box in values),
        max(float(box[2]) for box in values),
        max(float(box[3]) for box in values),
    )


def split_consecutive_runs(panels: Iterable[str]) -> list[list[str]]:
    ordered = sorted({str(panel).upper() for panel in panels if str(panel)})
    runs: list[list[str]] = []
    current: list[str] = []
    for panel in ordered:
        if len(panel) != 1 or not panel.isalpha():
            if current:
                runs.append(current)
                current = []
            runs.append([panel])
            continue
        if current and ord(panel) == ord(current[-1]) + 1:
            current.append(panel)
        else:
            if current:
                runs.append(current)
            current = [panel]
    if current:
        runs.append(current)
    return runs


def pixmap_to_image(pix: pymupdf.Pixmap) -> Image.Image:
    from PIL import Image

    mode = "RGBA" if pix.alpha else "RGB"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return image.convert("RGB")


def resize_to_max_px(image: Image.Image, max_px: int | None) -> Image.Image:
    if not max_px or max_px <= 0:
        return image
    if max(image.size) <= max_px:
        return image
    from PIL import Image

    resized = image.copy()
    resized.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    return resized


def save_png(
    image: Image.Image,
    path: Path,
    dpi: int | None = None,
    optimize: bool = False,
    compress_level: int = 6,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {}
    if dpi:
        options["dpi"] = (dpi, dpi)
    if optimize:
        options["optimize"] = True
    if compress_level != 6:
        options["compress_level"] = max(0, min(9, int(compress_level)))
    image.save(path, **options)


def save_jpeg(image: Image.Image, path: Path, quality: int = 82) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, quality=quality, optimize=True)


def valid_box(box: Iterable[float]) -> bool:
    values = list(box)
    if len(values) != 4:
        return False
    x0, y0, x1, y1 = (float(v) for v in values)
    return x1 > x0 and y1 > y0


def parse_page_selection(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                start, end = end, start
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    return sorted({page for page in pages if 1 <= page <= total})


def anchor_slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("*", "").replace("`", "")
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s]+", "-", text)
    return text.strip("-")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_number_text(text: str) -> str:
    text = text.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", "", text).lower()


def extract_numbers(text: str) -> list[str]:
    return [match.group(0) for match in NUMBER_RE.finditer(text)]


def image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def safe_stem(text: str, fallback: str = "handbook", max_length: int = 60) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    stem = stem[:max_length].rstrip("-")
    return stem or fallback
