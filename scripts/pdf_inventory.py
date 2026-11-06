"""Extract a page-anchored, source-grounded inventory from a paper PDF.

This script only reports facts and candidates. It does not decide which section is
the Methods section, which figures matter, or how to organize a handbook.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from common import parse_page_selection, pixmap_to_image, save_png, write_json

CAPTION_START_RE = re.compile(
    r"^\s*(?:(?:Extended\s+Data|Supplementary|Suppl\.?)\s+)?(?:Fig(?:ure)?\.?)\s*\d+[A-Za-z]?"
    r"|^\s*Table\s+\d+"
    r"|^\s*Supplementary\s+(?:Fig(?:ure)?|Table)",
    re.IGNORECASE,
)

METHODS_KEYWORDS = [
    "STAR METHOD",
    "STAR★METHOD",
    "Materials and methods",
    "Materials and Methods",
    "KEY RESOURCES TABLE",
    "EXPERIMENTAL MODEL AND STUDY PARTICIPANT DETAILS",
    "METHOD DETAILS",
    "QUANTIFICATION AND STATISTICAL ANALYSIS",
    "Methods",
]


def page_lines(page: pymupdf.Page) -> list[dict]:
    data = page.get_text("dict")
    lines: list[dict] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            sizes = [float(span.get("size", 0)) for span in spans if span.get("text", "").strip()]
            fonts = [str(span.get("font", "")) for span in spans]
            flags = [int(span.get("flags", 0)) for span in spans]
            lines.append(
                {
                    "text": text,
                    "bbox": [round(float(v), 2) for v in line.get("bbox", (0, 0, 0, 0))],
                    "size": round(max(sizes), 2) if sizes else None,
                    "bold": any(flag & 16 for flag in flags) or any("bold" in f.lower() for f in fonts),
                    "font": fonts[0] if fonts else "",
                }
            )
    return lines


def candidate_headings(lines: list[dict], body_size: float) -> list[dict]:
    headings = []
    for line in lines:
        text = line["text"]
        size = line["size"] or 0
        if len(text) > 160 or len(text) < 2:
            continue
        if line["bold"] and size >= body_size + 0.4:
            headings.append({**line, "reason": "bold-larger"})
        elif size >= body_size + 1.6:
            headings.append({**line, "reason": "larger"})
    return headings


def caption_candidates(page: pymupdf.Page) -> list[dict]:
    captions = []
    for block in page.get_text("blocks"):
        text = re.sub(r"\s+", " ", block[4] or "").strip()
        if text and CAPTION_START_RE.match(text):
            captions.append(
                {
                    "text": text,
                    "bbox": [round(float(v), 2) for v in block[:4]],
                }
            )
    return captions


def image_records(page: pymupdf.Page) -> list[dict]:
    records = []
    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox") or (0, 0, 0, 0)
        records.append(
            {
                "xref": int(info.get("xref", 0) or 0),
                "bbox": [round(float(v), 2) for v in bbox],
                "width": int(info.get("width", 0) or 0),
                "height": int(info.get("height", 0) or 0),
                "colorspace": int(info.get("colorspace", 0) or 0),
                "bpc": int(info.get("bpc", 0) or 0),
            }
        )
    return records


def methods_candidates(page_number: int, text: str) -> list[dict]:
    found = []
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    for keyword in METHODS_KEYWORDS:
        needle = keyword.casefold()
        if any(line.casefold() == needle or line.casefold().startswith(needle + " ") for line in lines):
            found.append({"keyword": keyword, "page": page_number})
    return found


def write_source_text(path: Path, records: list[dict]) -> None:
    chunks = []
    for record in records:
        chunks.append(f"<!-- page: {record['page']} -->\n\n{record['text'].rstrip()}\n")
    path.write_text("\n".join(chunks), encoding="utf-8")


def make_contact_sheet(thumbnails: list[tuple[int, Path]], out_path: Path, columns: int = 4) -> None:
    if not thumbnails:
        return
    images = []
    for page, path in thumbnails:
        with Image.open(path) as image:
            images.append((page, image.convert("RGB")))
    cell_width = 260
    gap = 14
    label_height = 18
    rows = (len(images) + columns - 1) // columns
    scaled = []
    cell_height = 0
    for page, image in images:
        scale = cell_width / image.width
        thumb = image.resize((cell_width, max(1, int(image.height * scale))))
        scaled.append((page, thumb))
        cell_height = max(cell_height, thumb.height)
    row_height = cell_height + label_height + gap
    sheet = Image.new(
        "RGB",
        (columns * (cell_width + gap) + gap, rows * row_height + gap),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (page, thumb) in enumerate(scaled):
        row, column = divmod(index, columns)
        x = gap + column * (cell_width + gap)
        y = gap + row * row_height
        draw.text((x, y), f"page {page}", fill="black", font=font)
        sheet.paste(thumb, (x, y + label_height))
    sheet.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pages", help="1-based page selection, e.g. 1-5,13,20-33")
    parser.add_argument("--dpi", type=int, default=100, help="thumbnail render DPI")
    parser.add_argument("--no-thumbnails", action="store_true")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"ERROR: PDF not found: {args.pdf}", file=sys.stderr)
        return 2

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(args.pdf))
    if doc.needs_pass:
        print("ERROR: PDF is encrypted", file=sys.stderr)
        return 2

    selected = parse_page_selection(args.pages, doc.page_count)
    records: list[dict] = []
    captions_all: list[dict] = []
    methods_all: list[dict] = []
    thumbnails: list[tuple[int, Path]] = []
    thumb_dir = out_dir / "thumbnails"
    if not args.no_thumbnails:
        thumb_dir.mkdir(parents=True, exist_ok=True)

    for page_number in selected:
        page = doc[page_number - 1]
        text = page.get_text()
        lines = page_lines(page)
        sizes = [line["size"] for line in lines if line["size"]]
        body_size = round(statistics.median(sizes), 2) if sizes else 10.0
        headings = candidate_headings(lines, body_size)
        captions = caption_candidates(page)
        images = image_records(page)
        methods = methods_candidates(page_number, text)
        methods_all.extend(methods)
        captions_all.extend({"page": page_number, **caption} for caption in captions)
        records.append(
            {
                "page": page_number,
                "width": round(float(page.rect.width), 2),
                "height": round(float(page.rect.height), 2),
                "rotation": int(page.rotation),
                "body_size": body_size,
                "text": text,
                "lines": lines,
                "candidate_headings": headings,
                "caption_candidates": captions,
                "images": images,
                "methods_candidates": methods,
            }
        )

        if not args.no_thumbnails:
            pix = page.get_pixmap(dpi=args.dpi, alpha=False)
            image = pixmap_to_image(pix)
            thumb_path = thumb_dir / f"page-{page_number:03d}.png"
            save_png(image, thumb_path)
            thumbnails.append((page_number, thumb_path))

    write_json(out_dir / "pages.json", records)
    write_source_text(out_dir / "source_text.md", records)
    write_json(out_dir / "captions.json", captions_all)
    write_json(out_dir / "methods_candidates.json", methods_all)

    if thumbnails:
        make_contact_sheet(thumbnails, out_dir / "page_contact_sheet.png")

    summary_lines = [
        f"# PDF inventory: {args.pdf.name}",
        "",
        f"- Pages in PDF: {doc.page_count}",
        f"- Pages inventoried: {len(records)}",
        f"- Text characters: {sum(len(record['text']) for record in records):,}",
        f"- Caption candidates: {len(captions_all)}",
        f"- Thumbnails: {'yes' if thumbnails else 'no'}",
        "",
        "## Methods candidates",
        "",
    ]
    if methods_all:
        for item in methods_all:
            summary_lines.append(f"- page {item['page']}: `{item['keyword']}`")
    else:
        summary_lines.append("- None detected; inspect `source_text.md` manually.")
    summary_lines.extend(["", "## Caption candidates", ""])
    if captions_all:
        for item in captions_all:
            summary_lines.append(f"- page {item['page']}: {item['text'][:220]}")
    else:
        summary_lines.append("- None detected.")
    summary_lines.extend(["", "## Pages with embedded images", ""])
    for record in records:
        if record["images"]:
            summary_lines.append(
                f"- page {record['page']}: {len(record['images'])} image(s), "
                f"first bbox={record['images'][0]['bbox']}"
            )
    (out_dir / "inventory_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    metadata = doc.metadata or {}
    write_json(
        out_dir / "pdf_metadata.json",
        {
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "page_count": doc.page_count,
        },
    )

    print(f"pages_inventoried={len(records)}")
    print(f"captions={len(captions_all)}")
    print(f"methods_candidates={len(methods_all)}")
    print(f"output={out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
