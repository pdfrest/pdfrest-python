# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Convert an uploaded PDF to sRGB with a perceptual rendering intent.

This sample demonstrates how to:

1. Load ``PDFREST_API_KEY`` from the environment or a local ``.env`` file.
2. Upload the checked-in ``examples/resources/report.pdf`` input.
3. Convert its colors to sRGB while preserving visual color relationships.
4. Print the generated PDF metadata.

Set ``PDFREST_BASE_URL`` only for a self-hosted deployment. Run from the
repository root with
``uv run examples/convert_colors/convert_pdf_colors_example.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.types import PdfRenderingIntent

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
INPUT_PATH = RESOURCE_DIRECTORY / "report.pdf"


def convert_pdf_colors() -> None:
    """Upload a PDF, convert its colors, and print the output metadata."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")
    rendering_intent: PdfRenderingIntent = "perceptual"

    with PdfRestClient(base_url=base_url) as client:
        uploaded_pdf = client.files.create_from_paths(INPUT_PATH)[0]
        response = client.convert_colors(
            uploaded_pdf,
            color_profile="srgb",
            rendering_intent=rendering_intent,
            output="report-srgb",
        )

    print(f"Input ID: {response.input_id}")
    print(f"Output file: {response.output_file.name}")
    print(f"Output MIME type: {response.output_file.type}")
    print(f"Output URL: {response.output_file.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    convert_pdf_colors()
