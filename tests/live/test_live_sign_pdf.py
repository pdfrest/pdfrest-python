from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile

from ..resources import get_test_resource_path


@pytest.fixture(scope="module")
def uploaded_pdf_for_signing(
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
def uploaded_pfx_credential(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("signing_credentials.pfx")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def uploaded_passphrase(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("signing_passphrase.txt")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def uploaded_certificate(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("signing_certificate.pem")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def uploaded_private_key(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("signing_private_key.der")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def uploaded_logo(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("signing_logo.png")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


def test_live_sign_pdf_with_pfx_credentials(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
) -> None:
    signature_configuration = {
        "type": "new",
        "name": "pdfrest-live",
    }
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration=signature_configuration,
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            output="live-signed-pfx",
        )

    assert response.output_file.type == "application/pdf"
    assert response.output_file.name == "live-signed-pfx.pdf"
    assert str(uploaded_pdf_for_signing.id) in response.input_ids


@pytest.mark.asyncio
async def test_live_async_sign_pdf_with_certificate(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_certificate: PdfRestFile,
    uploaded_private_key: PdfRestFile,
    uploaded_logo: PdfRestFile,
) -> None:
    signature_configuration = {
        "type": "new",
        "logo_opacity": 0.5,
        "location": {
            "bottom_left": {"x": 0, "y": 0},
            "top_right": {"x": 216, "y": 72},
            "page": 1,
        },
    }
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration=signature_configuration,
            credentials={
                "certificate": uploaded_certificate,
                "private_key": uploaded_private_key,
            },
            logo=uploaded_logo,
            output="live-signed-cert",
        )

    assert response.output_file.type == "application/pdf"
    assert response.output_file.name == "live-signed-cert.pdf"
    assert uploaded_logo.id in response.input_ids


def test_live_sign_pdf_invalid_signature_configuration(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError),
    ):
        client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={"type": "new"},
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            extra_body={"signature_configuration": "not-json"},
        )
