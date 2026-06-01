from __future__ import annotations

import pytest
from pydantic_core import to_json

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile

from ..resources import get_test_resource_path

SIGNATURE_TYPES = (
    pytest.param("new", id="new"),
    pytest.param("existing", id="existing"),
)

LOGO_OPACITY_BOUNDS = (
    pytest.param((0.01, "min"), id="min"),
    pytest.param((1.0, "max"), id="max"),
)

INVALID_LOGO_OPACITY_VALUES = (
    pytest.param(-0.1, id="below-min"),
    pytest.param(1.1, id="above-max"),
)


def _to_json_string(value: object) -> str:
    return to_json(value).decode("utf-8")


def make_signature_location() -> dict[str, dict[str, int] | int]:
    return {
        "bottom_left": {"x": 1, "y": 1},
        "top_right": {"x": 217, "y": 73},
        "page": 1,
    }


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
    sanitized_passphrase = resource.read_text(encoding="utf-8").strip()
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create(
            [(resource.name, sanitized_passphrase.encode("utf-8"), "text/plain")]
        )[0]


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
        "location": make_signature_location(),
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


def test_live_sign_pdf_with_existing_signature_field(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_certificate: PdfRestFile,
    uploaded_private_key: PdfRestFile,
) -> None:
    signature_name = "sdk-existing-live"
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        first_response = client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "name": signature_name,
                "location": make_signature_location(),
            },
            credentials={
                "certificate": uploaded_certificate,
                "private_key": uploaded_private_key,
            },
            output="live-signed-new-for-existing",
        )

        existing_response = client.sign_pdf(
            first_response.output_file,
            signature_configuration={"type": "existing", "name": signature_name},
            credentials={
                "certificate": uploaded_certificate,
                "private_key": uploaded_private_key,
            },
            output="live-signed-existing",
        )

    assert existing_response.output_file.type == "application/pdf"
    assert existing_response.output_file.name == "live-signed-existing.pdf"
    assert str(first_response.output_file.id) in existing_response.input_ids


@pytest.mark.parametrize("signature_type", SIGNATURE_TYPES)
def test_live_sign_pdf_signature_type_literals(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
    signature_type: str,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        if signature_type == "new":
            response = client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "name": "live-sign-literal-new",
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                output="live-sign-literal-new",
            )
        else:
            signature_name = "live-sign-literal-existing"
            prepared = client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "name": signature_name,
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                output="live-sign-literal-existing-prep",
            )
            response = client.sign_pdf(
                prepared.output_file,
                signature_configuration={"type": "existing", "name": signature_name},
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                output="live-sign-literal-existing",
            )

    assert response.output_file.type == "application/pdf"
    assert str(response.output_file.id) in str(response.output_file.url)


@pytest.mark.parametrize("logo_opacity_case", LOGO_OPACITY_BOUNDS)
def test_live_sign_pdf_logo_opacity_bounds(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_certificate: PdfRestFile,
    uploaded_private_key: PdfRestFile,
    uploaded_logo: PdfRestFile,
    logo_opacity_case: tuple[float, str],
) -> None:
    logo_opacity, case_label = logo_opacity_case
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "name": f"live-logo-opacity-{case_label}",
                "logo_opacity": logo_opacity,
                "location": make_signature_location(),
            },
            credentials={
                "certificate": uploaded_certificate,
                "private_key": uploaded_private_key,
            },
            logo=uploaded_logo,
            output=f"live-logo-opacity-{case_label}",
        )

    assert response.output_file.type == "application/pdf"
    assert uploaded_logo.id in response.input_ids


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
        "name": "live-async-signature",
        "logo_opacity": 0.5,
        "location": make_signature_location(),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("signature_type", SIGNATURE_TYPES)
async def test_live_async_sign_pdf_signature_type_literals(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
    signature_type: str,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        if signature_type == "new":
            response = await client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "name": "live-async-sign-literal-new",
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                output="live-async-sign-literal-new",
            )
        else:
            signature_name = "live-async-sign-literal-existing"
            prepared = await client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "name": signature_name,
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                output="live-async-sign-literal-existing-prep",
            )
            response = await client.sign_pdf(
                prepared.output_file,
                signature_configuration={"type": "existing", "name": signature_name},
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                output="live-async-sign-literal-existing",
            )

    assert response.output_file.type == "application/pdf"
    assert str(response.output_file.id) in str(response.output_file.url)


@pytest.mark.asyncio
@pytest.mark.parametrize("logo_opacity_case", LOGO_OPACITY_BOUNDS)
async def test_live_async_sign_pdf_logo_opacity_bounds(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_certificate: PdfRestFile,
    uploaded_private_key: PdfRestFile,
    uploaded_logo: PdfRestFile,
    logo_opacity_case: tuple[float, str],
) -> None:
    logo_opacity, case_label = logo_opacity_case
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "name": f"live-async-logo-opacity-{case_label}",
                "logo_opacity": logo_opacity,
                "location": make_signature_location(),
            },
            credentials={
                "certificate": uploaded_certificate,
                "private_key": uploaded_private_key,
            },
            logo=uploaded_logo,
            output=f"live-async-logo-opacity-{case_label}",
        )

    assert response.output_file.type == "application/pdf"
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
        pytest.raises(
            PdfRestApiError,
            match=r"JSON data provided is not properly formatted",
        ),
    ):
        client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            extra_body={"signature_configuration": "not-json"},
        )


def test_live_sign_pdf_invalid_signature_type_literal(
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
        pytest.raises(PdfRestApiError, match=r"(?i)signature|type|formatted"),
    ):
        client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            extra_body={
                "signature_configuration": _to_json_string(
                    {"type": "unexpected", "location": make_signature_location()}
                )
            },
        )


@pytest.mark.parametrize("invalid_logo_opacity", INVALID_LOGO_OPACITY_VALUES)
def test_live_sign_pdf_invalid_logo_opacity(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
    invalid_logo_opacity: float,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)logo_opacity|opacity|formatted"),
    ):
        client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            extra_body={
                "signature_configuration": _to_json_string(
                    {
                        "type": "new",
                        "name": "live-invalid-logo-opacity",
                        "location": make_signature_location(),
                        "logo_opacity": invalid_logo_opacity,
                    }
                )
            },
        )


def test_live_sign_pdf_logo_opacity_zero_is_allowed(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "name": "live-logo-opacity-zero",
                "location": make_signature_location(),
            },
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            extra_body={
                "signature_configuration": _to_json_string(
                    {
                        "type": "new",
                        "name": "live-logo-opacity-zero",
                        "location": make_signature_location(),
                        "logo_opacity": 0.0,
                    }
                )
            },
            output="live-logo-opacity-zero",
        )

    assert response.output_file.type == "application/pdf"
    assert response.output_file.name == "live-logo-opacity-zero.pdf"
    assert str(uploaded_pdf_for_signing.id) in response.input_ids


@pytest.mark.asyncio
async def test_live_async_sign_pdf_invalid_signature_configuration(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError,
            match=r"JSON data provided is not properly formatted",
        ):
            await client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                extra_body={"signature_configuration": "not-json"},
            )


@pytest.mark.asyncio
async def test_live_async_sign_pdf_invalid_signature_type_literal(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)signature|type|formatted"):
            await client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                extra_body={
                    "signature_configuration": _to_json_string(
                        {"type": "unexpected", "location": make_signature_location()}
                    )
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_logo_opacity", INVALID_LOGO_OPACITY_VALUES)
async def test_live_async_sign_pdf_invalid_logo_opacity(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
    invalid_logo_opacity: float,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError, match=r"(?i)logo_opacity|opacity|formatted"
        ):
            await client.sign_pdf(
                uploaded_pdf_for_signing,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={
                    "pfx": uploaded_pfx_credential,
                    "passphrase": uploaded_passphrase,
                },
                extra_body={
                    "signature_configuration": _to_json_string(
                        {
                            "type": "new",
                            "name": "live-async-invalid-logo-opacity",
                            "location": make_signature_location(),
                            "logo_opacity": invalid_logo_opacity,
                        }
                    )
                },
            )


@pytest.mark.asyncio
async def test_live_async_sign_pdf_logo_opacity_zero_is_allowed(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_signing: PdfRestFile,
    uploaded_pfx_credential: PdfRestFile,
    uploaded_passphrase: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.sign_pdf(
            uploaded_pdf_for_signing,
            signature_configuration={
                "type": "new",
                "name": "live-async-logo-opacity-zero",
                "location": make_signature_location(),
            },
            credentials={
                "pfx": uploaded_pfx_credential,
                "passphrase": uploaded_passphrase,
            },
            extra_body={
                "signature_configuration": _to_json_string(
                    {
                        "type": "new",
                        "name": "live-async-logo-opacity-zero",
                        "location": make_signature_location(),
                        "logo_opacity": 0.0,
                    }
                )
            },
            output="live-async-logo-opacity-zero",
        )

    assert response.output_file.type == "application/pdf"
    assert response.output_file.name == "live-async-logo-opacity-zero.pdf"
    assert str(uploaded_pdf_for_signing.id) in response.input_ids
