# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Create a ZUGFeRD PDF/A-3 invoice from a visual PDF and CII XML.

This sample demonstrates how to:

1. Upload the checked-in PDF and invoice XML resources.
2. Combine them while explicitly allowing a regenerated visual PDF when the
   supplied PDF does not match the invoice data.
3. Download and verify the resulting ZUGFeRD PDF.
4. Print the result metadata and input resource IDs.

Set ``PDFREST_API_KEY`` and optionally ``PDFREST_BASE_URL`` for a self-hosted
deployment, then run from the repository root with
``uv run examples/convert_pdf_to_zugferd_pdf/convert_pdf_to_zugferd_pdf_example.py``.
The required inputs are included in the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
PDF_PATH = RESOURCE_DIRECTORY / "report.pdf"
INVOICE_PATH = RESOURCE_DIRECTORY / "zugferd-minimum-invoice.xml"


def convert_pdf_to_zugferd_pdf() -> None:
    """Upload PDF/XML inputs, create the PDF/A-3 invoice, and verify it."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")

    with PdfRestClient(base_url=base_url) as client:
        pdf, invoice = client.files.create_from_paths([PDF_PATH, INVOICE_PATH])
        response = client.convert_pdf_to_zugferd_pdf(
            pdf,
            invoice=invoice,
            allow_regeneration=True,
            output="zugferd-from-pdf",
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
    convert_pdf_to_zugferd_pdf()
