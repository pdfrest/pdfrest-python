from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse
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
        "plain_text": get_test_resource_path("structured-document.txt"),
        "json": get_test_resource_path("structured-document.json"),
        "xml": get_test_resource_path("structured-document.xml"),
        "csv": get_test_resource_path("structured-document.csv"),
        "image": get_test_resource_path("test.png"),
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
            output=f"live-plain-text-page-size-{size.lower()}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-plain-text-page-size-{size.lower()}"
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
            output=f"live-plain-text-async-page-size-{size.lower()}",
        ),
    )
    _assert_structured_pdf(
        response, source, f"live-plain-text-async-page-size-{size.lower()}"
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
