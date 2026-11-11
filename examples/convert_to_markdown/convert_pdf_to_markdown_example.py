# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Convert a PDF to inline Markdown and a downloadable Markdown file.

This example loads ``PDFREST_API_KEY`` (optionally from ``.env``), uploads the
checked-in ``examples/resources/report.pdf`` fixture, requests inline Markdown,
then requests the file-output workflow and prints both results.

Run from the repository root with:
``uv run examples/convert_to_markdown/convert_pdf_to_markdown_example.py``.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient

load_dotenv()

resource = Path(__file__).resolve().parents[1] / "resources" / "report.pdf"

with PdfRestClient(api_key=os.environ["PDFREST_API_KEY"]) as client:
    source_pdf = client.files.create_from_paths([resource])[0]
    inline_response = client.convert_to_markdown_inline(source_pdf)
    file_response = client.convert_to_markdown(
        source_pdf,
        output="report-markdown",
    )

print("Inline Markdown preview:")
print(inline_response.markdown[:500])
print(f"Created file: {file_response.output_file.name}")
print(f"MIME type: {file_response.output_file.type}")
print(f"URL: {file_response.output_file.url}")
