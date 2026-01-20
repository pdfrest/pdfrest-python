from __future__ import annotations

import json

import httpx
import pytest

from pdfrest import AsyncPdfRestClient, PdfRestClient, PdfRestConfigurationError
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfSignPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)


def make_pfx_file(file_id: str) -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(file_id, "signer.pfx", "application/x-pkcs12")
    )


def make_passphrase_file(file_id: str) -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(file_id, "passphrase.txt", "text/plain")
    )


def make_certificate_file(file_id: str) -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(file_id, "certificate.pem", "application/pkix-cert")
    )


def make_private_key_file(file_id: str) -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(file_id, "private_key.der", "application/pkcs8")
    )


def make_logo_file(file_id: str) -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(file_id, "logo.png", "image/png")
    )


def test_sign_pdf_with_pfx_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())

    signature_configuration = {
        "type": "new",
        "name": "esignature",
        "display": {"include_datetime": True, "name": "Signer"},
    }
    payload_dump = PdfSignPayload.model_validate(
        {
            "files": [input_file],
            "signature_configuration": signature_configuration,
            "pfx_credential": [pfx_file],
            "pfx_passphrase": [passphrase_file],
            "output": "signed-pdf",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id, pfx_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "signed-pdf.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.sign_pdf(
            input_file,
            signature_configuration=signature_configuration,
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
            output="signed-pdf",
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "signed-pdf.pdf"
    assert str(input_file.id) in {str(item) for item in response.input_ids}


def test_sign_pdf_with_certificate_credentials_and_logo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    logo_file = make_logo_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())

    signature_configuration = {
        "type": "new",
        "name": "visible signature",
        "location": {
            "bottom_left": {"x": 0, "y": 0},
            "top_right": {"x": 216, "y": 72},
            "page": 1,
        },
    }
    payload_dump = PdfSignPayload.model_validate(
        {
            "files": [input_file],
            "signature_configuration": signature_configuration,
            "certificate": [certificate_file],
            "private_key": [private_key_file],
            "logo": [logo_file],
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "inputId": [
                        input_file.id,
                        certificate_file.id,
                        private_key_file.id,
                        logo_file.id,
                    ],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "signed.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.sign_pdf(
            input_file,
            signature_configuration=signature_configuration,
            credentials={
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
            logo=logo_file,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "signed.pdf"
    assert logo_file.id in response.input_ids


def test_sign_pdf_requires_credential_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(3))
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(PdfRestConfigurationError, match=r"pfx.*passphrase"),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={"type": "new"},
            credentials={"pfx": pfx_file},
        )


@pytest.mark.asyncio
async def test_async_sign_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(4))
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async-sign"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["certificate_id"] == str(certificate_file.id)
            assert payload["private_key_id"] == str(private_key_file.id)
            assert json.loads(payload["signature_configuration"])["type"] == "new"
            assert payload["output"] == "async-signed"
            assert payload["diagnostics"] == "on"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async-sign"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-signed.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=transport,
    ) as client:
        response = await client.sign_pdf(
            input_file,
            signature_configuration={"type": "new"},
            credentials={
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
            output="async-signed",
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async-sign"},
            extra_body={"diagnostics": "on"},
            timeout=0.5,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async-signed.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(pytest.approx(0.5) == value for value in timeout_value.values())
    else:
        assert timeout_value == pytest.approx(0.5)
