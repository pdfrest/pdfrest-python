# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Apply a text-and-data-mining reservation policy to a PDF.

This sample demonstrates how to:

1. Load ``PDFREST_API_KEY`` from the environment or a local ``.env`` file.
2. Upload the checked-in ``examples/resources/report.pdf`` input.
3. Embed a URL for hosted TDM terms or a machine-readable policy document.
4. Print the generated PDF metadata.

Replace ``POLICY_URL`` with the URL of your hosted policy in a real integration.
Set ``PDFREST_BASE_URL`` only for a self-hosted deployment. pdfRest stores the
URL without fetching or inspecting its destination. Run from the repository root with
``uv run examples/apply_tdm_reservation/apply_tdm_reservation_example.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
INPUT_PATH = RESOURCE_DIRECTORY / "report.pdf"
POLICY_URL = "https://example.com/terms/tdm-policy"


def apply_tdm_reservation() -> None:
    """Upload a PDF and add a URL-based TDM reservation policy."""
    load_dotenv()
    base_url = os.getenv("PDFREST_BASE_URL")

    with PdfRestClient(base_url=base_url) as client:
        uploaded_pdf = client.files.create_from_paths(INPUT_PATH)[0]
        response = client.apply_tdm_reservation(
            uploaded_pdf,
            policy=POLICY_URL,
            output="report-with-tdm-reservation",
        )

    print(f"Input ID: {response.input_id}")
    print(f"Output file: {response.output_file.name}")
    print(f"Output MIME type: {response.output_file.type}")
    print(f"Output URL: {response.output_file.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    apply_tdm_reservation()
