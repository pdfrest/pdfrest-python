# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Convert a password-protected PDF into PNG images.

This sample demonstrates how to:

1. Upload the bundled ``examples/resources/report.pdf`` resource.
2. Add an open password to create a protected PDF.
3. Supply that password to ``convert_to_png``.
4. Print metadata for every generated PNG image.

Set ``PDFREST_API_KEY``, then run from the repository root with
``uv run examples/convert_to_image/convert_password_protected_pdf_to_png_example.py``.
The input PDF is included in the repository, so no additional files are required.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient

RESOURCE = Path(__file__).resolve().parents[1] / "resources" / "report.pdf"
PASSWORD = "example-password"  # noqa: S105 - Demonstration-only password.


def convert_password_protected_pdf() -> None:
    """Protect the sample PDF, then convert its pages with the same password."""
    load_dotenv()

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths([RESOURCE])[0]
        protected = client.add_open_password(
            uploaded,
            new_open_password=PASSWORD,
            output="password-protected-report",
        ).output_file
        response = client.convert_to_png(
            protected,
            password=PASSWORD,
            output_prefix="password-protected-report-page",
        )

    print(f"Created {len(response.output_files)} PNG image(s)")
    for output in response.output_files:
        print(f"{output.name}: {output.type}, {output.size} bytes")
        print(f"  Download URL: {output.url}")


if __name__ == "__main__":  # pragma: no cover - manual example
    convert_password_protected_pdf()
