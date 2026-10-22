# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Convert selected PDF pages to PostScript and verify the result.

This sample demonstrates how to:

1. Upload the checked-in PDF resource.
2. Convert selected pages to level 3 PostScript with print controls.
3. Download the result and verify its PostScript header and page markers.
4. Print the generated file's metadata and download URL.

Set ``PDFREST_API_KEY`` and optionally ``PDFREST_BASE_URL`` for a self-hosted
deployment, then run from the repository root with
``uv run examples/convert_pdf_to_postscript/convert_pdf_to_postscript_example.py``.
The required input PDF is included in the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
PDF_PATH = RESOURCE_DIRECTORY / "report.pdf"


def _language_level(postscript: bytes, expected_level: int) -> str:
    """Return and verify the generated PostScript language-level marker."""
    expected = f"%%LanguageLevel: {expected_level}".encode()
    if expected not in postscript.splitlines():
        msg = f"The generated file is not PostScript level {expected_level}."
        raise RuntimeError(msg)
    return expected.decode("ascii")


def convert_pdf_to_postscript() -> None:
    """Upload a PDF, convert selected pages, and verify the PostScript."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")

    with PdfRestClient(base_url=base_url) as client:
        source = client.files.create_from_paths(PDF_PATH)[0]
        response = client.convert_pdf_to_postscript(
            source,
            ps_level=3,
            page_range="1-last",
            binary_output=False,
            scale=1,
            shrink_to_fit=True,
            print_annotations=False,
            output="print-ready",
        )
        postscript = client.files.read_bytes(response.output_file)

    output = response.output_file
    if not postscript.startswith(b"%!PS-Adobe"):
        msg = "The generated file does not have a PostScript header."
        raise RuntimeError(msg)
    language_level = _language_level(postscript, 3)

    print(f"Created: {output.name}")
    print(f"MIME type: {output.type}")
    print(f"Size: {output.size} bytes")
    print(f"Header: {postscript.splitlines()[0].decode('ascii')}")
    print(f"Language level: {language_level}")
    print(f"Pages: {postscript.count(b'%%Page:')}")
    print(f"Download URL: {output.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    convert_pdf_to_postscript()
