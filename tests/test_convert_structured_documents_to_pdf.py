from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast, get_args

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import (
    ConvertCsvToPdfPayload,
    ConvertJsonToPdfPayload,
    ConvertMarkdownToPdfPayload,
    ConvertPlainTextToPdfPayload,
    ConvertXmlToPdfPayload,
)
from pdfrest.types import (
    PdfStructuredTextFontName,
    PdfStructuredTextKnownFont,
    PdfStructuredTextPageSetup,
    PdfStructuredTextPageSize,
    PdfStructuredTextStyle,
)

from .convert_to_pdf_test_helpers import make_source_file
from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_image_file,
)

NAMED_PAGE_SIZES = [
    pytest.param("Letter", id="letter"),
    pytest.param("Legal", id="legal"),
    pytest.param("Ledger", id="ledger"),
    pytest.param("A3", id="a3"),
    pytest.param("A4", id="a4"),
    pytest.param("A5", id="a5"),
    pytest.param("Tabloid", id="tabloid"),
]
KNOWN_FONTS = [
    pytest.param(value, id=value.replace(" ", "-"))
    for value in get_args(PdfStructuredTextKnownFont)
]

CSV_DELIMITERS = [
    pytest.param(" ", id="space"),
    pytest.param("\t", id="tab"),
    pytest.param(",", id="comma"),
    pytest.param(";", id="semicolon"),
]
ALT_TEXT_VALUES = [
    pytest.param(" ", id="space"),
    pytest.param("\t", id="tab"),
    pytest.param("  Company logo  ", id="padded-text"),
]


def _dump_payload(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )


def _make_format_file(extension: str, mime_type: str) -> PdfRestFile:
    return make_source_file(
        str(PdfRestFileID.generate(1)), mime_type, f"source{extension}"
    )


def _sync_conversion(
    monkeypatch: pytest.MonkeyPatch,
    source: PdfRestFile,
    expected_payload: dict[str, Any],
    invoke: Callable[[PdfRestClient], PdfRestFileBasedResponse],
    *,
    input_ids: list[str] | None = None,
) -> PdfRestFileBasedResponse:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf":
            assert json.loads(request.content) == expected_payload
            return httpx.Response(
                200,
                json={
                    "inputId": input_ids or [str(source.id)],
                    "outputId": output_id,
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "structured.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        return invoke(client)


async def _async_conversion(
    monkeypatch: pytest.MonkeyPatch,
    source: PdfRestFile,
    expected_payload: dict[str, Any],
    invoke: Callable[[AsyncPdfRestClient], Any],
) -> PdfRestFileBasedResponse:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf":
            assert json.loads(request.content) == expected_payload
            return httpx.Response(
                200,
                json={"inputId": str(source.id), "outputId": output_id},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "structured.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        return await invoke(client)


def test_markdown_payload_serializes_options_and_deduplicates_images() -> None:
    source = _make_format_file(".md", "text/markdown")
    image = make_image_file(str(PdfRestFileID.generate(2)), "image/png", "logo.png")

    payload = _dump_payload(
        ConvertMarkdownToPdfPayload.model_validate(
            {
                "files": source,
                "title": "Quarterly service summary",
                "language": "en-US",
                "enable_tagging": True,
                "page_setup": {
                    "width": 612,
                    "height": 792,
                    "orientation": "auto",
                    "margin": {"top": 36, "right": 36, "bottom": 36, "left": 36},
                },
                "style": {
                    "font": "Arial",
                    "fallback_fonts": ["Noto Sans"],
                    "text_size": 12,
                    "text_color_rgb": (10, 20, 30),
                    "heading_scale": 1.5,
                },
                "include_unrendered_html": True,
                "image_alt_text": {"company-logo": "Company logo"},
                "missing_image_alt_text": "fail",
                "image_sources": {"company-logo": image, "footer-logo": image},
                "table_style": {
                    "column_width_weights": [1, 2],
                    "show_borders": True,
                    "border_width": 1,
                    "border_color_rgb": (1, 2, 3),
                    "cell_padding": {"top": 5, "right": 6},
                },
                "output": "quarterly-summary",
            }
        )
    )

    assert payload == {
        "id": str(source.id),
        "structured_text_options": {
            "title": "Quarterly service summary",
            "language": "en-US",
            "enable_tagging": True,
            "page_setup": {
                "width": 612.0,
                "height": 792.0,
                "orientation": "auto",
                "margin": {
                    "top": 36.0,
                    "right": 36.0,
                    "bottom": 36.0,
                    "left": 36.0,
                },
            },
            "style": {
                "font": "Arial",
                "fallback_fonts": ["Noto Sans"],
                "text_size": 12.0,
                "text_color_rgb": [10, 20, 30],
                "heading_scale": 1.5,
                "table": {
                    "column_width_weights": [1.0, 2.0],
                    "show_borders": True,
                    "border_width": 1.0,
                    "border_color_rgb": [1, 2, 3],
                    "cell_padding": {"top": 5.0, "right": 6.0},
                },
            },
            "include_unrendered_html": True,
            "markdown": {
                "image_alt_text": {"company-logo": "Company logo"},
                "missing_image_alt_text": "fail",
                "image_sources": {
                    "company-logo": {"image_id_index": 0},
                    "footer-logo": {"image_id_index": 0},
                },
            },
        },
        "image_ids": [str(image.id)],
        "output": "quarterly-summary",
    }


@pytest.mark.parametrize(
    ("payload_model", "extension", "mime_type", "options", "expected_options"),
    [
        pytest.param(
            ConvertPlainTextToPdfPayload,
            ".txt",
            "text/plain",
            {"line_handling": "preserve"},
            {"plain_text": {"line_handling": "preserve"}},
            id="plain-text",
        ),
        pytest.param(
            ConvertJsonToPdfPayload,
            ".json",
            "application/json",
            {"data_presentation": "hierarchy"},
            {"data_presentation": "hierarchy"},
            id="json",
        ),
        pytest.param(
            ConvertXmlToPdfPayload,
            ".xml",
            "application/xml",
            {"data_presentation": "source"},
            {"data_presentation": "source"},
            id="xml",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            ".csv",
            "text/csv",
            {
                "first_row_is_header": True,
                "delimiter": ";",
                "columns": [{"index": 0, "text_align": "right", "width_weight": 2}],
                "table_style": {"repeat_headers_on_overflow": True},
            },
            {
                "style": {"table": {"repeat_headers_on_overflow": True}},
                "csv": {
                    "first_row_is_header": True,
                    "delimiter": ";",
                    "columns": [
                        {"index": 0, "text_align": "right", "width_weight": 2.0}
                    ],
                },
            },
            id="csv",
        ),
    ],
)
def test_format_payloads_serialize_only_applicable_options(
    payload_model: type[BaseModel],
    extension: str,
    mime_type: str,
    options: dict[str, Any],
    expected_options: dict[str, Any],
) -> None:
    source = _make_format_file(extension, mime_type)
    payload = _dump_payload(payload_model.model_validate({"files": source, **options}))
    assert payload == {
        "id": str(source.id),
        "structured_text_options": expected_options,
    }


@pytest.mark.parametrize(
    ("payload_model", "valid_file", "invalid_file", "message"),
    [
        pytest.param(
            ConvertMarkdownToPdfPayload,
            (".md", "text/markdown"),
            (".txt", "text/plain"),
            "Must be a Markdown file",
            id="markdown",
        ),
        pytest.param(
            ConvertPlainTextToPdfPayload,
            (".txt", "text/plain"),
            (".json", "application/json"),
            "Must be a plain text file",
            id="plain-text",
        ),
        pytest.param(
            ConvertJsonToPdfPayload,
            (".json", "application/json"),
            (".xml", "application/xml"),
            "Must be a JSON file",
            id="json",
        ),
        pytest.param(
            ConvertXmlToPdfPayload,
            (".xml", "application/xml"),
            (".csv", "text/csv"),
            "Must be an XML file",
            id="xml",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            (".csv", "text/csv"),
            (".md", "text/markdown"),
            "Must be a CSV file",
            id="csv",
        ),
    ],
)
def test_format_payloads_reject_other_file_families_and_multiple_files(
    payload_model: type[BaseModel],
    valid_file: tuple[str, str],
    invalid_file: tuple[str, str],
    message: str,
) -> None:
    valid = _make_format_file(*valid_file)
    invalid = _make_format_file(*invalid_file)
    with pytest.raises(ValidationError, match=message):
        payload_model.model_validate({"files": invalid})
    with pytest.raises(
        ValidationError, match="List should have at most 1 item after validation"
    ):
        payload_model.model_validate({"files": [valid, valid]})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param(
            {"page_setup": {"width": 612}}, "must be provided together", id="page"
        ),
        pytest.param(
            {"page_setup": {"width": 0, "height": 792}},
            "greater than 0",
            id="page-width-lower-bound",
        ),
        pytest.param(
            {"page_setup": {"margin": {"top": -0.1}}},
            "greater than or equal to 0",
            id="margin-lower-bound",
        ),
        pytest.param(
            {"style": {"text_size": 5}}, "greater than or equal to 6", id="text-size"
        ),
        pytest.param(
            {"style": {"heading_scale": 4.1}},
            "less than or equal to 4",
            id="heading-scale",
        ),
        pytest.param(
            {"style": {"heading_scale": 0}},
            "greater than 0",
            id="heading-scale-lower-bound",
        ),
        pytest.param(
            {"table_style": {"border_width": 12.1}},
            "less than or equal to 12",
            id="border",
        ),
        pytest.param(
            {"table_style": {"border_width": -0.1}},
            "greater than or equal to 0",
            id="border-lower-bound",
        ),
        pytest.param(
            {"table_style": {"cell_padding": {"top": 73}}},
            "less than or equal to 72",
            id="padding",
        ),
        pytest.param(
            {"table_style": {"cell_padding": {"top": -0.1}}},
            "greater than or equal to 0",
            id="padding-lower-bound",
        ),
        pytest.param(
            {"style": {"text_color_rgb": (0, 0, 256)}},
            "less than or equal to 255",
            id="rgb",
        ),
        pytest.param(
            {"style": {"text_color_rgb": (-1, 0, 0)}},
            "greater than or equal to 0",
            id="rgb-lower-bound",
        ),
        pytest.param(
            {"table_style": {"column_width_weights": [0]}},
            "greater than 0",
            id="column-width-weight-lower-bound",
        ),
        pytest.param(
            {"image_alt_text": {"logo": ""}}, "at least 1 character", id="alt-text"
        ),
    ],
)
def test_markdown_payload_rejects_invalid_option_boundaries(
    payload: dict[str, Any], message: str
) -> None:
    source = _make_format_file(".md", "text/markdown")
    with pytest.raises(ValidationError, match=message):
        ConvertMarkdownToPdfPayload.model_validate({"files": source, **payload})


def test_markdown_payload_rejects_non_image_resources() -> None:
    source = _make_format_file(".md", "text/markdown")
    not_image = _make_format_file(".txt", "text/plain")
    with pytest.raises(
        ValidationError,
        match="Markdown images must be GIF, JPEG, PNG, or TIFF files",
    ):
        ConvertMarkdownToPdfPayload.model_validate(
            {"files": source, "image_sources": {"logo": not_image}}
        )


def test_structured_payload_uses_filename_extension_as_authoritative_format() -> None:
    wrong_extension = _make_format_file(".txt", "text/markdown")
    with pytest.raises(ValidationError, match=r"Must be a \.md or \.markdown file"):
        ConvertMarkdownToPdfPayload.model_validate({"files": wrong_extension})


@pytest.mark.parametrize("orientation", ["auto", "portrait", "landscape"])
def test_page_setup_accepts_every_orientation(orientation: str) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "page_setup": {"orientation": orientation}}
        )
    )
    assert (
        payload["structured_text_options"]["page_setup"]["orientation"] == orientation
    )


@pytest.mark.parametrize("size", NAMED_PAGE_SIZES)
def test_page_setup_accepts_every_named_size(size: PdfStructuredTextPageSize) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "page_setup": {"size": size}}
        )
    )
    assert payload["structured_text_options"]["page_setup"] == {"size": size}


def test_page_setup_rejects_unknown_named_size() -> None:
    source = _make_format_file(".txt", "text/plain")
    with pytest.raises(ValidationError, match=r"page_setup\.size"):
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "page_setup": {"size": "Executive"}}
        )


def test_page_setup_accepts_custom_dimensions_instead_of_size_string() -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "page_setup": {"width": 500, "height": 700}}
        )
    )
    assert payload["structured_text_options"]["page_setup"] == {
        "width": 500.0,
        "height": 700.0,
    }


@pytest.mark.parametrize("font", KNOWN_FONTS)
def test_style_accepts_every_published_font_name(
    font: PdfStructuredTextKnownFont,
) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "style": {"font": font}}
        )
    )
    assert payload["structured_text_options"]["style"] == {"font": font}


def test_style_accepts_open_font_names_in_all_font_fields() -> None:
    source = _make_format_file(".txt", "text/plain")
    other_font = "Noto Sans CJK JP"
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {
                "files": source,
                "style": {
                    "font": other_font,
                    "heading_font": other_font,
                    "code_font": other_font,
                    "cjk_font": other_font,
                    "fallback_fonts": ["arial", other_font],
                },
            }
        )
    )
    assert payload["structured_text_options"]["style"] == {
        "font": other_font,
        "heading_font": other_font,
        "code_font": other_font,
        "cjk_font": other_font,
        "fallback_fonts": ["arial", other_font],
    }


@pytest.mark.parametrize(
    "style",
    [
        pytest.param({"font": ""}, id="body"),
        pytest.param({"font": "  "}, id="body-whitespace"),
        pytest.param({"heading_font": ""}, id="heading"),
        pytest.param({"code_font": ""}, id="code"),
        pytest.param({"cjk_font": ""}, id="cjk"),
        pytest.param({"fallback_fonts": [""]}, id="fallback"),
    ],
)
def test_style_rejects_empty_font_names(style: dict[str, Any]) -> None:
    source = _make_format_file(".txt", "text/plain")
    with pytest.raises(ValidationError, match="at least 1 item"):
        ConvertPlainTextToPdfPayload.model_validate({"files": source, "style": style})


@pytest.mark.parametrize("presentation", ["source", "hierarchy"])
@pytest.mark.parametrize(
    ("payload_model", "extension", "mime_type"),
    [
        pytest.param(ConvertJsonToPdfPayload, ".json", "application/json", id="json"),
        pytest.param(ConvertXmlToPdfPayload, ".xml", "application/xml", id="xml"),
    ],
)
def test_data_payloads_accept_every_presentation_literal(
    payload_model: type[BaseModel],
    extension: str,
    mime_type: str,
    presentation: str,
) -> None:
    source = _make_format_file(extension, mime_type)
    payload = _dump_payload(
        payload_model.model_validate(
            {"files": source, "data_presentation": presentation}
        )
    )
    assert payload["structured_text_options"]["data_presentation"] == presentation


@pytest.mark.parametrize("policy", ["warn", "fail", "artifact"])
def test_markdown_payload_accepts_every_missing_alt_text_policy(policy: str) -> None:
    source = _make_format_file(".md", "text/markdown")
    payload = _dump_payload(
        ConvertMarkdownToPdfPayload.model_validate(
            {"files": source, "missing_image_alt_text": policy}
        )
    )
    assert (
        payload["structured_text_options"]["markdown"]["missing_image_alt_text"]
        == policy
    )


@pytest.mark.parametrize("line_handling", ["reflow", "preserve"])
def test_plain_text_payload_accepts_every_line_handling_literal(
    line_handling: str,
) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "line_handling": line_handling}
        )
    )
    assert (
        payload["structured_text_options"]["plain_text"]["line_handling"]
        == line_handling
    )


@pytest.mark.parametrize("alignment", ["left", "center", "right"])
def test_csv_payload_accepts_every_text_alignment_literal(alignment: str) -> None:
    source = _make_format_file(".csv", "text/csv")
    payload = _dump_payload(
        ConvertCsvToPdfPayload.model_validate(
            {"files": source, "columns": [{"index": 0, "text_align": alignment}]}
        )
    )
    assert (
        payload["structured_text_options"]["csv"]["columns"][0]["text_align"]
        == alignment
    )


@pytest.mark.parametrize(
    "options",
    [
        pytest.param({"page_setup": {"width": 0.1, "height": 0.1}}, id="page-min"),
        pytest.param({"page_setup": {"margin": {"top": 0}}}, id="margin-min"),
        pytest.param({"style": {"text_size": 6}}, id="text-size-min"),
        pytest.param({"style": {"text_size": 72}}, id="text-size-max"),
        pytest.param({"style": {"heading_scale": 0.1}}, id="heading-scale-min"),
        pytest.param({"style": {"heading_scale": 4}}, id="heading-scale-max"),
        pytest.param({"table_style": {"border_width": 0}}, id="border-min"),
        pytest.param({"table_style": {"border_width": 12}}, id="border-max"),
        pytest.param({"table_style": {"cell_padding": {"top": 0}}}, id="padding-min"),
        pytest.param({"table_style": {"cell_padding": {"top": 72}}}, id="padding-max"),
        pytest.param({"table_style": {"column_width_weights": [0.1]}}, id="weight-min"),
        pytest.param({"style": {"text_color_rgb": (0, 255, 0)}}, id="rgb-bounds"),
    ],
)
def test_markdown_payload_accepts_numeric_boundaries(options: dict[str, Any]) -> None:
    source = _make_format_file(".md", "text/markdown")
    ConvertMarkdownToPdfPayload.model_validate({"files": source, **options})


@pytest.mark.parametrize(
    ("payload_model", "file_args", "options", "message"),
    [
        pytest.param(
            ConvertMarkdownToPdfPayload,
            (".md", "text/markdown"),
            {"missing_image_alt_text": "ignore"},
            "Input should be",
            id="markdown-policy",
        ),
        pytest.param(
            ConvertPlainTextToPdfPayload,
            (".txt", "text/plain"),
            {"line_handling": "wrap"},
            "Input should be",
            id="line-handling",
        ),
        pytest.param(
            ConvertJsonToPdfPayload,
            (".json", "application/json"),
            {"data_presentation": "tree"},
            "Input should be",
            id="data-presentation",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            (".csv", "text/csv"),
            {"columns": [{"index": 0, "text_align": "justify"}]},
            "Input should be",
            id="text-alignment",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            (".csv", "text/csv"),
            {"delimiter": "||"},
            "at most 1 character",
            id="delimiter",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            (".csv", "text/csv"),
            {"delimiter": ""},
            "at least 1 character",
            id="delimiter-lower-bound",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            (".csv", "text/csv"),
            {"columns": [{"index": -1}]},
            "greater than or equal to 0",
            id="column-index",
        ),
        pytest.param(
            ConvertCsvToPdfPayload,
            (".csv", "text/csv"),
            {"columns": [{"index": 0, "width_weight": 0}]},
            "greater than 0",
            id="column-width-weight-lower-bound",
        ),
    ],
)
def test_payloads_reject_invalid_literals_and_boundaries(
    payload_model: type[BaseModel],
    file_args: tuple[str, str],
    options: dict[str, Any],
    message: str,
) -> None:
    source = _make_format_file(*file_args)
    with pytest.raises(ValidationError, match=message):
        payload_model.model_validate({"files": source, **options})


@pytest.mark.parametrize(
    ("method_name", "expected_extension", "expected_mime_type", "expected_message"),
    [
        ("convert_markdown_to_pdf", ".md", "text/markdown", "Must be a Markdown file"),
        (
            "convert_plain_text_to_pdf",
            ".txt",
            "text/plain",
            "Must be a plain text file",
        ),
        ("convert_json_to_pdf", ".json", "application/json", "Must be a JSON file"),
        ("convert_xml_to_pdf", ".xml", "application/xml", "Must be an XML file"),
        ("convert_csv_to_pdf", ".csv", "text/csv", "Must be a CSV file"),
    ],
)
@pytest.mark.parametrize(
    ("foreign_extension", "foreign_mime_type"),
    [
        (".md", "text/markdown"),
        (".txt", "text/plain"),
        (".json", "application/json"),
        (".xml", "application/xml"),
        (".csv", "text/csv"),
    ],
)
def test_sync_structured_conversions_reject_foreign_files_before_transport(
    method_name: str,
    expected_extension: str,
    expected_mime_type: str,
    expected_message: str,
    foreign_extension: str,
    foreign_mime_type: str,
) -> None:
    if (foreign_extension, foreign_mime_type) == (
        expected_extension,
        expected_mime_type,
    ):
        pytest.skip("matching structured document format")
    source = _make_format_file(foreign_extension, foreign_mime_type)

    def fail_transport(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport should not be called")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(fail_transport)
        ) as client,
        pytest.raises(ValidationError, match=expected_message),
    ):
        getattr(client, method_name)(source)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "expected_extension", "expected_mime_type", "expected_message"),
    [
        ("convert_markdown_to_pdf", ".md", "text/markdown", "Must be a Markdown file"),
        (
            "convert_plain_text_to_pdf",
            ".txt",
            "text/plain",
            "Must be a plain text file",
        ),
        ("convert_json_to_pdf", ".json", "application/json", "Must be a JSON file"),
        ("convert_xml_to_pdf", ".xml", "application/xml", "Must be an XML file"),
        ("convert_csv_to_pdf", ".csv", "text/csv", "Must be a CSV file"),
    ],
)
@pytest.mark.parametrize(
    ("foreign_extension", "foreign_mime_type"),
    [
        (".md", "text/markdown"),
        (".txt", "text/plain"),
        (".json", "application/json"),
        (".xml", "application/xml"),
        (".csv", "text/csv"),
    ],
)
async def test_async_structured_conversions_reject_foreign_files_before_transport(
    method_name: str,
    expected_extension: str,
    expected_mime_type: str,
    expected_message: str,
    foreign_extension: str,
    foreign_mime_type: str,
) -> None:
    if (foreign_extension, foreign_mime_type) == (
        expected_extension,
        expected_mime_type,
    ):
        pytest.skip("matching structured document format")
    source = _make_format_file(foreign_extension, foreign_mime_type)

    def fail_transport(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport should not be called")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(fail_transport)
    ) as client:
        with pytest.raises(ValidationError, match=expected_message):
            await getattr(client, method_name)(source)


def test_convert_markdown_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _make_format_file(".md", "text/markdown")
    image = make_image_file(str(PdfRestFileID.generate(2)))
    payload = _dump_payload(
        ConvertMarkdownToPdfPayload.model_validate(
            {"files": source, "image_sources": {"logo": image}, "output": "structured"}
        )
    )
    response = _sync_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_markdown_to_pdf(
            source, image_sources={"logo": image}, output="structured"
        ),
        input_ids=[str(source.id), str(image.id)],
    )
    assert response.output_file.name == "structured.pdf"
    assert response.output_file.type == "application/pdf"
    assert response.input_ids == [source.id, image.id]


def test_convert_plain_text_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "line_handling": "reflow"}
        )
    )
    response = _sync_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_plain_text_to_pdf(source, line_handling="reflow"),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.parametrize("size", NAMED_PAGE_SIZES)
def test_convert_plain_text_to_pdf_accepts_every_named_size(
    monkeypatch: pytest.MonkeyPatch, size: PdfStructuredTextPageSize
) -> None:
    source = _make_format_file(".txt", "text/plain")
    expected_payload = {
        "id": str(source.id),
        "structured_text_options": {"page_setup": {"size": size}},
    }
    response = _sync_conversion(
        monkeypatch,
        source,
        expected_payload,
        lambda client: client.convert_plain_text_to_pdf(
            source, page_setup={"size": size}
        ),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.parametrize(
    "font", [*KNOWN_FONTS, pytest.param("Noto Sans CJK JP", id="installed-name")]
)
def test_convert_plain_text_to_pdf_accepts_known_or_open_font_name(
    monkeypatch: pytest.MonkeyPatch, font: PdfStructuredTextFontName
) -> None:
    source = _make_format_file(".txt", "text/plain")
    expected_payload = {
        "id": str(source.id),
        "structured_text_options": {"style": {"font": font}},
    }
    response = _sync_conversion(
        monkeypatch,
        source,
        expected_payload,
        lambda client: client.convert_plain_text_to_pdf(source, style={"font": font}),
    )
    assert response.output_file.type == "application/pdf"


def test_convert_plain_text_to_pdf_serializes_all_font_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".txt", "text/plain")
    style = PdfStructuredTextStyle(
        font="arial",
        heading_font="Arial Bold",
        code_font="courier",
        cjk_font="Noto Sans CJK JP",
        fallback_fonts=["arial", "Noto Sans"],
    )
    expected_payload = {
        "id": str(source.id),
        "structured_text_options": {"style": style},
    }
    response = _sync_conversion(
        monkeypatch,
        source,
        expected_payload,
        lambda client: client.convert_plain_text_to_pdf(source, style=style),
    )
    assert response.output_file.type == "application/pdf"


def test_convert_plain_text_to_pdf_rejects_unknown_size_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = _make_format_file(".txt", "text/plain")

    def fail_transport(request: httpx.Request) -> httpx.Response:
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(fail_transport)
        ) as client,
        pytest.raises(ValidationError, match=r"page_setup\.size"),
    ):
        client.convert_plain_text_to_pdf(
            source,
            page_setup=cast(
                PdfStructuredTextPageSetup, cast(object, {"size": "Executive"})
            ),
        )


def test_convert_json_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _make_format_file(".json", "application/json")
    payload = _dump_payload(
        ConvertJsonToPdfPayload.model_validate(
            {"files": source, "data_presentation": "hierarchy"}
        )
    )
    response = _sync_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_json_to_pdf(
            source, data_presentation="hierarchy"
        ),
    )
    assert response.output_file.type == "application/pdf"


def test_convert_xml_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _make_format_file(".xml", "application/xml")
    payload = _dump_payload(
        ConvertXmlToPdfPayload.model_validate(
            {"files": source, "data_presentation": "source"}
        )
    )
    response = _sync_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_xml_to_pdf(source, data_presentation="source"),
    )
    assert response.output_file.type == "application/pdf"


def test_convert_csv_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _make_format_file(".csv", "text/csv")
    payload = _dump_payload(
        ConvertCsvToPdfPayload.model_validate(
            {"files": source, "first_row_is_header": True, "delimiter": ","}
        )
    )
    response = _sync_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_csv_to_pdf(
            source, first_row_is_header=True, delimiter=","
        ),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_convert_markdown_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".md", "text/markdown")
    payload = _dump_payload(
        ConvertMarkdownToPdfPayload.model_validate(
            {"files": source, "include_unrendered_html": True}
        )
    )
    response = await _async_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_markdown_to_pdf(
            source, include_unrendered_html=True
        ),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_convert_plain_text_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = _dump_payload(
        ConvertPlainTextToPdfPayload.model_validate(
            {"files": source, "line_handling": "preserve"}
        )
    )
    response = await _async_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_plain_text_to_pdf(
            source, line_handling="preserve"
        ),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize("size", NAMED_PAGE_SIZES)
async def test_async_convert_plain_text_to_pdf_accepts_every_named_size(
    monkeypatch: pytest.MonkeyPatch, size: PdfStructuredTextPageSize
) -> None:
    source = _make_format_file(".txt", "text/plain")
    expected_payload = {
        "id": str(source.id),
        "structured_text_options": {"page_setup": {"size": size}},
    }
    response = await _async_conversion(
        monkeypatch,
        source,
        expected_payload,
        lambda client: client.convert_plain_text_to_pdf(
            source, page_setup={"size": size}
        ),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "font", [*KNOWN_FONTS, pytest.param("Noto Sans CJK JP", id="installed-name")]
)
async def test_async_convert_plain_text_to_pdf_accepts_known_or_open_font_name(
    monkeypatch: pytest.MonkeyPatch, font: PdfStructuredTextFontName
) -> None:
    source = _make_format_file(".txt", "text/plain")
    expected_payload = {
        "id": str(source.id),
        "structured_text_options": {"style": {"font": font}},
    }
    response = await _async_conversion(
        monkeypatch,
        source,
        expected_payload,
        lambda client: client.convert_plain_text_to_pdf(source, style={"font": font}),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_convert_plain_text_to_pdf_serializes_all_font_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".txt", "text/plain")
    style = PdfStructuredTextStyle(
        font="arial",
        heading_font="Arial Bold",
        code_font="courier",
        cjk_font="Noto Sans CJK JP",
        fallback_fonts=["arial", "Noto Sans"],
    )
    expected_payload = {
        "id": str(source.id),
        "structured_text_options": {"style": style},
    }
    response = await _async_conversion(
        monkeypatch,
        source,
        expected_payload,
        lambda client: client.convert_plain_text_to_pdf(source, style=style),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_convert_plain_text_to_pdf_rejects_unknown_size_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = _make_format_file(".txt", "text/plain")

    def fail_transport(request: httpx.Request) -> httpx.Response:
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(fail_transport)
    ) as client:
        with pytest.raises(ValidationError, match=r"page_setup\.size"):
            await client.convert_plain_text_to_pdf(
                source,
                page_setup=cast(
                    PdfStructuredTextPageSetup, cast(object, {"size": "Executive"})
                ),
            )


@pytest.mark.asyncio
async def test_async_convert_json_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".json", "application/json")
    payload = _dump_payload(ConvertJsonToPdfPayload.model_validate({"files": source}))
    response = await _async_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_json_to_pdf(source),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_convert_xml_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".xml", "application/xml")
    payload = _dump_payload(ConvertXmlToPdfPayload.model_validate({"files": source}))
    response = await _async_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_xml_to_pdf(source),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_convert_csv_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _make_format_file(".csv", "text/csv")
    payload = _dump_payload(
        ConvertCsvToPdfPayload.model_validate(
            {"files": source, "columns": [{"index": 0, "text_align": "left"}]}
        )
    )
    response = await _async_conversion(
        monkeypatch,
        source,
        payload,
        lambda client: client.convert_csv_to_pdf(
            source, columns=[{"index": 0, "text_align": "left"}]
        ),
    )
    assert response.output_file.type == "application/pdf"


@pytest.mark.parametrize(
    ("method_name", "extension", "mime_type"),
    [
        ("convert_markdown_to_pdf", ".md", "text/markdown"),
        ("convert_plain_text_to_pdf", ".txt", "text/plain"),
        ("convert_json_to_pdf", ".json", "application/json"),
        ("convert_xml_to_pdf", ".xml", "application/xml"),
        ("convert_csv_to_pdf", ".csv", "text/csv"),
    ],
)
def test_structured_conversions_request_customization(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    extension: str,
    mime_type: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = _make_format_file(extension, mime_type)
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.params["trace"] == "sync"
            assert request.headers["X-Debug"] == "sync"
            captured_timeout.update(request.extensions["timeout"])
            assert json.loads(request.content)["debug"] is True
            return httpx.Response(
                200, json={"inputId": source.id, "outputId": output_id}
            )
        return httpx.Response(
            200,
            json=build_file_info_payload(output_id, "custom.pdf", "application/pdf"),
        )

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        getattr(client, method_name)(
            source,
            extra_query={"trace": "sync"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"debug": True},
            timeout=0.5,
        )
    assert captured_timeout == {
        "connect": pytest.approx(0.5),
        "read": pytest.approx(0.5),
        "write": pytest.approx(0.5),
        "pool": pytest.approx(0.5),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "extension", "mime_type"),
    [
        ("convert_markdown_to_pdf", ".md", "text/markdown"),
        ("convert_plain_text_to_pdf", ".txt", "text/plain"),
        ("convert_json_to_pdf", ".json", "application/json"),
        ("convert_xml_to_pdf", ".xml", "application/xml"),
        ("convert_csv_to_pdf", ".csv", "text/csv"),
    ],
)
async def test_async_structured_conversions_request_customization(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    extension: str,
    mime_type: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = _make_format_file(extension, mime_type)
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            captured_timeout.update(request.extensions["timeout"])
            assert json.loads(request.content)["debug"] is True
            return httpx.Response(
                200, json={"inputId": source.id, "outputId": output_id}
            )
        return httpx.Response(
            200,
            json=build_file_info_payload(output_id, "custom.pdf", "application/pdf"),
        )

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await getattr(client, method_name)(
            source,
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async"},
            extra_body={"debug": True},
            timeout=0.6,
        )
    assert captured_timeout == {
        "connect": pytest.approx(0.6),
        "read": pytest.approx(0.6),
        "write": pytest.approx(0.6),
        "pool": pytest.approx(0.6),
    }


@pytest.mark.parametrize("delimiter", CSV_DELIMITERS)
def test_csv_payload_preserves_delimiter(delimiter: str) -> None:
    source = _make_format_file(".csv", "text/csv")
    payload = ConvertCsvToPdfPayload.model_validate(
        {"files": source, "delimiter": delimiter}
    )
    assert _dump_payload(payload) == {
        "id": str(source.id),
        "structured_text_options": {"csv": {"delimiter": delimiter}},
    }


@pytest.mark.parametrize("delimiter", CSV_DELIMITERS)
def test_convert_csv_to_pdf_preserves_delimiter(
    monkeypatch: pytest.MonkeyPatch, delimiter: str
) -> None:
    source = _make_format_file(".csv", "text/csv")
    _sync_conversion(
        monkeypatch,
        source,
        {
            "id": str(source.id),
            "structured_text_options": {"csv": {"delimiter": delimiter}},
        },
        lambda client: client.convert_csv_to_pdf(source, delimiter=delimiter),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("delimiter", CSV_DELIMITERS)
async def test_async_convert_csv_to_pdf_preserves_delimiter(
    monkeypatch: pytest.MonkeyPatch, delimiter: str
) -> None:
    source = _make_format_file(".csv", "text/csv")
    await _async_conversion(
        monkeypatch,
        source,
        {
            "id": str(source.id),
            "structured_text_options": {"csv": {"delimiter": delimiter}},
        },
        lambda client: client.convert_csv_to_pdf(source, delimiter=delimiter),
    )


@pytest.mark.parametrize("alt_text", ALT_TEXT_VALUES)
def test_markdown_payload_preserves_alt_text(alt_text: str) -> None:
    source = _make_format_file(".md", "text/markdown")
    payload = ConvertMarkdownToPdfPayload.model_validate(
        {"files": source, "image_alt_text": {"logo": alt_text}}
    )
    assert _dump_payload(payload) == {
        "id": str(source.id),
        "structured_text_options": {"markdown": {"image_alt_text": {"logo": alt_text}}},
    }


@pytest.mark.parametrize("alt_text", ALT_TEXT_VALUES)
def test_convert_markdown_to_pdf_preserves_alt_text(
    monkeypatch: pytest.MonkeyPatch, alt_text: str
) -> None:
    source = _make_format_file(".md", "text/markdown")
    _sync_conversion(
        monkeypatch,
        source,
        {
            "id": str(source.id),
            "structured_text_options": {
                "markdown": {"image_alt_text": {"logo": alt_text}}
            },
        },
        lambda client: client.convert_markdown_to_pdf(
            source, image_alt_text={"logo": alt_text}
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("alt_text", ALT_TEXT_VALUES)
async def test_async_convert_markdown_to_pdf_preserves_alt_text(
    monkeypatch: pytest.MonkeyPatch, alt_text: str
) -> None:
    source = _make_format_file(".md", "text/markdown")
    await _async_conversion(
        monkeypatch,
        source,
        {
            "id": str(source.id),
            "structured_text_options": {
                "markdown": {"image_alt_text": {"logo": alt_text}}
            },
        },
        lambda client: client.convert_markdown_to_pdf(
            source, image_alt_text={"logo": alt_text}
        ),
    )


TRIMMED_TEXT_OPTIONS = [
    pytest.param({"title": "  Report  "}, {"title": "Report"}, id="title"),
    pytest.param({"language": "  en-US  "}, {"language": "en-US"}, id="language"),
    *[
        pytest.param(
            {"style": {field: "  Noto Sans  "}},
            {"style": {field: "Noto Sans"}},
            id=field,
        )
        for field in ("font", "heading_font", "code_font", "cjk_font")
    ],
    pytest.param(
        {"style": {"fallback_fonts": ["  arial  ", "  Noto Sans  "]}},
        {"style": {"fallback_fonts": ["arial", "Noto Sans"]}},
        id="fallback-fonts",
    ),
]


@pytest.mark.parametrize(("options", "expected_options"), TRIMMED_TEXT_OPTIONS)
def test_payload_trims_api_normalized_text(
    options: dict[str, Any], expected_options: dict[str, Any]
) -> None:
    source = _make_format_file(".txt", "text/plain")
    payload = ConvertPlainTextToPdfPayload.model_validate({"files": source, **options})
    assert _dump_payload(payload) == {
        "id": str(source.id),
        "structured_text_options": expected_options,
    }


@pytest.mark.parametrize(("options", "expected_options"), TRIMMED_TEXT_OPTIONS)
def test_convert_plain_text_to_pdf_trims_api_normalized_text(
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
    expected_options: dict[str, Any],
) -> None:
    source = _make_format_file(".txt", "text/plain")
    _sync_conversion(
        monkeypatch,
        source,
        {"id": str(source.id), "structured_text_options": expected_options},
        lambda client: client.convert_plain_text_to_pdf(source, **options),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("options", "expected_options"), TRIMMED_TEXT_OPTIONS)
async def test_async_convert_plain_text_to_pdf_trims_api_normalized_text(
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
    expected_options: dict[str, Any],
) -> None:
    source = _make_format_file(".txt", "text/plain")
    await _async_conversion(
        monkeypatch,
        source,
        {"id": str(source.id), "structured_text_options": expected_options},
        lambda client: client.convert_plain_text_to_pdf(source, **options),
    )


INVALID_CSV_DELIMITERS = [
    pytest.param("", "at least 1 character", id="empty"),
    pytest.param(", ", "at most 1 character", id="trailing-space"),
    pytest.param(" ,", "at most 1 character", id="leading-space"),
    pytest.param(" \t", "at most 1 character", id="two-whitespace-characters"),
]


@pytest.mark.parametrize(("delimiter", "message"), INVALID_CSV_DELIMITERS)
def test_csv_payload_rejects_delimiter_without_trimming(
    delimiter: str, message: str
) -> None:
    source = _make_format_file(".csv", "text/csv")
    with pytest.raises(ValidationError, match=rf"(?s)delimiter.*{message}"):
        ConvertCsvToPdfPayload.model_validate({"files": source, "delimiter": delimiter})


@pytest.fixture
def validation_transport() -> httpx.MockTransport:
    def fail_transport(_: httpx.Request) -> httpx.Response:
        pytest.fail("invalid options must not reach transport")

    return httpx.MockTransport(fail_transport)


@pytest.mark.parametrize(("delimiter", "message"), INVALID_CSV_DELIMITERS)
def test_convert_csv_to_pdf_rejects_delimiter_before_transport(
    delimiter: str, message: str, validation_transport: httpx.MockTransport
) -> None:
    source = _make_format_file(".csv", "text/csv")
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=validation_transport) as client,
        pytest.raises(ValidationError, match=rf"(?s)delimiter.*{message}"),
    ):
        client.convert_csv_to_pdf(source, delimiter=delimiter)


@pytest.mark.asyncio
@pytest.mark.parametrize(("delimiter", "message"), INVALID_CSV_DELIMITERS)
async def test_async_convert_csv_to_pdf_rejects_delimiter_before_transport(
    delimiter: str, message: str, validation_transport: httpx.MockTransport
) -> None:
    source = _make_format_file(".csv", "text/csv")
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=validation_transport
    ) as client:
        with pytest.raises(ValidationError, match=rf"(?s)delimiter.*{message}"):
            await client.convert_csv_to_pdf(source, delimiter=delimiter)
