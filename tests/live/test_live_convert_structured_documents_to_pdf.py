from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse
from pdfrest.types import (
    PdfStructuredTextCsvColumn,
    PdfStructuredTextDataPresentation,
    PdfStructuredTextLineHandling,
    PdfStructuredTextMissingImageAltText,
    PdfStructuredTextPageOrientation,
    PdfStructuredTextTextAlignment,
)

from ..resources import get_test_resource_path


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
