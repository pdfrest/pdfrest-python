# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Add tagged English text to a PDF for accessible reading and extraction.

This sample demonstrates how to:

1. Upload the bundled ``examples/resources/report.pdf`` resource.
2. Describe a text overlay with the typed ``PdfAddTextObject`` contract.
3. Enable tagging and identify the added text with a BCP 47 language tag.
4. Print metadata for the PDF returned by pdfRest.

Set ``PDFREST_API_KEY``, then run from the repository root with
``uv run examples/add_text/add_tagged_text_to_pdf_example.py``. The input PDF
is included in the repository, so no additional input files are required.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.types import PdfAddTextObject

RESOURCE = Path(__file__).resolve().parents[1] / "resources" / "report.pdf"


def add_tagged_text_to_report() -> None:
    """Upload the sample report and add an accessible English heading."""
    load_dotenv()
    heading = PdfAddTextObject(
        font="Arial Bold",
        max_width=468,
        opacity=1,
        page=1,
        rotation=0,
        text="Quarterly report",
        text_color_rgb=(26, 72, 112),
        text_size=24,
        x=72,
        y=684,
    )

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths([RESOURCE])[0]
        response = client.add_text_to_pdf(
            uploaded,
            text_objects=heading,
            tag_enabled=True,
            tag_language="en-US",
            output="report-with-tagged-text",
        )

    output = response.output_file
    print(f"Created {output.name}")
    print(f"Output ID: {output.id}")
    print(f"MIME type: {output.type}")
    print(f"Size: {output.size} bytes")
    print(f"Download URL: {output.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    add_tagged_text_to_report()
