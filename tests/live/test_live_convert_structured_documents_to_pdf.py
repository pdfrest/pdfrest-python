from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse
from pdfrest.models._internal import ConvertCsvToPdfPayload, ConvertMarkdownToPdfPayload
from pdfrest.types import (
    PdfStructuredTextCsvColumn,
    PdfStructuredTextDataPresentation,
    PdfStructuredTextFontName,
    PdfStructuredTextLineHandling,
    PdfStructuredTextMissingImageAltText,
    PdfStructuredTextPageOrientation,
    PdfStructuredTextPageSize,
    PdfStructuredTextTextAlignment,
)

from ..resources import get_test_resource_path

NAMED_PAGE_SIZES = [
    pytest.param("Letter", id="letter"),
    pytest.param(" \tLetter\n ", id="padded-letter"),
    pytest.param("Legal", id="legal"),
    pytest.param("Ledger", id="ledger"),
    pytest.param("A3", id="a3"),
    pytest.param("A4", id="a4"),
    pytest.param("A5", id="a5"),
    pytest.param("Tabloid", id="tabloid"),
]

WHITESPACE_DELIMITER_SKIP_REASON = (
    "Blocked by clu-structured-text-to-pdf CsvAdapter.ResolveDelimiter(): "
    "space/tab delimiters fall back to comma. Enable after the CLU fix is deployed."
)


@pytest.fixture(scope="module")
def uploaded_structured_documents(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> dict[str, PdfRestFile]:
    resources = {
        "markdown": get_test_resource_path("structured-document.md"),
        "markdown_image": get_test_resource_path("structured-document-with-image.md"),
        "markdown_table": get_test_resource_path("structured-document-table.md"),
        "markdown_two_images": get_test_resource_path(
            "structured-document-with-two-images.md"
        ),
        "plain_text": get_test_resource_path("structured-document.txt"),
        "json": get_test_resource_path("structured-document.json"),
        "xml": get_test_resource_path("structured-document.xml"),
        "csv": get_test_resource_path("structured-document.csv"),
        "image": get_test_resource_path("test.png"),
        "second_image": get_test_resource_path("test.jpg"),
    }
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths(list(resources.values()))
    return dict(zip(resources, uploaded, strict=True))


def _assert_structured_pdf(
    response: PdfRestFileBasedResponse,
    source: PdfRestFile,
    output_prefix: str,
) -> None:
    assert response.output_files
    output = response.output_file
    assert output.name.startswith(output_prefix)
    assert output.type == "application/pdf"
    assert output.size > 0
    assert output.url is not None
    assert source.id in response.input_ids


def _run_sync(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    invoke: Callable[[PdfRestClient], PdfRestFileBasedResponse],
) -> PdfRestFileBasedResponse:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return invoke(client)


async def _run_async(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    invoke: Callable[[AsyncPdfRestClient], Awaitable[PdfRestFileBasedResponse]],
) -> PdfRestFileBasedResponse:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return await invoke(client)


@pytest.mark.parametrize("missing_image_alt_text", ["warn", "fail", "artifact"])
def test_live_convert_markdown_to_pdf_missing_image_alt_text(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    missing_image_alt_text: PdfStructuredTextMissingImageAltText,
) -> None:
    source = uploaded_structured_documents["markdown_image"]
    image = uploaded_structured_documents["image"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_markdown_to_pdf(
            source,
            image_sources={"company-logo": image},
            image_alt_text={"company-logo": "Datalogics company logo"},
            missing_image_alt_text=missing_image_alt_text,
            output=f"live-markdown-{missing_image_alt_text}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-markdown-{missing_image_alt_text}")
    assert response.input_ids == [source.id, image.id]


@pytest.mark.parametrize("line_handling", ["reflow", "preserve"])
def test_live_convert_plain_text_to_pdf_line_handling(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    line_handling: PdfStructuredTextLineHandling,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source,
            line_handling=line_handling,
            output=f"live-plain-text-{line_handling}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-plain-text-{line_handling}")


@pytest.mark.parametrize("orientation", ["auto", "portrait", "landscape"])
def test_live_convert_plain_text_to_pdf_page_orientation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    orientation: PdfStructuredTextPageOrientation,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source,
            page_setup={"orientation": orientation},
            output=f"live-plain-text-orientation-{orientation}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-plain-text-orientation-{orientation}"
    )


@pytest.mark.parametrize("size", NAMED_PAGE_SIZES)
def test_live_convert_plain_text_to_pdf_page_size(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    size: PdfStructuredTextPageSize,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source,
            page_setup={"size": size},
            output=f"live-plain-text-page-size-{size.strip().lower()}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-plain-text-page-size-{size.strip().lower()}"
    )


def test_live_convert_plain_text_to_pdf_rejects_invalid_page_size(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["plain_text"]
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)page.?setup|size|invalid"),
    ):
        client.convert_plain_text_to_pdf(
            source,
            extra_body={
                "structured_text_options": {"page_setup": {"size": "Executive"}}
            },
        )


@pytest.mark.parametrize(
    "font",
    [
        pytest.param("arial", id="published-token"),
        pytest.param("Noto Sans", id="installed-unlisted-name"),
    ],
)
def test_live_convert_plain_text_to_pdf_font_name(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    font: PdfStructuredTextFontName,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source, style={"font": font}, output="live-plain-text-font"
        ),
    )
    _assert_structured_pdf(response, source, "live-plain-text-font")


@pytest.mark.parametrize("data_presentation", ["source", "hierarchy"])
def test_live_convert_json_to_pdf_data_presentation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    data_presentation: PdfStructuredTextDataPresentation,
) -> None:
    source = uploaded_structured_documents["json"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_json_to_pdf(
            source,
            data_presentation=data_presentation,
            output=f"live-json-{data_presentation}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-json-{data_presentation}")


@pytest.mark.parametrize("data_presentation", ["source", "hierarchy"])
def test_live_convert_xml_to_pdf_data_presentation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    data_presentation: PdfStructuredTextDataPresentation,
) -> None:
    source = uploaded_structured_documents["xml"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_xml_to_pdf(
            source,
            data_presentation=data_presentation,
            output=f"live-xml-{data_presentation}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-xml-{data_presentation}")


@pytest.mark.parametrize("text_align", ["left", "center", "right"])
def test_live_convert_csv_to_pdf_text_align(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    text_align: PdfStructuredTextTextAlignment,
) -> None:
    source = uploaded_structured_documents["csv"]
    columns = [
        PdfStructuredTextCsvColumn(index=0, text_align=text_align, width_weight=1)
    ]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_csv_to_pdf(
            source,
            first_row_is_header=True,
            columns=columns,
            output=f"live-csv-{text_align}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-csv-{text_align}")


@pytest.fixture
def whitespace_csv_document(
    tmp_path: Path,
    delimiter: str,
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    """Upload input whose two columns use the delimiter under test."""
    path = tmp_path / "whitespace-delimited.csv"
    path.write_text(f"Name{delimiter}Value\nAlpha{delimiter}1\n", encoding="utf-8")
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        return client.files.create_from_paths(path)[0]


@pytest.mark.skip(reason=WHITESPACE_DELIMITER_SKIP_REASON)
@pytest.mark.parametrize(
    "delimiter", [pytest.param(" ", id="space"), pytest.param("\t", id="tab")]
)
def test_live_convert_csv_to_pdf_whitespace_delimiter(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    whitespace_csv_document: PdfRestFile,
    delimiter: str,
) -> None:
    """Selecting the second column requires the delimiter to split the input."""
    source = whitespace_csv_document
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_csv_to_pdf(
            source,
            delimiter=delimiter,
            first_row_is_header=True,
            columns=[PdfStructuredTextCsvColumn(index=1, text_align="right")],
            output="live-csv-whitespace",
        ),
    )
    _assert_structured_pdf(response, source, "live-csv-whitespace")


@pytest.mark.asyncio
@pytest.mark.skip(reason=WHITESPACE_DELIMITER_SKIP_REASON)
@pytest.mark.parametrize(
    "delimiter", [pytest.param(" ", id="space"), pytest.param("\t", id="tab")]
)
async def test_live_async_convert_csv_to_pdf_whitespace_delimiter(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    whitespace_csv_document: PdfRestFile,
    delimiter: str,
) -> None:
    """Selecting the second column requires the delimiter to split the input."""
    source = whitespace_csv_document
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_csv_to_pdf(
            source,
            delimiter=delimiter,
            first_row_is_header=True,
            columns=[PdfStructuredTextCsvColumn(index=1, text_align="right")],
            output="live-csv-async-whitespace",
        ),
    )
    _assert_structured_pdf(response, source, "live-csv-async-whitespace")


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_image_alt_text", ["warn", "fail", "artifact"])
async def test_live_async_convert_markdown_to_pdf_missing_image_alt_text(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    missing_image_alt_text: PdfStructuredTextMissingImageAltText,
) -> None:
    source = uploaded_structured_documents["markdown_image"]
    image = uploaded_structured_documents["image"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_markdown_to_pdf(
            source,
            image_sources={"company-logo": image},
            image_alt_text={"company-logo": "Datalogics company logo"},
            missing_image_alt_text=missing_image_alt_text,
            enable_tagging=True,
            output=f"live-markdown-async-{missing_image_alt_text}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-markdown-async-{missing_image_alt_text}"
    )
    assert response.input_ids == [source.id, image.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("line_handling", ["reflow", "preserve"])
async def test_live_async_convert_plain_text_to_pdf_line_handling(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    line_handling: PdfStructuredTextLineHandling,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source,
            line_handling=line_handling,
            output=f"live-plain-text-async-{line_handling}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-plain-text-async-{line_handling}")


@pytest.mark.asyncio
@pytest.mark.parametrize("orientation", ["auto", "portrait", "landscape"])
async def test_live_async_convert_plain_text_to_pdf_page_orientation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    orientation: PdfStructuredTextPageOrientation,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source,
            page_setup={"orientation": orientation},
            output=f"live-plain-text-async-orientation-{orientation}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-plain-text-async-orientation-{orientation}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("size", NAMED_PAGE_SIZES)
async def test_live_async_convert_plain_text_to_pdf_page_size(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    size: PdfStructuredTextPageSize,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source,
            page_setup={"size": size},
            output=f"live-plain-text-async-page-size-{size.strip().lower()}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-plain-text-async-page-size-{size.strip().lower()}"
    )


@pytest.mark.asyncio
async def test_live_async_convert_plain_text_to_pdf_rejects_invalid_page_size(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["plain_text"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)page.?setup|size|invalid"):
            await client.convert_plain_text_to_pdf(
                source,
                extra_body={
                    "structured_text_options": {"page_setup": {"size": "Executive"}}
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "font",
    [
        pytest.param("arial", id="published-token"),
        pytest.param("Noto Sans", id="installed-unlisted-name"),
    ],
)
async def test_live_async_convert_plain_text_to_pdf_font_name(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    font: PdfStructuredTextFontName,
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source, style={"font": font}, output="live-plain-text-async-font"
        ),
    )
    _assert_structured_pdf(response, source, "live-plain-text-async-font")


@pytest.mark.asyncio
@pytest.mark.parametrize("data_presentation", ["source", "hierarchy"])
async def test_live_async_convert_json_to_pdf_data_presentation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    data_presentation: PdfStructuredTextDataPresentation,
) -> None:
    source = uploaded_structured_documents["json"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_json_to_pdf(
            source,
            data_presentation=data_presentation,
            output=f"live-json-async-{data_presentation}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-json-async-{data_presentation}")


@pytest.mark.asyncio
@pytest.mark.parametrize("data_presentation", ["source", "hierarchy"])
async def test_live_async_convert_xml_to_pdf_data_presentation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    data_presentation: PdfStructuredTextDataPresentation,
) -> None:
    source = uploaded_structured_documents["xml"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_xml_to_pdf(
            source,
            data_presentation=data_presentation,
            output=f"live-xml-async-{data_presentation}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-xml-async-{data_presentation}")


@pytest.mark.asyncio
@pytest.mark.parametrize("text_align", ["left", "center", "right"])
async def test_live_async_convert_csv_to_pdf_text_align(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    text_align: PdfStructuredTextTextAlignment,
) -> None:
    source = uploaded_structured_documents["csv"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_csv_to_pdf(
            source,
            columns=[
                PdfStructuredTextCsvColumn(
                    index=0, text_align=text_align, width_weight=1
                )
            ],
            delimiter=",",
            output=f"live-csv-async-{text_align}",
        ),
    )
    _assert_structured_pdf(response, source, f"live-csv-async-{text_align}")


def test_live_convert_json_to_pdf_rejects_invalid_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["json"]
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)data.presentation|invalid|source"),
    ):
        client.convert_json_to_pdf(
            source,
            extra_body={"structured_text_options": {"data_presentation": "diorama"}},
        )


@pytest.mark.asyncio
async def test_live_async_convert_json_to_pdf_rejects_invalid_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["json"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError, match=r"(?i)data.presentation|invalid|source"
        ):
            await client.convert_json_to_pdf(
                source,
                extra_body={
                    "structured_text_options": {"data_presentation": "diorama"}
                },
            )


def _numeric_schema_fields(
    node: dict[str, Any],
    definitions: dict[str, Any],
    path: tuple[str | int, ...] = (),
) -> dict[tuple[str | int, ...], dict[str, Any]]:
    """Read numeric constraints from payload schemas, including RGB channels."""
    if "$ref" in node:
        node = definitions[node["$ref"].rsplit("/", 1)[-1]]
    if "anyOf" in node:
        node = next(branch for branch in node["anyOf"] if branch.get("type") != "null")
        return _numeric_schema_fields(node, definitions, path)
    if node.get("type") in ("number", "integer"):
        return {path: node}
    fields: dict[tuple[str | int, ...], dict[str, Any]] = {}
    for name, child in node.get("properties", {}).items():
        fields.update(_numeric_schema_fields(child, definitions, (*path, name)))
    if "items" in node:
        fields.update(_numeric_schema_fields(node["items"], definitions, (*path, 0)))
    for index, child in enumerate(node.get("prefixItems", [])):
        fields.update(_numeric_schema_fields(child, definitions, (*path, index)))
    return fields


def _numeric_live_cases() -> tuple[list[Any], list[Any]]:
    fields: dict[tuple[str | int, ...], dict[str, Any]] = {}
    for model in (ConvertMarkdownToPdfPayload, ConvertCsvToPdfPayload):
        schema = model.model_json_schema()
        fields.update(
            _numeric_schema_fields(
                schema["properties"]["structured_text_options"], schema["$defs"]
            )
        )
    accepted: list[Any] = []
    rejected: list[Any] = []
    for path, field in fields.items():
        step = 1 if field["type"] == "integer" else 0.1
        minimum = field["minimum"] if "minimum" in field else field["exclusiveMinimum"]
        valid = [minimum + step]
        invalid = [minimum - step]
        if "minimum" in field:
            valid.insert(0, minimum)
        else:
            valid.append(minimum + 1)
            invalid.append(minimum)
        if "maximum" in field:
            valid.extend([field["maximum"] - step, field["maximum"]])
            invalid.append(field["maximum"] + step)
        label = "-".join(map(str, path))
        for value in valid:
            # The service requires usable page area beyond its positive bounds.
            layout_rejection = (
                path in (("page_setup", "width"), ("page_setup", "height"))
                and value < 180
            )
            accepted.append(
                pytest.param(path, value, layout_rejection, id=f"{label}-{value}")
            )
        rejected.extend(
            pytest.param(path, value, id=f"{label}-{value}") for value in invalid
        )
    return accepted, rejected


VALID_NUMERIC_LIVE_CASES, INVALID_NUMERIC_LIVE_CASES = _numeric_live_cases()


def _numeric_live_options(
    path: tuple[str | int, ...], value: float
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Change one numeric option while keeping related fields valid."""
    options: dict[str, Any] = {}
    if path[0] == "csv":
        options["csv"] = {"columns": [{"index": 0}]}
    if path in (("page_setup", "width"), ("page_setup", "height")):
        options["page_setup"] = {"width": 612, "height": 792}
    if isinstance(path[-1], int):
        if path[-2] == "column_width_weights":
            options["style"] = {"table": {"column_width_weights": [1, 1]}}
        else:
            options["style"] = {}
            style = options["style"]
            if path[1] == "table":
                style["table"] = {}
                style = style["table"]
            style[path[-2]] = [128, 128, 128]
    current: Any = options
    for key in path[:-1]:
        if isinstance(current, dict):
            current = current.setdefault(key, {})
        else:
            current = current[key]
    current[path[-1]] = value
    arguments = dict(options)
    if "csv" in arguments:
        arguments.update(arguments.pop("csv"))
    if "table" in arguments.get("style", {}):
        arguments["style"] = dict(arguments["style"])
        arguments["table_style"] = arguments["style"].pop("table")
    source_name = "csv" if path[0] == "csv" else "markdown_table"
    return source_name, options, arguments


@pytest.mark.parametrize(
    ("path", "value", "layout_rejection"), VALID_NUMERIC_LIVE_CASES
)
def test_live_structured_numeric_boundaries(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    path: tuple[str | int, ...],
    value: float,
    layout_rejection: bool,
) -> None:
    source_name, _, arguments = _numeric_live_options(path, value)
    source = uploaded_structured_documents[source_name]
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        method = (
            client.convert_csv_to_pdf
            if source_name == "csv"
            else client.convert_markdown_to_pdf
        )
        if layout_rejection:
            with pytest.raises(
                PdfRestApiError, match=r"(?i)issue processing|usable width"
            ):
                method(source, **arguments)
        else:
            response = method(source, **arguments, output="live-numeric-boundary")
            _assert_structured_pdf(response, source, "live-numeric-boundary")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "value", "layout_rejection"), VALID_NUMERIC_LIVE_CASES
)
async def test_live_async_structured_numeric_boundaries(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    path: tuple[str | int, ...],
    value: float,
    layout_rejection: bool,
) -> None:
    source_name, _, arguments = _numeric_live_options(path, value)
    source = uploaded_structured_documents[source_name]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        method = (
            client.convert_csv_to_pdf
            if source_name == "csv"
            else client.convert_markdown_to_pdf
        )
        if layout_rejection:
            with pytest.raises(
                PdfRestApiError, match=r"(?i)issue processing|usable width"
            ):
                await method(source, **arguments)
        else:
            response = await method(
                source, **arguments, output="live-async-numeric-boundary"
            )
            _assert_structured_pdf(response, source, "live-async-numeric-boundary")


@pytest.mark.parametrize(("path", "value"), INVALID_NUMERIC_LIVE_CASES)
def test_live_structured_rejects_numeric_boundaries(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    path: tuple[str | int, ...],
    value: float,
) -> None:
    source_name, options, _ = _numeric_live_options(path, value)
    with (
        PdfRestClient(
            api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)structured_text_options|invalid"),
    ):
        (
            client.convert_csv_to_pdf
            if source_name == "csv"
            else client.convert_markdown_to_pdf
        )(
            uploaded_structured_documents[source_name],
            extra_body={"structured_text_options": options},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "value"), INVALID_NUMERIC_LIVE_CASES)
async def test_live_async_structured_rejects_numeric_boundaries(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    path: tuple[str | int, ...],
    value: float,
) -> None:
    source_name, options, _ = _numeric_live_options(path, value)
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        method = (
            client.convert_csv_to_pdf
            if source_name == "csv"
            else client.convert_markdown_to_pdf
        )
        with pytest.raises(
            PdfRestApiError, match=r"(?i)structured_text_options|invalid"
        ):
            await method(
                uploaded_structured_documents[source_name],
                extra_body={"structured_text_options": options},
            )


IMAGE_INDEX_BOUNDARIES = [
    pytest.param(0, True, id="minimum"),
    pytest.param(1, True, id="inside"),
    pytest.param(-1, False, id="below-minimum"),
    pytest.param(2, False, id="outside-uploaded-images"),
]


def _image_index_options(image_index: int) -> dict[str, Any]:
    return {
        "markdown": {
            "image_sources": {
                "company-logo": {"image_id_index": image_index},
                "second-logo": {"image_id_index": 1 if image_index != 1 else 0},
            },
            "image_alt_text": {
                "company-logo": "Company logo",
                "second-logo": "Second logo",
            },
        }
    }


@pytest.mark.parametrize(("image_index", "valid"), IMAGE_INDEX_BOUNDARIES)
def test_live_markdown_image_index_boundaries(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    image_index: int,
    valid: bool,
) -> None:
    source = uploaded_structured_documents["markdown_two_images"]
    image = uploaded_structured_documents["image"]
    second_image = uploaded_structured_documents["second_image"]
    # Wire indices are internal: extra_body is required to exercise their bounds.
    extra_body = {
        "image_ids": [str(image.id), str(second_image.id)],
        "structured_text_options": _image_index_options(image_index),
    }
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        if valid:
            response = client.convert_markdown_to_pdf(
                source, extra_body=extra_body, output="live-image-index"
            )
            _assert_structured_pdf(response, source, "live-image-index")
            assert response.input_ids == [source.id, image.id, second_image.id]
        else:
            with pytest.raises(
                PdfRestApiError,
                match=r"(?i)image_id_index|image.ids|structured_text_options",
            ):
                client.convert_markdown_to_pdf(source, extra_body=extra_body)


@pytest.mark.asyncio
@pytest.mark.parametrize(("image_index", "valid"), IMAGE_INDEX_BOUNDARIES)
async def test_live_async_markdown_image_index_boundaries(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
    image_index: int,
    valid: bool,
) -> None:
    source = uploaded_structured_documents["markdown_two_images"]
    image = uploaded_structured_documents["image"]
    second_image = uploaded_structured_documents["second_image"]
    extra_body = {
        "image_ids": [str(image.id), str(second_image.id)],
        "structured_text_options": _image_index_options(image_index),
    }
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        if valid:
            response = await client.convert_markdown_to_pdf(
                source, extra_body=extra_body, output="live-async-image-index"
            )
            _assert_structured_pdf(response, source, "live-async-image-index")
            assert response.input_ids == [source.id, image.id, second_image.id]
        else:
            with pytest.raises(
                PdfRestApiError,
                match=r"(?i)image_id_index|image.ids|structured_text_options",
            ):
                await client.convert_markdown_to_pdf(source, extra_body=extra_body)
