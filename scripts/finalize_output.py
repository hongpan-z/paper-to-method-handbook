"""Remove temporary workflow files from a skill output directory.

The skill delivers only the handbook Markdown and its assets directory. This
script removes known intermediate artifacts after verification. It never
deletes handbooks, assets, source PDFs, or paths outside --output.
Use --keep-work to retain all intermediate files.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TOP_LEVEL_DIRS = (
    "source",
    "working",
    "_calibration",
    "_qa",
    "_backup",
    "thumbnails",
)
TOP_LEVEL_FILES = (
    "scope.md",
    "pages.json",
    "source_text.md",
    "captions.json",
    "methods_candidates.json",
    "inventory_summary.md",
    "pdf_metadata.json",
    "page_contact_sheet.png",
    "asset_index.json",
)
FILE_PATTERNS = (
    "qa_report*.md",
    "qa_report*.json",
    "*_report.json",
    "paper_manifest*.json",
    "*.bak",
)
ASSET_INTERMEDIATE = "asset_index.json"


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def display(path: Path, output: Path) -> str:
    try:
        return str(path.relative_to(output))
    except ValueError:
        return str(path)


def resolve_kept(
    values: list[Path] | None,
    output: Path,
    kind: str,
    expect_dir: bool,
) -> list[Path] | None:
    if not values:
        return []
    kept: list[Path] = []
    for value in values:
        path = value.resolve()
        if not path.exists():
            print(f"ERROR: {kind} not found: {path}", file=sys.stderr)
            return None
        if not is_relative_to(path, output):
            print(f"ERROR: {kind} is outside output: {path}", file=sys.stderr)
            return None
        if expect_dir and not path.is_dir():
            print(f"ERROR: {kind} is not a directory: {path}", file=sys.stderr)
            return None
        if not expect_dir and not path.is_file():
            print(f"ERROR: {kind} is not a file: {path}", file=sys.stderr)
            return None
        kept.append(path)
    return kept


def auto_handbooks(output: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for path in output.glob("*.md")
        if path.is_file() and not path.name.startswith("qa_report") and path.name != "scope.md"
    )


def auto_assets(output: Path) -> list[Path]:
    return sorted(
        path.resolve() for path in output.glob("*.assets") if path.is_dir()
    )


def collect_candidates(
    output: Path,
    handbooks: list[Path],
    assets: list[Path],
) -> list[Path]:
    keep = set(handbooks) | set(assets)
    candidates: list[Path] = []

    for name in TOP_LEVEL_DIRS:
        path = output / name
        if path.exists():
            candidates.append(path.resolve())
    for name in TOP_LEVEL_FILES:
        path = output / name
        if path.exists():
            candidates.append(path.resolve())
    for pattern in FILE_PATTERNS:
        for path in output.glob(pattern):
            candidates.append(path.resolve())
    for assets_dir in assets:
        index = assets_dir / ASSET_INTERMEDIATE
        if index.exists():
            candidates.append(index.resolve())

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(candidates, key=lambda item: (len(item.parts), str(item))):
        if path in seen:
            continue
        seen.add(path)
        if not is_relative_to(path, output):
            continue
        if path in keep:
            continue
        if any(path in kept.parents for kept in keep):
            continue
        unique.append(path)
    return unique


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def print_entries(output: Path) -> None:
    entries = sorted(path.name for path in output.iterdir())
    print(f"final_entries={', '.join(entries) if entries else '(empty)'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--handbook",
        nargs="+",
        type=Path,
        help="handbook file(s) to keep; default: top-level Markdown files",
    )
    parser.add_argument(
        "--assets-dir",
        nargs="+",
        type=Path,
        help="assets directory to keep; default: top-level *.assets directories",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="retain all intermediate files instead of removing them",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete files; without this flag the script only prints a dry run",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    if not output.is_dir():
        print(f"ERROR: output directory not found: {output}", file=sys.stderr)
        return 2

    handbooks = resolve_kept(args.handbook, output, "handbook", expect_dir=False)
    if handbooks is None:
        return 2
    assets = resolve_kept(args.assets_dir, output, "assets directory", expect_dir=True)
    if assets is None:
        return 2
    if not args.handbook:
        handbooks = auto_handbooks(output)
    if not args.assets_dir:
        assets = auto_assets(output)

    if args.keep_work:
        print("keep_work=true")
        print_entries(output)
        return 0

    removals = collect_candidates(output, handbooks, assets)
    if not removals:
        print("No intermediate files found.")
        print_entries(output)
        return 0

    for path in removals:
        label = display(path, output)
        if args.apply:
            remove_path(path)
            print(f"REMOVED {label}")
        else:
            print(f"WOULD REMOVE {label}")

    if args.apply:
        print_entries(output)
    else:
        print("dry_run=true (pass --apply to remove these files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
