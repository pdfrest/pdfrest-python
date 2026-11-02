# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Create and validate a ZUGFeRD PDF/A-3 invoice.

This sample demonstrates how to:

1. Upload the checked-in CII invoice XML resource.
2. Create a ZUGFeRD PDF/A-3 invoice to use as deterministic validation input.
3. Validate its embedded XML, package metadata, visible content, and PDF/A-3
   conformance.
4. Print the typed validation status and any findings.

Set ``PDFREST_API_KEY`` and optionally ``PDFREST_BASE_URL`` for a self-hosted
deployment, then run from the repository root with
``uv run examples/validate_zugferd_pdf/validate_zugferd_pdf_example.py``. The
required XML input is included in the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
INVOICE_PATH = RESOURCE_DIRECTORY / "zugferd-minimum-invoice.xml"


def validate_zugferd_pdf() -> None:
    """Create a deterministic ZUGFeRD PDF and validate its conformance."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")

    with PdfRestClient(base_url=base_url) as client:
        invoice = client.files.create_from_paths(INVOICE_PATH)[0]
        created = client.create_zugferd_pdf(
            invoice,
            output="zugferd-validation-example",
        )
        validation = client.validate_zugferd_pdf(created.output_file)

    print(f"Status: {validation.status}")
    print(f"PDF/A-3 conformant: {validation.pdfa}")
    print(f"Content match: {validation.content_match_status}")
    print(f"Input ID: {validation.input_id}")
    print(f"Input URL: {validation.input_url}")
    if validation.message:
        print(f"Notice: {validation.message}")
    for finding in validation.findings or []:
        print(f"{finding.severity}: {finding.code} — {finding.message}")


if __name__ == "__main__":  # pragma: no cover - manual example
    validate_zugferd_pdf()
