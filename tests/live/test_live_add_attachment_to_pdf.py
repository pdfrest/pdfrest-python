from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile

from ..resources import get_test_resource_path


@pytest.fixture(scope="module")
def uploaded_pdf_for_attachment(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def uploaded_attachment_file(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.docx")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


def test_live_add_attachment_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_attachment: PdfRestFile,
    uploaded_attachment_file: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_attachment_to_pdf(
            uploaded_pdf_for_attachment,
            attachment=uploaded_attachment_file,
            output="with-attachment",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("with-attachment")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert [str(file_id) for file_id in response.input_ids] == [
        str(uploaded_pdf_for_attachment.id),
        str(uploaded_attachment_file.id),
    ]


@pytest.mark.asyncio
async def test_live_async_add_attachment_to_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_attachment: PdfRestFile,
    uploaded_attachment_file: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_attachment_to_pdf(
            uploaded_pdf_for_attachment,
            attachment=uploaded_attachment_file,
            output="async-attachment",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async-attachment")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert [str(file_id) for file_id in response.input_ids] == [
        str(uploaded_pdf_for_attachment.id),
        str(uploaded_attachment_file.id),
    ]


def test_live_add_attachment_to_pdf_invalid_file_id(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_attachment: PdfRestFile,
    uploaded_attachment_file: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)(id|file)"),
    ):
        client.add_attachment_to_pdf(
            uploaded_pdf_for_attachment,
            attachment=uploaded_attachment_file,
            extra_body={"id": "00000000-0000-0000-0000-000000000000"},
        )


@pytest.mark.asyncio
async def test_live_async_add_attachment_to_pdf_invalid_attachment_id(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_attachment: PdfRestFile,
    uploaded_attachment_file: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)(id|file)"):
            await client.add_attachment_to_pdf(
                uploaded_pdf_for_attachment,
                attachment=uploaded_attachment_file,
                extra_body={"id_to_attach": "ffffffff-ffff-ffff-ffff-ffffffffffff"},
            )
