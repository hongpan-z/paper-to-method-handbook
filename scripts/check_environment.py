"""Check the Python runtime and required PDF dependencies.

This script uses only the standard library so it can run before PyMuPDF and
Pillow are installed. It exits 0 only when Python 3.10+ is running and both
required packages import successfully. Missing dependencies do not prevent a
text-only handbook, so the fallback instructions are printed as well.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

MIN_VERSION = (3, 10)
REQUIRED = (
    ("pymupdf", "PyMuPDF", "pymupdf"),
    ("PIL.Image", "Pillow", "PIL"),
)
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"


def module_version(module) -> str:
    if module is None:
        return "unknown"
    value = getattr(module, "__version__", None)
    if value is None:
        value = getattr(module, "version", None)
    if isinstance(value, tuple):
        return ".".join(str(part) for part in value)
    if value:
        return str(value)
    return "unknown"


def probe(import_name: str, version_module: str) -> tuple[bool, str, str]:
    try:
        importlib.import_module(import_name)
    except Exception as exc:  # ImportError or a broken binary build
        return False, "", f"{type(exc).__name__}: {exc}"
    try:
        module = importlib.import_module(version_module)
    except Exception:
        module = None
    return True, module_version(module), ""


def main() -> int:
    python_ok = sys.version_info >= MIN_VERSION
    print(
        f"Python: {sys.version.split()[0]} "
        f"({'ok' if python_ok else 'MISSING'}; requires >={MIN_VERSION[0]}.{MIN_VERSION[1]})"
    )

    missing: list[str] = []
    for import_name, display_name, version_module in REQUIRED:
        available, version, error = probe(import_name, version_module)
        if available:
            print(f"{display_name}: {version} (ok)")
        else:
            print(f"{display_name}: MISSING")
            if error:
                print(f"  reason: {error}")
            missing.append(display_name)

    pdftotext = shutil.which("pdftotext")
    print(f"pdftotext: {pdftotext if pdftotext else 'not found (optional)'}")

    if not python_ok:
        print("")
        print("Upgrade Python to 3.10 or newer before running the PDF scripts.")
        if shutil.which("uv"):
            print("With uv: uv python install 3.10")

    if missing:
        print("")
        print("Install the required packages before running the PDF scripts.")
        if shutil.which("uv"):
            print("Ephemeral uv environment (no project files changed):")
            print(
                "  uv run --with pymupdf --with pillow python scripts/pdf_inventory.py ..."
            )
        else:
            print("uv is not installed; use pip or a virtual environment below.")
        print("")
        print("pip:")
        print(f"  python -m pip install -r \"{REQUIREMENTS}\"")
        print("")
        print("virtual environment:")
        print("  python -m venv .venv")
        print(
            f"  Windows: .venv\\Scripts\\python -m pip install -r \"{REQUIREMENTS}\""
        )
        print(
            f"  macOS/Linux: .venv/bin/python -m pip install -r \"{REQUIREMENTS}\""
        )
        print("")
        print("If installation is not possible, extract text and use the text-only fallback:")
        print("  pdftotext paper.pdf source/source_text.md")
        print(
            "  python scripts/verify_handbook.py --handbook handbook.md "
            "--units working/units.json --text-only --strict"
        )

    if not python_ok or missing:
        return 1
    print("")
    print("Environment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
