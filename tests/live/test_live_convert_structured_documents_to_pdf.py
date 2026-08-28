from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse
from pdfrest.types import PdfStructuredTextCsvColumn

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


def test_live_convert_markdown_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
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
            missing_image_alt_text="fail",
            output="live-markdown",
        ),
    )
    _assert_structured_pdf(response, source, "live-markdown")
    assert response.input_ids == [source.id, image.id]


def test_live_convert_plain_text_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source, line_handling="preserve", output="live-plain-text"
        ),
    )
    _assert_structured_pdf(response, source, "live-plain-text")


def test_live_convert_json_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["json"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_json_to_pdf(
            source, data_presentation="hierarchy", output="live-json"
        ),
    )
    _assert_structured_pdf(response, source, "live-json")


def test_live_convert_xml_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["xml"]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_xml_to_pdf(
            source, data_presentation="source", output="live-xml"
        ),
    )
    _assert_structured_pdf(response, source, "live-xml")


def test_live_convert_csv_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["csv"]
    columns = [
        PdfStructuredTextCsvColumn(index=0, text_align="left", width_weight=2),
        PdfStructuredTextCsvColumn(index=1, text_align="right", width_weight=1),
    ]
    response = _run_sync(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_csv_to_pdf(
            source,
            first_row_is_header=True,
            columns=columns,
            output="live-csv",
        ),
    )
    _assert_structured_pdf(response, source, "live-csv")


@pytest.mark.asyncio
async def test_live_async_convert_markdown_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["markdown"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_markdown_to_pdf(
            source, enable_tagging=True, output="live-markdown-async"
        ),
    )
    _assert_structured_pdf(response, source, "live-markdown-async")


@pytest.mark.asyncio
async def test_live_async_convert_plain_text_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["plain_text"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_plain_text_to_pdf(
            source, line_handling="reflow", output="live-plain-text-async"
        ),
    )
    _assert_structured_pdf(response, source, "live-plain-text-async")


@pytest.mark.asyncio
async def test_live_async_convert_json_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["json"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_json_to_pdf(
            source, data_presentation="source", output="live-json-async"
        ),
    )
    _assert_structured_pdf(response, source, "live-json-async")


@pytest.mark.asyncio
async def test_live_async_convert_xml_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["xml"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_xml_to_pdf(
            source, data_presentation="hierarchy", output="live-xml-async"
        ),
    )
    _assert_structured_pdf(response, source, "live-xml-async")


@pytest.mark.asyncio
async def test_live_async_convert_csv_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_structured_documents: dict[str, PdfRestFile],
) -> None:
    source = uploaded_structured_documents["csv"]
    response = await _run_async(
        pdfrest_api_key,
        pdfrest_live_base_url,
        lambda client: client.convert_csv_to_pdf(
            source, delimiter=",", output="live-csv-async"
        ),
    )
    _assert_structured_pdf(response, source, "live-csv-async")


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
