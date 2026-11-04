# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Update the MediaBox and CropBox of an uploaded PDF.

This sample demonstrates how to:

1. Load ``PDFREST_API_KEY`` from the environment or a local ``.env`` file.
2. Upload the checked-in ``examples/resources/report.pdf`` input.
3. Enlarge its MediaBox and apply a positive CropBox inset to every page.
4. Print the generated PDF metadata.

Set ``PDFREST_BASE_URL`` only for a self-hosted deployment. Run from the
repository root with
``uv run examples/set_pdf_page_boxes/set_pdf_page_boxes_example.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.types import (
    PdfInsetPageBoxDefinition,
    PdfInsetPageBoxPage,
    PdfMediaBoxDefinition,
    PdfMediaBoxPage,
    PdfPageBoxDefinition,
)

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
INPUT_PATH = RESOURCE_DIRECTORY / "report.pdf"


def set_pdf_page_boxes() -> None:
    """Upload a PDF, update two page boxes, and print the output metadata."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")
    boxes: list[PdfPageBoxDefinition] = [
        PdfMediaBoxDefinition(
            box="media",
            pages=[
                PdfMediaBoxPage(
                    range="all",
                    top=-18,
                    bottom=-18,
                    left=-18,
                    right=-18,
                )
            ],
        ),
        PdfInsetPageBoxDefinition(
            box="crop",
            pages=[
                PdfInsetPageBoxPage(
                    range="all",
                    top=36,
                    bottom=36,
                    left=36,
                    right=36,
                )
            ],
        ),
    ]

    with PdfRestClient(base_url=base_url) as client:
        uploaded_pdf = client.files.create_from_paths(INPUT_PATH)[0]
        response = client.set_pdf_page_boxes(
            uploaded_pdf,
            boxes=boxes,
            output="report-with-page-boxes",
        )

    print(f"Input ID: {response.input_id}")
    print(f"Output file: {response.output_file.name}")
    print(f"Output MIME type: {response.output_file.type}")
    print(f"Output URL: {response.output_file.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    set_pdf_page_boxes()
