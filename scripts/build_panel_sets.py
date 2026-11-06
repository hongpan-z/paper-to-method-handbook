"""Build consecutive-run panel sets from structured unit citations.

Reads `units.json`, collects the panels cited by each unit (or each
`result_blocks` entry), splits them into maximal consecutive runs, and writes
`panel_sets` entries into the paper manifest.

The LLM still decides which panels are cited. This script only applies the
mechanical rule: a group is allowed only for consecutive panel letters.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    expand_panel_letters,
    panel_run_string,
    panel_set_filename,
    parse_figure_label,
    read_json,
    split_consecutive_runs,
    write_json,
)


def figure_candidates(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("figures", []))


def resolve_figure(label: str, figures: list[dict[str, Any]]) -> dict[str, Any] | None:
    for figure in figures:
        if str(figure.get("id")) == label:
            return figure
    parsed = parse_figure_label(label)
    if not parsed:
        return None
    for figure in figures:
        candidate = parse_figure_label(str(figure.get("id", "")))
        if (
            candidate
            and candidate["prefix"] == parsed["prefix"]
            and candidate["number"] == parsed["number"]
        ):
            return figure
    return None


def panel_lookup(figure: dict[str, Any]) -> dict[str, str]:
    return {str(key).upper(): key for key in (figure.get("panels") or {}) if str(key)}


def figure_panel_order(figure: dict[str, Any]) -> list[str]:
    return sorted(panel_lookup(figure).keys())


def collect_runs(
    citations: list[str],
    figures: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    by_figure: dict[str, set[str]] = {}
    unparsed: list[str] = []
    for label in citations:
        figure = resolve_figure(str(label), figures)
        if figure is None:
            unparsed.append(str(label))
            continue
        parsed = parse_figure_label(str(label))
        if not parsed or not parsed["panels_raw"]:
            continue
        letters = expand_panel_letters(parsed["panels_raw"])
        if not letters:
            continue
        lookup = panel_lookup(figure)
        missing = [letter for letter in letters if letter not in lookup]
        if missing:
            warnings.append(f"{label}: panels not found in {figure.get('id')}: {missing}")
            continue
        by_figure.setdefault(str(figure.get("id")), set()).update(letters)

    panel_sets: list[dict[str, Any]] = []
    for figure_id, letters in sorted(by_figure.items()):
        figure = next(item for item in figures if str(item.get("id")) == figure_id)
        lookup = panel_lookup(figure)
        # Preserve the figure's panel order before splitting into runs.
        ordered = [letter for letter in figure_panel_order(figure) if letter in letters]
        runs = split_consecutive_runs(ordered)
        for run in runs:
            if len(run) < 2:
                continue
            keys = [lookup[letter] for letter in run]
            run_id = f"{figure_id}{panel_run_string(run)}"
            panel_sets.append(
                {
                    "id": run_id,
                    "figure": figure_id,
                    "panels": keys,
                    "filename": panel_set_filename(figure_id, keys),
                }
            )
    return panel_sets, unparsed, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="write panel_sets into the manifest")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--keep-existing", action="store_true", help="merge with existing panel_sets")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    units_path = args.units.resolve()
    manifest_path = args.manifest.resolve()
    if not units_path.exists():
        print(f"ERROR: units file not found: {units_path}", file=sys.stderr)
        return 2
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    units = read_json(units_path)
    manifest = read_json(manifest_path)
    figures = figure_candidates(manifest)
    warnings: list[str] = []
    all_sets: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    unit_report: list[dict[str, Any]] = []

    for chapter in units.get("chapters", []):
        for unit in chapter.get("units", []):
            blocks = unit.get("result_blocks") or [{"evidence": unit.get("evidence", [])}]
            citations: list[str] = []
            for block in blocks:
                citations.extend(str(item) for item in (block.get("evidence") or []))
            sets, unparsed, _ = collect_runs(citations, figures, warnings)
            unit_sets: list[dict[str, Any]] = []
            for panel_set in sets:
                key = (str(panel_set["figure"]), tuple(str(p).upper() for p in panel_set["panels"]))
                all_sets.setdefault(key, panel_set)
                unit_sets.append(panel_set)
            if unparsed:
                warnings.append(f"{unit.get('id')}: could not resolve {unparsed}")
            unit_report.append({"unit": unit.get("id"), "panel_sets": unit_sets})

    panel_sets = sorted(all_sets.values(), key=lambda item: (str(item["figure"]), item["id"]))
    if args.keep_existing:
        existing = {str(item.get("id")): item for item in manifest.get("panel_sets", [])}
        for item in panel_sets:
            existing[item["id"]] = item
        panel_sets = sorted(existing.values(), key=lambda item: (str(item["figure"]), item["id"]))

    print(f"panel_sets={len(panel_sets)}")
    print(f"warnings={len(warnings)}")
    for panel_set in panel_sets:
        print(f"  {panel_set['id']}: {panel_set['panels']} -> {panel_set['filename']}")
    for warning in warnings:
        print(f"WARNING: {warning}")

    if args.report:
        write_json(args.report, {"panel_sets": panel_sets, "units": unit_report, "warnings": warnings})

    if not args.write:
        return 0

    if args.backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = manifest_path.with_name(f"{manifest_path.stem}_{stamp}{manifest_path.suffix}.bak")
        shutil.copy2(manifest_path, backup)
        print(f"backup={backup}")

    manifest["panel_sets"] = panel_sets
    write_json(manifest_path, manifest)
    print(f"written={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
