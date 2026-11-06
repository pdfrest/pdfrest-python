# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Add two uploaded images to a PDF with reusable typed placements.

This example loads ``PDFREST_API_KEY`` (optionally from ``.env``), uploads the
checked-in PDF, PNG, and JPEG fixtures under ``examples/resources/``, adds the
images with sizing and accessible tag metadata, and prints the generated PDF
details.

Run from the repository root with:
``uv run examples/add_images/add_images_to_pdf_example.py``.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.types import PdfAddImageObject

load_dotenv()

resources_directory = Path(__file__).resolve().parents[1] / "resources"
pdf_path = resources_directory / "report.pdf"
image_paths = [
    resources_directory / "image-overlay-logo.png",
    resources_directory / "image-overlay-photo.jpg",
]

with PdfRestClient(api_key=os.environ["PDFREST_API_KEY"]) as client:
    source_pdf = client.files.create_from_paths([pdf_path])[0]
    logo, photo = client.files.create_from_paths(image_paths)
    placements: list[PdfAddImageObject] = [
        PdfAddImageObject(
            image=logo,
            page="1-last",
            x=36,
            y=36,
            width=72,
            tag_alt_text="Company logo",
            tag_structure_type="Figure",
        ),
        PdfAddImageObject(
            image=photo,
            page=1,
            x=144,
            y=36,
            height=72,
            tag_alt_text="Sample photograph",
            tag_structure_type="Figure",
        ),
    ]
    response = client.add_images_to_pdf(
        source_pdf,
        image_objects=placements,
        tag_enabled=True,
        tag_language="en-US",
        output="report-with-images",
    )

print(f"Created: {response.output_file.name}")
print(f"MIME type: {response.output_file.type}")
print(f"Size: {response.output_file.size} bytes")
print(f"URL: {response.output_file.url}")
