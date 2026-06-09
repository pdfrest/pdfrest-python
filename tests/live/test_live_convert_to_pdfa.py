from __future__ import annotations

from typing import Any, cast, get_args

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile
from pdfrest.types import PdfAType

from ..resources import get_test_resource_path

PDFA_TYPES: tuple[PdfAType, ...] = cast(tuple[PdfAType, ...], get_args(PdfAType))
PDFA_TYPE_PARAMS = [
    pytest.param(output_type, id=output_type) for output_type in PDFA_TYPES
]


@pytest.fixture(scope="module")
def uploaded_pdf_for_pdfa(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.mark.parametrize("output_type", PDFA_TYPE_PARAMS)
def test_live_convert_to_pdfa_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
    output_type: PdfAType,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type=output_type,
            output="pdfa-live",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert str(response.input_id) == str(uploaded_pdf_for_pdfa.id)
    assert output_file.name.startswith("pdfa-live")


@pytest.mark.asyncio
@pytest.mark.parametrize("output_type", PDFA_TYPE_PARAMS)
async def test_live_async_convert_to_pdfa_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
    output_type: PdfAType,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type=output_type,
            output="async-pdfa",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async-pdfa")
    assert output_file.type == "application/pdf"
    assert str(response.input_id) == str(uploaded_pdf_for_pdfa.id)


def test_live_convert_to_pdfa_with_rasterize_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type="PDF/A-2b",
            rasterize_if_errors_encountered="on",
            output="pdfa-rasterize",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("pdfa-rasterize")
    assert output_file.type == "application/pdf"
    assert str(response.input_id) == str(uploaded_pdf_for_pdfa.id)


def test_live_convert_to_pdfa_accepts_lowercase_output_type(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type=cast(Any, "pdf/a-2b"),
            output="pdfa-lowercase",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("pdfa-lowercase")
    assert output_file.type == "application/pdf"
    assert str(response.input_id) == str(uploaded_pdf_for_pdfa.id)


@pytest.mark.asyncio
async def test_live_async_convert_to_pdfa_with_rasterize_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type="PDF/A-2b",
            rasterize_if_errors_encountered="on",
            output="async-pdfa-rasterize",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async-pdfa-rasterize")
    assert output_file.type == "application/pdf"
    assert str(response.input_id) == str(uploaded_pdf_for_pdfa.id)


@pytest.mark.asyncio
async def test_live_async_convert_to_pdfa_accepts_lowercase_output_type(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type=cast(Any, "pdf/a-2b"),
            output="async-pdfa-lowercase",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async-pdfa-lowercase")
    assert output_file.type == "application/pdf"
    assert str(response.input_id) == str(uploaded_pdf_for_pdfa.id)


@pytest.mark.parametrize(
    "invalid_output_type",
    [
        pytest.param("PDF/A-0", id="pdfa-0"),
        pytest.param("PDF/A-99", id="pdfa-99"),
    ],
)
def test_live_convert_to_pdfa_invalid_output_type(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
    invalid_output_type: str,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)pdf.?a"),
    ):
        client.convert_to_pdfa(
            uploaded_pdf_for_pdfa,
            output_type="PDF/A-1b",
            extra_body={"output_type": invalid_output_type},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_output_type",
    [
        pytest.param("PDF/A-0", id="pdfa-0"),
        pytest.param("PDF/A-99", id="pdfa-99"),
    ],
)
async def test_live_async_convert_to_pdfa_invalid_output_type(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_pdfa: PdfRestFile,
    invalid_output_type: str,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)pdf.?a"):
            await client.convert_to_pdfa(
                uploaded_pdf_for_pdfa,
                output_type="PDF/A-1b",
                extra_body={"output_type": invalid_output_type},
            )
