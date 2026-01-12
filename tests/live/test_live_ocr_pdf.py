from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse

from ..resources import get_test_resource_path


def test_live_ocr_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        response = client.ocr_pdf(uploaded, languages=["English", "German"])

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files
    output_file = response.output_file
    assert output_file.name.endswith(".pdf")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert response.input_id == uploaded.id


@pytest.mark.asyncio
async def test_live_async_ocr_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        response = await client.ocr_pdf(uploaded, output="async-ocr")

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files
    assert response.output_file.name.startswith("async-ocr")
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.warning is None
    assert response.input_id == uploaded.id


def test_live_ocr_pdf_invalid_pages(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            client.ocr_pdf(
                uploaded,
                extra_body={"pages": "last-1"},
            )


@pytest.mark.asyncio
async def test_live_async_ocr_pdf_invalid_pages(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            await client.ocr_pdf(
                uploaded,
                extra_body={"pages": "last-1"},
            )
