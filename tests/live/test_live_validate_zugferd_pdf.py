from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile, PdfZugferdValidationResponse

from ..resources import get_test_resource_path


@pytest.fixture(scope="module")
def generated_zugferd_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    invoice_path = get_test_resource_path("zugferd-minimum-invoice.xml")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        invoice = client.files.create_from_paths(invoice_path)[0]
        response = client.create_zugferd_pdf(
            invoice,
            output="validation-source-zugferd",
        )
    return response.output_file


def _assert_valid_response(
    response: PdfZugferdValidationResponse,
    source: PdfRestFile,
) -> None:
    assert response.status == "VALID"
    assert response.pdfa is True
    assert response.content_match_status in {"CONFIRMED", "DEMO_REDACTED"}
    assert response.input_id == source.id
    assert f"/resource/{source.id}" in response.input_url
    if response.findings is not None:
        assert all(finding.code for finding in response.findings)
        assert all(finding.message for finding in response.findings)


def test_live_validate_zugferd_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    generated_zugferd_pdf: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.validate_zugferd_pdf(generated_zugferd_pdf)

    _assert_valid_response(response, generated_zugferd_pdf)


@pytest.mark.asyncio
async def test_live_async_validate_zugferd_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    generated_zugferd_pdf: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.validate_zugferd_pdf(generated_zugferd_pdf)

    _assert_valid_response(response, generated_zugferd_pdf)


def test_live_validate_zugferd_pdf_rejects_invalid_resource_id(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    generated_zugferd_pdf: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)invalid|resource|processing"),
    ):
        client.validate_zugferd_pdf(
            generated_zugferd_pdf,
            extra_body={"id": "not-a-resource-id"},
        )


@pytest.mark.asyncio
async def test_live_async_validate_zugferd_pdf_rejects_invalid_resource_id(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    generated_zugferd_pdf: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)invalid|resource|processing"):
            await client.validate_zugferd_pdf(
                generated_zugferd_pdf,
                extra_body={"id": "not-a-resource-id"},
            )
