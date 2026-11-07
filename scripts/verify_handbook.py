"""Verify structure, links, assets, panel/caption matching, and coverage.

Hard checks fail the run. Heuristic fidelity and coverage checks emit warnings
for the LLM to audit; they do not establish scientific validity. Panel-specific
claims must use panel crops or consecutive-run panel sets, not full figures.
--text-only skips all figure, manifest and asset checks for a deliberate
no-figure handbook; text, structure and fidelity checks still run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

from common import (
    anchor_slug,
    expand_panel_letters,
    extract_numbers,
    manifest_asset_index,
    manifest_paths,
    normalize_number_text,
    parse_figure_label,
    read_json,
    split_consecutive_runs,
)

LABEL = (
    r"(?:(?:Extended\s+Data|Supplementary|Suppl\.?|ED)\s+)?"
    r"(?:Fig(?:ure)?\.?)\s*\d+[A-Za-z]?"
    r"(?:\s*(?:[\u2013-]|,)\s*[A-Za-z])?"
    r"(?:\s*\([^)]*\))?"
)
CAPTION_PLAIN_RE = re.compile(rf"^(?P<label>{LABEL})\s*:\s*")
CAPTION_BOLD_RE = re.compile(rf"^\*\*(?P<label>{LABEL})\*\*\s*:\s*")
CAPTION_ITALIC_RE = re.compile(rf"^\*(?P<label>{LABEL})\*\s*:\s*")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
INLINE_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
CATALOGUE_LINK_RE = re.compile(r"\[[^\]]+\]\(#([^)]+)\)")
FIGURE_PREFIX_RE = re.compile(
    r"^\s*((?:(?:Extended\s+Data|Supplementary|Suppl\.?|ED)\s+)?(?:Fig(?:ure)?\.?)\s*\d+[A-Za-z]?)",
    re.IGNORECASE,
)


def add_issue(store: list[dict], message: str, line: int | None = None) -> None:
    store.append({"message": message, "line": line})


def build_anchors(lines: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    anchors: dict[str, int] = {}
    for line_number, line in enumerate(lines, 1):
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = anchor_slug(match.group(2))
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count}"
        anchors.setdefault(anchor, line_number)
    return anchors


def sections_by_heading(lines: list[str]) -> list[dict]:
    headings = []
    for line_number, line in enumerate(lines, 1):
        match = HEADING_RE.match(line)
        if match:
            headings.append(
                {
                    "line": line_number,
                    "level": len(match.group(1)),
                    "text": match.group(2).strip(),
                }
            )
    sections = []
    for index, heading in enumerate(headings):
        start = heading["line"]
        end = len(lines)
        for later in headings[index + 1 :]:
            if later["level"] <= heading["level"]:
                end = later["line"] - 1
                break
        sections.append({**heading, "end": end})
    return sections


def link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split()[0] if target.split() else target
    target = unquote(target)
    target = target.split("#", 1)[0].split("?", 1)[0]
    return target


def verify_images(
    lines: list[str],
    handbook_path: Path,
    assets_dir: Path | None,
    min_px: int,
    errors: list[dict],
    warnings: list[dict],
) -> tuple[int, set[Path]]:
    referenced: set[Path] = set()
    image_count = 0
    try:
        from PIL import Image
    except ImportError as exc:
        if any(IMAGE_RE.search(line) for line in lines):
            add_issue(errors, f"Pillow is required to verify images: {exc}")
        return image_count, referenced
    for line_number, line in enumerate(lines, 1):
        for raw in IMAGE_RE.findall(line):
            image_count += 1
            target = link_target(raw)
            if not target:
                add_issue(errors, "empty image target", line_number)
                continue
            path = Path(target)
            if not path.is_absolute():
                path = handbook_path.parent / path
            path = path.resolve()
            if assets_dir is not None:
                try:
                    inside = path.is_relative_to(assets_dir.resolve())
                except AttributeError:
                    inside = str(path).startswith(str(assets_dir.resolve()))
                if not inside:
                    add_issue(errors, f"image is outside assets_dir: {target}", line_number)
            if not path.exists():
                add_issue(errors, f"missing image: {target}", line_number)
                continue
            referenced.add(path)
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    width, height = image.size
                    if width < min_px or height < min_px:
                        add_issue(
                            warnings,
                            f"small image ({width}x{height}): {target}",
                            line_number,
                        )
            except Exception as exc:
                add_issue(errors, f"invalid image {target}: {exc}", line_number)
        for raw in INLINE_LINK_RE.findall(line):
            target = link_target(raw)
            if not target:
                continue
            path = Path(target)
            if not path.is_absolute():
                path = handbook_path.parent / path
            if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                referenced.add(path.resolve())
    return image_count, referenced


def check_units(units_path: Path, errors: list[dict], warnings: list[dict]) -> dict:
    if not units_path.exists():
        add_issue(errors, f"units file not found: {units_path}")
        return {}
    try:
        data = read_json(units_path)
    except Exception as exc:
        add_issue(errors, f"units JSON invalid: {exc}")
        return {}
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        add_issue(errors, "units.chapters must be a non-empty array")
        return {}
    seen: set[str] = set()
    unit_count = 0
    evidence: list[str] = []
    unit_ids: set[str] = set()
    chapter_ids: set[str] = set()
    unit_evidence: dict[str, list[str]] = {}
    unit_blocks: dict[str, list[list[str]]] = {}
    unit_exceptions: dict[str, list] = {}
    for chapter_index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            add_issue(errors, f"chapters[{chapter_index}] must be an object")
            continue
        for key in ("id", "title", "goal", "units"):
            if not chapter.get(key):
                add_issue(errors, f"chapters[{chapter_index}].{key} is required")
        if chapter.get("id"):
            chapter_ids.add(str(chapter["id"]))
        units = chapter.get("units")
        if not isinstance(units, list) or not units:
            add_issue(errors, f"chapter {chapter.get('id')}: units must be a non-empty array")
            continue
        for unit_index, unit in enumerate(units):
            if not isinstance(unit, dict):
                add_issue(errors, f"chapter {chapter.get('id')} units[{unit_index}] must be an object")
                continue
            unit_id = unit.get("id")
            if not unit_id:
                add_issue(errors, f"chapter {chapter.get('id')} units[{unit_index}].id is required")
            elif unit_id in seen:
                add_issue(errors, f"duplicate unit id: {unit_id}")
            else:
                unit_ids.add(str(unit_id))
            seen.add(unit_id)
            unit_count += 1
            for key in ("title", "goal_principle", "methods", "evidence", "source_refs"):
                if key not in unit:
                    add_issue(errors, f"unit {unit_id}: missing {key}")
            blocks = unit.get("result_blocks")
            block_evidence: list[list[str]] = []
            if blocks is not None:
                if not isinstance(blocks, list):
                    add_issue(errors, f"unit {unit_id}: result_blocks must be an array")
                    blocks = []
                for block_index, block in enumerate(blocks):
                    if not isinstance(block, dict):
                        add_issue(errors, f"unit {unit_id} result_blocks[{block_index}] must be an object")
                        continue
                    block_evidence.append([str(item) for item in (block.get("evidence") or [])])
            if not block_evidence:
                block_evidence = [[str(item) for item in (unit.get("evidence") or [])]]
            unit_evidence[str(unit_id)] = [item for block in block_evidence for item in block]
            unit_blocks[str(unit_id)] = block_evidence
            evidence.extend(unit_evidence[str(unit_id)])
            exceptions = unit.get("evidence_exceptions")
            if exceptions is not None:
                if not isinstance(exceptions, list):
                    add_issue(errors, f"unit {unit_id}: evidence_exceptions must be an array")
                else:
                    unit_exceptions[str(unit_id)] = exceptions
    if not unit_count:
        add_issue(errors, "units file contains no units")
    return {
        "chapters": len(chapters),
        "units": unit_count,
        "evidence": evidence,
        "unit_ids": unit_ids,
        "chapter_ids": chapter_ids,
        "unit_evidence": unit_evidence,
        "unit_blocks": unit_blocks,
        "unit_exceptions": unit_exceptions,
    }


def check_coverage(
    evidence: list[str],
    manifest: dict | None,
    captions: list[dict] | None,
    errors: list[dict],
    warnings: list[dict],
) -> None:
    manifest_figures = set()
    if manifest:
        for figure in manifest.get("figures", []):
            parsed = parse_figure_label(str(figure.get("id", "")))
            if parsed:
                manifest_figures.add((parsed["prefix"], parsed["number"]))
    if not manifest_figures:
        return
    for label in evidence:
        parsed = parse_figure_label(label)
        if not parsed:
            add_issue(warnings, f"evidence label is not parseable: {label}")
            continue
        key = (parsed["prefix"], parsed["number"])
        if key not in manifest_figures:
            add_issue(warnings, f"evidence figure is not in the manifest: {label}")
    if captions:
        source_figures = set()
        for caption in captions:
            match = FIGURE_PREFIX_RE.match(str(caption.get("text", "")))
            if not match:
                continue
            parsed = parse_figure_label(match.group(1))
            if parsed:
                source_figures.add((parsed["prefix"], parsed["number"]))
        missing = sorted(source_figures - manifest_figures)
        for prefix, number in missing:
            add_issue(
                warnings,
                f"source caption figure {prefix} {number} is not represented in the manifest",
            )


def collect_referenced_paths(handbook_path: Path) -> set[Path]:
    text = handbook_path.read_text(encoding="utf-8")
    paths: set[Path] = set()
    for raw in IMAGE_RE.findall(text) + INLINE_LINK_RE.findall(text):
        target = link_target(raw)
        if not target:
            continue
        path = Path(target)
        if not path.is_absolute():
            path = handbook_path.parent / path
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
            paths.add(path.resolve())
    return paths


def caption_info(line: str) -> dict | None:
    match = CAPTION_BOLD_RE.match(line.strip())
    if not match:
        return None
    label = match.group("label")
    parsed = parse_figure_label(label)
    if not parsed:
        return None
    return {
        "label": label,
        "prefix": parsed["prefix"],
        "number": parsed["number"],
        "panels": expand_panel_letters(parsed["panels_raw"]),
    }


def caption_block_info(lines: list[str], start: int) -> dict | None:
    labels: list[str] = []
    panels: set[str] = set()
    prefixes: set[str] = set()
    numbers: set[int] = set()
    index = start
    while index < len(lines) and not lines[index].strip():
        index += 1
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        matched = False
        for segment in line.split("<br>"):
            info = caption_info(segment)
            if info is None:
                continue
            labels.append(info["label"])
            panels.update(info["panels"])
            prefixes.add(info["prefix"])
            numbers.add(info["number"])
            matched = True
        if not matched:
            break
        if "<br>" not in line:
            break
        index += 1
    if not labels:
        return None
    if len(prefixes) != 1 or len(numbers) != 1:
        return {
            "label": "; ".join(labels),
            "labels": labels,
            "prefix": None,
            "number": None,
            "panels": sorted(panels),
        }
    return {
        "label": "; ".join(labels),
        "labels": labels,
        "prefix": next(iter(prefixes)),
        "number": next(iter(numbers)),
        "panels": sorted(panels),
    }


def manifest_figure_id(info: dict, figures: list[dict]) -> str | None:
    for figure in figures:
        parsed = parse_figure_label(str(figure.get("id", "")))
        if (
            parsed
            and parsed["prefix"] == info["prefix"]
            and parsed["number"] == info["number"]
        ):
            return str(figure.get("id"))
    return None


def figure_panel_keys(manifest: dict | None, figure_id: str) -> list[str]:
    if not manifest:
        return []
    for figure in manifest.get("figures", []):
        if str(figure.get("id")) == figure_id:
            return sorted(
                str(key).upper() for key in (figure.get("panels") or {}) if str(key)
            )
    return []


def panel_tuple(panels: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(panel).upper() for panel in panels if str(panel)}))


def collect_unit_images(lines: list[str], start: int, end: int) -> list[dict]:
    images = []
    for line_number in range(start, min(end + 1, len(lines) + 1)):
        line = lines[line_number - 1]
        match = IMAGE_RE.search(line)
        if not match:
            continue
        info = caption_block_info(lines, line_number)
        images.append(
            {
                "line": line_number,
                "asset": Path(link_target(match.group(1))).name,
                "info": info,
            }
        )
    return images


def evidence_info(label: str, manifest_figures: list[dict]) -> dict | None:
    parsed = parse_figure_label(str(label))
    if not parsed:
        return None
    probe = {"prefix": parsed["prefix"], "number": parsed["number"]}
    return {
        "label": str(label),
        "prefix": parsed["prefix"],
        "number": parsed["number"],
        "panels": expand_panel_letters(parsed["panels_raw"]),
        "figure_id": manifest_figure_id(probe, manifest_figures),
    }


def check_unit_coverage(
    unit_id: str,
    citations: list[str],
    images: list[dict],
    manifest: dict | None,
    errors: list[dict],
    warnings: list[dict],
    has_exception: bool,
) -> None:
    if manifest is None:
        return
    manifest_figures = list(manifest.get("figures", []))
    cited_by_figure: dict[str, set[str]] = {}
    for label in citations:
        info = evidence_info(label, manifest_figures)
        if info is None:
            add_issue(warnings, f"unit {unit_id}: cannot parse evidence label {label!r}")
            continue
        if info["figure_id"] is None:
            add_issue(warnings, f"unit {unit_id}: evidence figure not in manifest: {label}")
            continue
        if info["panels"]:
            cited_by_figure.setdefault(info["figure_id"], set()).update(info["panels"])

    stored = errors if not has_exception else warnings
    for figure_id, cited in sorted(cited_by_figure.items()):
        order = figure_panel_keys(manifest, figure_id)
        ordered_cited = [panel for panel in order if panel in cited]
        unknown = cited - set(ordered_cited)
        if unknown:
            add_issue(stored, f"unit {unit_id}: cited panels not in {figure_id}: {sorted(unknown)}")
            continue
        runs = split_consecutive_runs(ordered_cited)
        image_sets = []
        for image in images:
            info = image.get("info")
            if not info:
                continue
            image_figure = manifest_figure_id(info, manifest_figures)
            if image_figure != figure_id:
                continue
            panels = panel_tuple(info["panels"])
            if panels:
                image_sets.append((image.get("line"), panels))
        for run in runs:
            run_tuple = panel_tuple(run)
            if not any(panels == run_tuple for _, panels in image_sets):
                add_issue(
                    stored,
                    f"unit {unit_id}: cited panel run {figure_id}{''.join(run)} has no matching image",
                )
        run_sets = [set(run) for run in runs]
        for line_number, panels in image_sets:
            if not any(set(panels) <= run_set for run_set in run_sets):
                add_issue(
                    stored,
                    f"unit {unit_id}: image panels {panels} span a citation gap or do not match a cited run",
                    line_number,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handbook", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--units", type=Path)
    parser.add_argument("--source", type=Path, help="pdf_inventory.py output directory")
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="skip manifest, asset, image, caption and figure-coverage checks for a no-figure handbook",
    )
    parser.add_argument("--fidelity", action="store_true")
    parser.add_argument("--min-image-px", type=int, default=100)
    parser.add_argument("--asset-index", type=Path)
    parser.add_argument("--reference-handbook", nargs="+", type=Path, help="additional handbooks sharing the assets directory")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    handbook_path = args.handbook.resolve()
    if not handbook_path.exists():
        print(f"ERROR: handbook not found: {handbook_path}", file=sys.stderr)
        return 2
    text = handbook_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors: list[dict] = []
    warnings: list[dict] = []
    stats: dict[str, object] = {}
    text_only = args.text_only
    stats["text_only"] = text_only
    if text_only:
        for option, value in (
            ("--manifest", args.manifest),
            ("--assets-dir", args.assets_dir),
            ("--asset-index", args.asset_index),
            ("--reference-handbook", args.reference_handbook),
        ):
            if value:
                print(f"NOTE: --text-only ignores {option}")

    if not lines:
        add_issue(errors, "handbook is empty")
    elif not HEADING_RE.match(lines[0]) or len(HEADING_RE.match(lines[0]).group(1)) != 1:
        add_issue(errors, "first non-empty line must be an H1 title", 1)

    front = "\n".join(lines[:80])
    if not re.search(r"(?:Source paper|DOI|doi\.org|10\.\d{4,9}/)", front):
        add_issue(errors, "front matter must cite the source paper (DOI or citation)")
    if not re.search(r"(?im)^\s*(?:Scope:|##\s+Scope\b)", front):
        add_issue(errors, "front matter must contain a Scope statement")
    if not re.search(r"(?im)^##\s+Reading conventions\b", front):
        add_issue(errors, "front matter must contain '## Reading conventions'")
    if not re.search(r"(?im)^##\s+Chapter catalogue\b", front):
        add_issue(errors, "front matter must contain '## Chapter catalogue'")

    anchors = build_anchors(lines)
    catalogue_match = re.search(r"(?im)^##\s+Chapter catalogue\b", text)
    if catalogue_match:
        catalogue_start = text[: catalogue_match.start()].count("\n") + 1
        catalogue_lines = lines[catalogue_start:]
        stop = len(catalogue_lines)
        for index, line in enumerate(catalogue_lines):
            if line.strip() == "---" or re.match(r"^#\s+", line):
                stop = index
                break
        links = CATALOGUE_LINK_RE.findall("\n".join(catalogue_lines[:stop]))
        if not links:
            add_issue(errors, "chapter catalogue contains no anchor links", catalogue_start)
        for anchor in links:
            if anchor not in anchors:
                add_issue(errors, f"catalogue anchor does not resolve: #{anchor}", catalogue_start)
        stats["catalogue_links"] = len(links)

    sections = sections_by_heading(lines)
    chapter_sections = [section for section in sections if section["level"] == 1 and section["text"].lower().startswith("chapter ")]
    unit_sections = [section for section in sections if section["level"] == 2 and re.match(r"^\d+\.\d+\b", section["text"])]
    stats["chapters"] = len(chapter_sections)
    stats["units"] = len(unit_sections)
    if not chapter_sections:
        add_issue(errors, "no '# Chapter ...' headings found")

    for chapter in chapter_sections:
        body = "\n".join(lines[chapter["line"] - 1 : chapter["end"]])
        first_unit_line = None
        for section in unit_sections:
            if chapter["line"] < section["line"] <= chapter["end"]:
                first_unit_line = section["line"]
                break
        chapter_body = "\n".join(lines[chapter["line"] - 1 : (first_unit_line or chapter["end"] + 1) - 1])
        if "**Goal and principle.**" not in chapter_body:
            add_issue(errors, f"chapter missing chapter-level goal: {chapter['text']}", chapter["line"])
        if first_unit_line is None:
            add_issue(errors, f"chapter has no numbered units: {chapter['text']}", chapter["line"])

    for unit in unit_sections:
        body = "\n".join(lines[unit["line"] - 1 : unit["end"]])
        for label in ("**Goal and principle.**", "**Methods**", "**Results**"):
            if label not in body:
                add_issue(errors, f"unit {unit['text']} missing {label}", unit["line"])

    end_matter = next(
        (section for section in sections if section["level"] == 1 and "reproducibility notes" in section["text"].lower()),
        None,
    )
    if end_matter is None:
        add_issue(errors, "missing '# Reproducibility notes' section")
    else:
        end_body = "\n".join(lines[end_matter["line"] - 1 : end_matter["end"]])
        for letter in "ABCD":
            if not re.search(rf"(?im)^##\s+{letter}\.", end_body):
                add_issue(errors, f"end matter missing subsection {letter}.")

    assets_dir = None
    manifest = None
    asset_index: dict[str, dict] = {}
    referenced: set[Path] = set()
    image_count = 0
    manifest_figures: list[dict] = []
    if text_only:
        stats["images"] = 0
        stats["images_ignored"] = sum(len(IMAGE_RE.findall(line)) for line in lines)
        stats["figure_checks"] = "skipped"
    else:
        assets_dir = args.assets_dir.resolve() if args.assets_dir else None
        if args.manifest:
            manifest_path = args.manifest.resolve()
            if not manifest_path.exists():
                add_issue(errors, f"manifest not found: {manifest_path}")
            else:
                try:
                    manifest = read_json(manifest_path)
                    paths = manifest_paths(manifest_path, manifest)
                    assets_dir = assets_dir or paths["assets"]
                except Exception as exc:
                    add_issue(errors, f"manifest invalid: {exc}")

        if args.asset_index and args.asset_index.exists():
            try:
                asset_index = read_json(args.asset_index)
            except Exception as exc:
                add_issue(warnings, f"cannot read asset index: {exc}")
        elif assets_dir and (assets_dir / "asset_index.json").exists():
            try:
                asset_index = read_json(assets_dir / "asset_index.json")
            except Exception as exc:
                add_issue(warnings, f"cannot read asset_index.json: {exc}")
        elif manifest is not None:
            asset_index = manifest_asset_index(manifest)

        image_count, referenced = verify_images(
            lines, handbook_path, assets_dir, args.min_image_px, errors, warnings
        )
        stats["images"] = image_count
        if args.reference_handbook:
            for reference_path in args.reference_handbook:
                reference = reference_path.resolve()
                if not reference.exists():
                    add_issue(warnings, f"reference handbook not found: {reference}")
                    continue
                referenced |= collect_referenced_paths(reference)

        manifest_figures = list((manifest or {}).get("figures", []))
        for line_number, line in enumerate(lines, 1):
            match = IMAGE_RE.search(line)
            if not match:
                continue
            asset = Path(link_target(match.group(1))).name
            info = caption_block_info(lines, line_number)
            if info is None:
                add_issue(errors, "image has no bold caption label", line_number)
                continue
            if info.get("prefix") is None:
                add_issue(warnings, f"caption labels span multiple figures: {info['label']}", line_number)
                continue
            entry = asset_index.get(asset)
            if entry is None:
                add_issue(warnings, f"asset is not in the asset index: {asset}", line_number)
                continue
            figure_id = manifest_figure_id(info, manifest_figures)
            if figure_id is None:
                add_issue(warnings, f"caption figure not found in manifest: {info['label']}", line_number)
                continue
            panels = panel_tuple(info["panels"])
            entry_panels = panel_tuple(entry.get("panels", []))
            kind = entry.get("kind")
            if panels:
                if kind == "full":
                    add_issue(errors, f"full-figure asset used for panel caption: {info['label']}", line_number)
                elif kind in {"panel", "panel-set", "group"}:
                    if entry.get("figure") != figure_id:
                        add_issue(errors, f"asset figure {entry.get('figure')} does not match caption {info['label']}", line_number)
                    if entry_panels != panels:
                        add_issue(
                            errors,
                            f"caption panels {panels} do not match asset panels {entry_panels}: {asset}",
                            line_number,
                        )
                    if kind == "panel" and len(panels) != 1:
                        add_issue(errors, "multi-panel caption uses a single-panel asset", line_number)
                    if kind in {"panel-set", "group"} and len(panels) < 2:
                        add_issue(errors, "single-panel caption uses a panel-set asset", line_number)
            else:
                allowed = kind == "full" or (
                    kind == "panel"
                    and len(figure_panel_keys(manifest, figure_id)) == 1
                )
                if not allowed:
                    add_issue(warnings, f"whole-figure caption uses non-full asset: {asset}", line_number)
        if assets_dir is not None and assets_dir.exists():
            assets = {path.resolve() for path in assets_dir.glob("*.png")}
            unreferenced = sorted(path.name for path in assets - referenced)
            stats["assets"] = len(assets)
            stats["unreferenced_assets"] = len(unreferenced)
            for name in unreferenced:
                add_issue(warnings, f"unreferenced asset: {name}")
            if manifest:
                for group in manifest.get("groups", []):
                    filename = group.get("filename")
                    if filename and not (assets_dir / filename).exists():
                        add_issue(warnings, f"manifest group asset missing: {filename}")

    # Formatting checks.
    trailing = [number for number, line in enumerate(lines, 1) if line != line.rstrip()]
    for number in trailing[:10]:
        add_issue(errors, "trailing whitespace", number)
    if trailing:
        add_issue(errors, f"trailing whitespace on {len(trailing)} line(s)")
    if not text.endswith("\n"):
        add_issue(errors, "file must end with a newline")
    elif text.endswith("\n\n"):
        add_issue(errors, "file must end with exactly one newline")

    in_results = False
    in_code = False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if stripped == "**Results**":
            in_results = True
            continue
        if in_results and (
            line.startswith("#")
            or stripped == "---"
            or re.match(r"^\*\*Goal\s*(?:and|&)\s*[Pp]rinciple", stripped)
            or stripped in {"**Methods**", "**Method**"}
        ):
            in_results = False
        if in_results:
            if CAPTION_ITALIC_RE.match(stripped):
                add_issue(errors, "figure caption label must be bold, not italic", number)
            elif CAPTION_PLAIN_RE.match(stripped):
                add_issue(errors, "figure caption label must be bold", number)
    if in_code:
        add_issue(errors, "unbalanced code fence")

    stats["anchors"] = len(anchors)

    units_stats = {}
    if args.units:
        units_stats = check_units(args.units.resolve(), errors, warnings)
        stats.update({f"units_{key}": value for key, value in units_stats.items() if isinstance(value, int)})

        handbook_unit_ids = set()
        for section in unit_sections:
            match = re.match(r"^(\d+\.\d+)\b", section["text"])
            if match:
                handbook_unit_ids.add(match.group(1))
        for missing in sorted(units_stats.get("unit_ids", set()) - handbook_unit_ids):
            add_issue(errors, f"unit {missing} is in units.json but missing from the handbook")
        for extra in sorted(handbook_unit_ids - units_stats.get("unit_ids", set())):
            add_issue(errors, f"unit {extra} is in the handbook but missing from units.json")

        handbook_chapter_ids = set()
        for chapter in chapter_sections:
            match = re.match(r"^Chapter\s+(\d+)\b", chapter["text"], re.IGNORECASE)
            if match:
                handbook_chapter_ids.add(match.group(1))
        for missing in sorted(units_stats.get("chapter_ids", set()) - handbook_chapter_ids):
            add_issue(errors, f"chapter {missing} is in units.json but missing from the handbook")
        for extra in sorted(handbook_chapter_ids - units_stats.get("chapter_ids", set())):
            add_issue(errors, f"chapter {extra} is in the handbook but missing from units.json")

        if not text_only:
            unit_section_by_id = {}
            for section in unit_sections:
                match = re.match(r"^(\d+\.\d+)\b", section["text"])
                if match:
                    unit_section_by_id[match.group(1)] = section
            exceptions = units_stats.get("unit_exceptions", {})
            for unit_id, citations in units_stats.get("unit_evidence", {}).items():
                section = unit_section_by_id.get(unit_id)
                if section is None:
                    continue
                images = collect_unit_images(lines, section["line"], section["end"])
                check_unit_coverage(
                    unit_id,
                    citations,
                    images,
                    manifest,
                    errors,
                    warnings,
                    bool(exceptions.get(unit_id)),
                )

    captions = None
    source_text = None
    if args.source:
        source_dir = args.source.resolve()
        if not text_only:
            captions_path = source_dir / "captions.json"
            if captions_path.exists():
                try:
                    captions = read_json(captions_path)
                except Exception as exc:
                    add_issue(warnings, f"cannot read captions.json: {exc}")
        source_path = source_dir / "source_text.md"
        if source_path.exists():
            source_text = source_path.read_text(encoding="utf-8")
    if not text_only and units_stats.get("evidence"):
        check_coverage(units_stats["evidence"], manifest, captions, errors, warnings)

    if args.fidelity and source_text:
        source_normalized = normalize_number_text(source_text)
        checked = 0
        missing = 0
        in_methods = False
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == "**Methods**":
                in_methods = True
                continue
            if in_methods and (
                stripped == "**Results**"
                or line.startswith("#")
                or re.match(r"^\*\*Goal\s*(?:and|&)\s*[Pp]rinciple", stripped)
            ):
                in_methods = False
            if not in_methods:
                continue
            for token in extract_numbers(line):
                normalized = normalize_number_text(token)
                if len(normalized) < 2:
                    continue
                checked += 1
                if normalized not in source_normalized:
                    missing += 1
                    if missing <= 30:
                        add_issue(warnings, f"number not found verbatim in source: {token}", number)
        stats["fidelity_numbers_checked"] = checked
        stats["fidelity_numbers_not_found"] = missing

    print(f"chapters={stats.get('chapters', 0)}")
    print(f"units={stats.get('units', 0)}")
    print(f"images={stats.get('images', 0)}")
    print(f"text_only={str(text_only).lower()}")
    if text_only:
        print("figure_checks=skipped")
        print(f"images_ignored={stats.get('images_ignored', 0)}")
    print(f"assets={stats.get('assets', 0)}")
    print(f"unreferenced_assets={stats.get('unreferenced_assets', 0)}")
    print(f"errors={len(errors)}")
    print(f"warnings={len(warnings)}")
    for item in errors:
        line_suffix = f" (line {item['line']})" if item.get("line") else ""
        print(f"ERROR: {item['message']}{line_suffix}")
    for item in warnings:
        line_suffix = f" (line {item['line']})" if item.get("line") else ""
        print(f"WARNING: {item['message']}{line_suffix}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {"errors": errors, "warnings": warnings, "stats": stats},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
