"""Conservatively normalize a methods handbook's Markdown formatting.

Safe transformations only: trailing whitespace, final newline, blank-line
separation, list markers, canonical section labels, and bold figure-caption
labels inside Results blocks. Prose is never reflowed or rewritten.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

LABEL = (
    r"(?:(?:Extended\s+Data|Supplementary|Suppl\.?|ED)\s+)?"
    r"(?:Fig(?:ure)?\.?)\s*\d+[A-Za-z]?"
    r"(?:\s*(?:[\u2013-]|,)\s*[A-Za-z])?"
    r"(?:\s*\([^)]*\))?"
)
CAPTION_RE = re.compile(rf"^(?P<label>{LABEL})\s*:\s*(?P<rest>.*)$")
CAPTION_BOLD_RE = re.compile(rf"^\*\*(?P<label>{LABEL})\*\*\s*:\s*(?P<rest>.*)$")
CAPTION_ITALIC_RE = re.compile(rf"^\*(?P<label>{LABEL})\*\s*:\s*(?P<rest>.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s")
IMAGE_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s")


def classify(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if stripped.startswith("```") or stripped.startswith("~~~"):
        return "fence"
    if HEADING_RE.match(stripped):
        return "heading"
    if IMAGE_RE.match(stripped):
        return "image"
    if stripped.startswith("|"):
        return "table"
    if stripped == "---":
        return "hr"
    if CAPTION_BOLD_RE.match(stripped):
        return "caption"
    if LIST_RE.match(line):
        return "list"
    return "text"


def next_kind(lines: list[str], index: int) -> str | None:
    for candidate in lines[index + 1 :]:
        kind = classify(candidate)
        if kind != "blank":
            return kind
    return None


def normalize_line(line: str, in_results: bool) -> tuple[str, bool, bool]:
    original = line
    section_changed = False
    caption_changed = False

    normalized = re.sub(
        r"\*\*Goal\s*(?:and|&)\s*[Pp]rinciple\.?\*\*",
        "**Goal and principle.**",
        line,
    )
    normalized = re.sub(r"\*\*Method\*\*\s*$", "**Methods**", normalized)
    normalized = re.sub(r"\*\*Result\*\*\s*$", "**Results**", normalized)
    if normalized != line:
        section_changed = True

    if in_results:
        stripped = normalized.strip()
        match = CAPTION_BOLD_RE.match(stripped)
        if not match:
            match = CAPTION_ITALIC_RE.match(stripped)
            if match:
                normalized = f"**{match.group('label')}**: {match.group('rest')}"
                caption_changed = True
            else:
                match = CAPTION_RE.match(stripped)
                if match:
                    normalized = f"**{match.group('label')}**: {match.group('rest')}"
                    caption_changed = True

    normalized = normalized.rstrip()
    return normalized, section_changed, caption_changed


def normalize_spacing(lines: list[str]) -> list[str]:
    out: list[str] = []
    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index].rstrip()
        kind = classify(line)
        stripped = line.strip()

        if kind == "blank":
            previous = classify(out[-1]) if out else "blank"
            following = next_kind(lines, index)
            skip = previous in {"list", "caption"} and following == previous
            if not skip and out and out[-1].strip():
                out.append("")
            index += 1
            continue

        if kind == "fence":
            if out and out[-1].strip():
                out.append("")
            out.append(line)
            fence_marker = stripped[:3]
            index += 1
            while index < len(lines):
                inner = lines[index].rstrip()
                out.append(inner)
                index += 1
                if inner.strip().startswith(fence_marker):
                    break
            out.append("")
            continue

        previous_kind = classify(out[-1]) if out else None
        previous_text = out[-1].strip() if out else ""

        if kind == "table":
            if previous_kind != "table" and out and out[-1].strip():
                out.append("")
        elif kind in {"heading", "image", "hr"}:
            if out and out[-1].strip():
                out.append("")
        elif kind == "caption":
            if previous_kind not in {None, "blank", "caption"}:
                if out and out[-1].strip():
                    out.append("")
        elif kind == "list":
            if previous_kind not in {None, "blank", "list"}:
                allowed_after = previous_text in {"**Methods**", "**Results**", "**Goal and principle.**"}
                if not allowed_after and out and out[-1].strip():
                    out.append("")

        out.append(line)

        following = next_kind(lines, index)
        if kind == "table":
            if following != "table":
                out.append("")
        elif kind in {"heading", "image", "hr"}:
            out.append("")
        elif kind == "caption" and following != "caption":
            out.append("")
        elif kind == "list" and following != "list":
            out.append("")

        index += 1

    while out and not out[-1].strip():
        out.pop()
    return out


def format_text(text: str) -> tuple[str, dict[str, int]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = text.split("\n")
    stats = {
        "captions_bolded": 0,
        "section_labels_normalized": 0,
        "trailing_whitespace_removed": 0,
        "lines_changed": 0,
    }

    transformed: list[str] = []
    in_results = False
    for line in raw_lines:
        stripped = line.strip()
        if stripped == "**Results**":
            in_results = True
            transformed.append(line)
            continue
        if in_results and (
            line.startswith("#")
            or stripped == "---"
            or re.match(r"^\*\*Goal\s*(?:and|&)\s*[Pp]rinciple", stripped)
            or stripped in {"**Methods**", "**Method**"}
        ):
            in_results = False

        normalized, section_changed, caption_changed = normalize_line(line, in_results)
        if line.rstrip() != line:
            stats["trailing_whitespace_removed"] += 1
        if section_changed:
            stats["section_labels_normalized"] += 1
        if caption_changed:
            stats["captions_bolded"] += 1
        if normalized != line:
            stats["lines_changed"] += 1
        transformed.append(normalized)

    spaced = normalize_spacing(transformed)
    result = "\n".join(spaced) + "\n"
    if result != text:
        stats["lines_changed"] = max(stats["lines_changed"], 1)
    return result, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handbook", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="write changes (default: check only)")
    parser.add_argument("--check", action="store_true", help="check only; exit 1 when changes are needed")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    handbook = args.handbook.resolve()
    if not handbook.exists():
        print(f"ERROR: handbook not found: {handbook}", file=sys.stderr)
        return 2
    original = handbook.read_text(encoding="utf-8")
    formatted, stats = format_text(original)
    changed = formatted != original

    if args.json_out:
        import json

        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"changed": changed, **stats}, indent=2) + "\n",
            encoding="utf-8",
        )
    for key, value in stats.items():
        print(f"{key}={value}")
    print(f"changed={'yes' if changed else 'no'}")

    if not args.write:
        return 1 if changed else 0

    if not changed:
        return 0
    if args.backup:
        backup_dir = args.backup_dir or (handbook.parent / "_backup")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"{handbook.stem}_{stamp}{handbook.suffix}.bak"
        shutil.copy2(handbook, backup)
        print(f"backup={backup}")
    handbook.write_text(formatted, encoding="utf-8")
    print(f"written={handbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
