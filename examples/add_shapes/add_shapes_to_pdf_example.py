# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Add a styled panel and divider line to a PDF.

This sample demonstrates how to:

1. Upload the bundled ``examples/resources/report.pdf`` resource.
2. Describe rectangle and line overlays with typed ``PdfAddShapeObject`` values.
3. Add the shapes to page 1 with accessibility tagging enabled.
4. Print metadata for the PDF returned by pdfRest.

Set ``PDFREST_API_KEY``, then run from the repository root with
``uv run examples/add_shapes/add_shapes_to_pdf_example.py``. The input PDF is
included in the repository, so no additional input files are required.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.types import (
    PdfAddLineObject,
    PdfAddRectangleObject,
    PdfAddShapeObject,
)

RESOURCE = Path(__file__).resolve().parents[1] / "resources" / "report.pdf"


def add_shapes_to_report() -> None:
    """Upload the sample report and add a tagged panel and divider line."""
    load_dotenv()
    shapes: list[PdfAddShapeObject] = [
        PdfAddRectangleObject(
            type="rectangle",
            page=1,
            x=54,
            y=540,
            width=504,
            height=108,
            fill_color=(245, 247, 250),
            stroke_color=(26, 72, 112),
            stroke_width=1,
            tag_is_artifact=True,
        ),
        PdfAddLineObject(
            type="line",
            page=1,
            x1=72,
            y1=510,
            x2=540,
            y2=510,
            stroke_color=(220, 45, 55),
            stroke_width=4,
            tag_actual_text="Report section divider",
            tag_structure_type="Figure",
        ),
    ]

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths([RESOURCE])[0]
        response = client.add_shapes_to_pdf(
            uploaded,
            shape_objects=shapes,
            tag_enabled=True,
            output="report-with-shapes",
        )

    output = response.output_file
    print(f"Created {output.name}")
    print(f"Output ID: {output.id}")
    print(f"MIME type: {output.type}")
    print(f"Size: {output.size} bytes")
    print(f"Download URL: {output.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    add_shapes_to_report()
