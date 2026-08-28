# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfrest", "python-dotenv"]
# ///
"""Convert Markdown, plain text, JSON, XML, and CSV documents to PDF.

This sample demonstrates how to:

1. Upload the five deterministic structured documents in ``examples/resources``.
2. Select format-specific conversion options with public typed dictionaries.
3. Generate one PDF from each source through the focused client helpers.
4. Print the returned PDF names, MIME types, sizes, and download URLs.

Set ``PDFREST_API_KEY``, then run from the repository root with
``uv run examples/convert_structured_documents/convert_structured_documents_to_pdf_example.py``.
All required input files are included in the repository.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from pdfrest import PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse
from pdfrest.types import (
    PdfStructuredTextCsvColumn,
    PdfStructuredTextMargin,
    PdfStructuredTextPageSetup,
    PdfStructuredTextStyle,
    PdfStructuredTextTableStyle,
)

RESOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "resources"
RESOURCE_PATHS = [
    RESOURCE_DIRECTORY / "structured-document.md",
    RESOURCE_DIRECTORY / "structured-document.txt",
    RESOURCE_DIRECTORY / "structured-document.json",
    RESOURCE_DIRECTORY / "structured-document.xml",
    RESOURCE_DIRECTORY / "structured-document.csv",
]


def _print_result(label: str, response: PdfRestFileBasedResponse) -> None:
    output = response.output_file
    print(f"{label}: {output.name}")
    print(f"  MIME type: {output.type}")
    print(f"  Size: {output.size} bytes")
    print(f"  Download URL: {output.url}")


def convert_structured_documents() -> None:
    """Upload each sample and convert it with its format-specific helper."""
    load_dotenv()
    page_setup = PdfStructuredTextPageSetup(
        size="Letter",
        orientation="portrait",
        margin=PdfStructuredTextMargin(top=36, right=36, bottom=36, left=36),
    )
    style = PdfStructuredTextStyle(
        font="Arial",
        text_size=11,
        text_color_rgb=(32, 42, 54),
        heading_scale=1.4,
    )
    table_style = PdfStructuredTextTableStyle(
        show_borders=True,
        repeat_headers_on_overflow=True,
        header_fill_color_rgb=(34, 93, 131),
        header_text_color_rgb=(255, 255, 255),
    )
    columns = [
        PdfStructuredTextCsvColumn(index=0, text_align="left", width_weight=2),
        PdfStructuredTextCsvColumn(index=1, text_align="right", width_weight=1),
    ]

    with PdfRestClient() as client:
        markdown, plain_text, json_file, xml_file, csv_file = (
            client.files.create_from_paths(RESOURCE_PATHS)
        )
        responses = [
            (
                "Markdown",
                client.convert_markdown_to_pdf(
                    markdown,
                    title="Markdown service summary",
                    enable_tagging=True,
                    page_setup=page_setup,
                    style=style,
                    table_style=table_style,
                    output="markdown-summary",
                ),
            ),
            (
                "Plain text",
                client.convert_plain_text_to_pdf(
                    plain_text,
                    line_handling="reflow",
                    page_setup=page_setup,
                    style=style,
                    output="plain-text-summary",
                ),
            ),
            (
                "JSON",
                client.convert_json_to_pdf(
                    json_file,
                    data_presentation="hierarchy",
                    page_setup=page_setup,
                    style=style,
                    output="json-summary",
                ),
            ),
            (
                "XML",
                client.convert_xml_to_pdf(
                    xml_file,
                    data_presentation="hierarchy",
                    page_setup=page_setup,
                    style=style,
                    output="xml-summary",
                ),
            ),
            (
                "CSV",
                client.convert_csv_to_pdf(
                    csv_file,
                    first_row_is_header=True,
                    columns=columns,
                    table_style=table_style,
                    page_setup=page_setup,
                    style=style,
                    output="csv-summary",
                ),
            ),
        ]

    for label, response in responses:
        _print_result(label, response)


if __name__ == "__main__":  # pragma: no cover - manual example
    convert_structured_documents()
