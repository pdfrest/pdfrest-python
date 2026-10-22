# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Create a branded ZUGFeRD PDF/A-3 invoice from CII XML.

This sample demonstrates how to:

1. Upload the checked-in invoice XML resource.
2. Generate a ZUGFeRD PDF with typed appearance and locale options.
3. Download and verify the generated PDF.
4. Print the result metadata and input resource IDs.

Set ``PDFREST_API_KEY`` and optionally ``PDFREST_BASE_URL`` for a self-hosted
deployment, then run from the repository root with
``uv run examples/create_zugferd_pdf/create_zugferd_pdf_example.py``. The
required XML input is included in the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.types import PdfZugferdRenderOptions

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
INVOICE_PATH = RESOURCE_DIRECTORY / "zugferd-minimum-invoice.xml"


def create_zugferd_pdf() -> None:
    """Upload invoice resources, create the PDF/A-3 invoice, and verify it."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")
    render_options = PdfZugferdRenderOptions(
        font="courier",
        bold_font="courierbold",
        accent_color=(20, 64, 115),
        locale="de-DE",
        label_language="en",
        currency_display="symbol",
        date_format="dd.MM.yyyy",
        decimal_precision=2,
        footer_message="Thank you for your business.",
    )

    with PdfRestClient(base_url=base_url) as client:
        invoice = client.files.create_from_paths(INVOICE_PATH)[0]
        response = client.create_zugferd_pdf(
            invoice,
            render_options=render_options,
            output="zugferd-invoice",
        )
        pdf_bytes = client.files.read_bytes(response.output_file)

    if not pdf_bytes.startswith(b"%PDF-"):
        msg = "The generated resource is not a PDF."
        raise RuntimeError(msg)

    output = response.output_file
    print(f"Created: {output.name}")
    print(f"MIME type: {output.type}")
    print(f"Size: {output.size} bytes")
    print(f"Input IDs: {', '.join(response.input_ids)}")
    print(f"Download URL: {output.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    create_zugferd_pdf()
