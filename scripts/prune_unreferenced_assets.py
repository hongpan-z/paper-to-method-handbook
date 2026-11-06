"""Report or move assets that are not referenced by the handbook.

Moves, never deletes. Dry-run by default.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from common import manifest_paths, read_json

IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
INLINE_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


def target_path(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if target.split():
        target = target.split()[0]
    target = unquote(target)
    return target.split("#", 1)[0].split("?", 1)[0]


def referenced_assets(handbook: Path) -> set[Path]:
    text = handbook.read_text(encoding="utf-8")
    raw_targets = IMAGE_RE.findall(text) + INLINE_LINK_RE.findall(text) + HTML_IMG_RE.findall(text)
    referenced: set[Path] = set()
    for raw in raw_targets:
        target = target_path(raw)
        if not target:
            continue
        path = Path(target)
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if not path.is_absolute():
            path = handbook.parent / path
        referenced.add(path.resolve())
    return referenced


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handbook", required=True, nargs="+", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    handbooks = [path.resolve() for path in args.handbook]
    for handbook in handbooks:
        if not handbook.exists():
            print(f"ERROR: handbook not found: {handbook}", file=sys.stderr)
            return 2

    assets_dir = args.assets
    if assets_dir is None and args.manifest:
        manifest_path = args.manifest.resolve()
        manifest = read_json(manifest_path)
        assets_dir = manifest_paths(manifest_path, manifest)["assets"]
    if assets_dir is None:
        print("ERROR: provide --assets or --manifest", file=sys.stderr)
        return 2
    assets_dir = assets_dir.resolve()
    if not assets_dir.exists():
        print(f"ERROR: assets directory not found: {assets_dir}", file=sys.stderr)
        return 2

    referenced: set[Path] = set()
    for handbook in handbooks:
        referenced |= referenced_assets(handbook)
    assets = sorted(path for path in assets_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    redundant = [path for path in assets if path.resolve() not in referenced]
    total = sum(path.stat().st_size for path in redundant)

    print(f"referenced_images={len(referenced)}")
    print(f"asset_files={len(assets)}")
    print(f"unreferenced_files={len(redundant)}")
    print(f"unreferenced_MB={total / (1024 * 1024):.2f}")
    for path in redundant:
        print(path.name)

    result = {
        "referenced_images": len(referenced),
        "asset_files": len(assets),
        "unreferenced_files": len(redundant),
        "unreferenced_bytes": total,
        "unreferenced": [path.name for path in redundant],
    }

    if args.apply and redundant:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = args.backup_dir or (assets_dir.parent / "_backup" / f"unreferenced_assets_{stamp}")
        backup_dir.mkdir(parents=True, exist_ok=True)
        for path in redundant:
            shutil.move(str(path), str(backup_dir / path.name))
        result["moved_to"] = str(backup_dir)
        print(f"moved_to={backup_dir}")

    if args.json_out:
        import json

        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
