from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
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


def make_signature_location() -> dict[str, dict[str, int] | int]:
    return {
        "bottom_left": {"x": 0, "y": 0},
        "top_right": {"x": 216, "y": 72},
        "page": 1,
    }


def make_signature_configuration(signature_type: str) -> dict[str, object]:
    if signature_type == "new":
        return {
            "type": "new",
            "name": "esignature",
            "location": make_signature_location(),
        }
    return {"type": "existing", "name": "esignature"}


MULTI_FILE_CREDENTIAL_CASES = (
    pytest.param("pfx", "passphrase", make_pfx_file, make_passphrase_file, id="pfx"),
    pytest.param(
        "passphrase",
        "pfx",
        make_passphrase_file,
        make_pfx_file,
        id="passphrase",
    ),
    pytest.param(
        "certificate",
        "private_key",
        make_certificate_file,
        make_private_key_file,
        id="certificate",
    ),
    pytest.param(
        "private_key",
        "certificate",
        make_private_key_file,
        make_certificate_file,
        id="private-key",
    ),
)


def test_sign_pdf_with_pfx_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())
    seen = {"post": 0, "get": 0}

    signature_configuration = {
        "type": "new",
        "name": "esignature",
        "location": make_signature_location(),
        "display": {"include_datetime": True, "name": "Signer"},
    }
    payload_dump = PdfSignPayload.model_validate(
        {
            "files": [input_file],
            "signature_configuration": signature_configuration,
            "credentials": {"pfx": pfx_file, "passphrase": passphrase_file},
            "output": "signed-pdf",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            seen["post"] += 1
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
            seen["get"] += 1
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
    assert seen == {"post": 1, "get": 1}


def test_sign_pdf_with_certificate_credentials_and_logo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    logo_file = make_logo_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())
    seen = {"post": 0, "get": 0}

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
            "credentials": {
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
            "logo": [logo_file],
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            seen["post"] += 1
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
            seen["get"] += 1
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
    assert seen == {"post": 1, "get": 1}


def test_sign_pdf_requires_credential_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match=r"Both pfx and passphrase"),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={"pfx": pfx_file},
        )


def test_sign_pdf_rejects_non_mapping_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match=r"credentials must be a mapping"),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials=["not-a-mapping"],  # type: ignore[arg-type]
        )


def test_sign_pdf_requires_location_for_new_signature_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=r"Missing location information for a new digital signature field",
        ),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={"type": "new"},
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )


def test_sign_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file_a = make_pdf_file(PdfRestFileID.generate())
    input_file_b = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=r"files\n\s+List should have at most 1 item after validation",
        ),
    ):
        client.sign_pdf(
            [input_file_a, input_file_b],
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )


def test_sign_pdf_rejects_multiple_logo_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    logo_file_a = make_logo_file(str(PdfRestFileID.generate()))
    logo_file_b = make_logo_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=r"logo\n\s+List should have at most 1 item after validation",
        ),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
            logo=[logo_file_a, logo_file_b],
        )


@pytest.mark.parametrize(
    ("multi_field", "single_field", "multi_factory", "single_factory"),
    MULTI_FILE_CREDENTIAL_CASES,
)
def test_sign_pdf_rejects_multiple_credential_files(
    monkeypatch: pytest.MonkeyPatch,
    multi_field: str,
    single_field: str,
    multi_factory: Callable[[str], PdfRestFile],
    single_factory: Callable[[str], PdfRestFile],
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    multi_file_a = multi_factory(str(PdfRestFileID.generate()))
    multi_file_b = multi_factory(str(PdfRestFileID.generate()))
    single_file = single_factory(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    expected_match = (
        rf"{multi_field}\n\s+List should have at most 1 item after validation"
    )
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match=expected_match),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={
                multi_field: [multi_file_a, multi_file_b],  # type: ignore[dict-item]
                single_field: single_file,
            },
        )


@pytest.mark.asyncio
async def test_async_sign_pdf_requires_credential_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match=r"Both pfx and passphrase"):
            await client.sign_pdf(
                input_file,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={"pfx": pfx_file},
            )


@pytest.mark.asyncio
async def test_async_sign_pdf_rejects_non_mapping_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match=r"credentials must be a mapping"):
            await client.sign_pdf(
                input_file,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials=["not-a-mapping"],  # type: ignore[arg-type]
            )


@pytest.mark.asyncio
async def test_async_sign_pdf_requires_location_for_new_signature_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=r"Missing location information for a new digital signature field",
        ):
            await client.sign_pdf(
                input_file,
                signature_configuration={"type": "new"},
                credentials={"pfx": pfx_file, "passphrase": passphrase_file},
            )


@pytest.mark.asyncio
async def test_async_sign_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file_a = make_pdf_file(PdfRestFileID.generate())
    input_file_b = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=r"files\n\s+List should have at most 1 item after validation",
        ):
            await client.sign_pdf(
                [input_file_a, input_file_b],
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={"pfx": pfx_file, "passphrase": passphrase_file},
            )


@pytest.mark.asyncio
async def test_async_sign_pdf_rejects_multiple_logo_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    logo_file_a = make_logo_file(str(PdfRestFileID.generate()))
    logo_file_b = make_logo_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=r"logo\n\s+List should have at most 1 item after validation",
        ):
            await client.sign_pdf(
                input_file,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={
                    "certificate": certificate_file,
                    "private_key": private_key_file,
                },
                logo=[logo_file_a, logo_file_b],
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("multi_field", "single_field", "multi_factory", "single_factory"),
    MULTI_FILE_CREDENTIAL_CASES,
)
async def test_async_sign_pdf_rejects_multiple_credential_files(
    monkeypatch: pytest.MonkeyPatch,
    multi_field: str,
    single_field: str,
    multi_factory: Callable[[str], PdfRestFile],
    single_factory: Callable[[str], PdfRestFile],
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    multi_file_a = multi_factory(str(PdfRestFileID.generate()))
    multi_file_b = multi_factory(str(PdfRestFileID.generate()))
    single_file = single_factory(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    expected_match = (
        rf"{multi_field}\n\s+List should have at most 1 item after validation"
    )
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match=expected_match):
            await client.sign_pdf(
                input_file,
                signature_configuration={
                    "type": "new",
                    "location": make_signature_location(),
                },
                credentials={
                    multi_field: [multi_file_a, multi_file_b],  # type: ignore[dict-item]
                    single_field: single_file,
                },
            )


@pytest.mark.parametrize(
    "signature_type",
    [
        pytest.param("new", id="new"),
        pytest.param("existing", id="existing"),
    ],
)
def test_sign_pdf_signature_type_literal_matrix(
    monkeypatch: pytest.MonkeyPatch,
    signature_type: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            payload = json.loads(request.content.decode("utf-8"))
            signature_payload = json.loads(payload["signature_configuration"])
            assert signature_payload["type"] == signature_type
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    f"literal-{signature_type}.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.sign_pdf(
            input_file,
            signature_configuration=make_signature_configuration(signature_type),
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )

    assert response.output_file.name == f"literal-{signature_type}.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signature_type",
    [
        pytest.param("new", id="new"),
        pytest.param("existing", id="existing"),
    ],
)
async def test_async_sign_pdf_signature_type_literal_matrix(
    monkeypatch: pytest.MonkeyPatch,
    signature_type: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            payload = json.loads(request.content.decode("utf-8"))
            signature_payload = json.loads(payload["signature_configuration"])
            assert signature_payload["type"] == signature_type
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    f"literal-async-{signature_type}.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.sign_pdf(
            input_file,
            signature_configuration=make_signature_configuration(signature_type),
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )

    assert response.output_file.name == f"literal-async-{signature_type}.pdf"


def test_sign_pdf_rejects_invalid_signature_type_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Input should be 'new' or 'existing'"),
    ):
        client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "unexpected",
                "location": make_signature_location(),
            },
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )


@pytest.mark.asyncio
async def test_async_sign_pdf_rejects_invalid_signature_type_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError, match="Input should be 'new' or 'existing'"
        ):
            await client.sign_pdf(
                input_file,
                signature_configuration={
                    "type": "unexpected",
                    "location": make_signature_location(),
                },
                credentials={"pfx": pfx_file, "passphrase": passphrase_file},
            )


def test_sign_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            seen["post"] += 1
            assert request.url.params["trace"] == "sync"
            assert request.headers["X-Debug"] == "sync-sign"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["certificate_id"] == str(certificate_file.id)
            assert payload["private_key_id"] == str(private_key_file.id)
            assert json.loads(payload["signature_configuration"])["type"] == "new"
            assert payload["output"] == "sync-signed"
            assert payload["diagnostics"] == "on"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["trace"] == "sync"
            assert request.headers["X-Debug"] == "sync-sign"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "sync-signed.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
            credentials={
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
            output="sync-signed",
            extra_query={"trace": "sync"},
            extra_headers={"X-Debug": "sync-sign"},
            extra_body={"diagnostics": "on"},
            timeout=0.5,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "sync-signed.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(pytest.approx(0.5) == value for value in timeout_value.values())
    else:
        assert timeout_value == pytest.approx(0.5)
    assert seen == {"post": 1, "get": 1}


def test_sign_pdf_allows_zero_logo_opacity_via_public_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            payload = json.loads(request.content.decode("utf-8"))
            signature_payload = json.loads(payload["signature_configuration"])
            assert signature_payload["logo_opacity"] == pytest.approx(0.0)
            assert signature_payload["type"] == "new"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "logo-opacity-zero.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "name": "visible-zero",
                "location": make_signature_location(),
                "logo_opacity": 0.0,
            },
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "logo-opacity-zero.pdf"


@pytest.mark.asyncio
async def test_async_sign_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            seen["post"] += 1
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
            seen["get"] += 1
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
            signature_configuration={
                "type": "new",
                "location": make_signature_location(),
            },
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
    assert seen == {"post": 1, "get": 1}


@pytest.mark.asyncio
async def test_async_sign_pdf_allows_zero_logo_opacity_via_public_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/signed-pdf":
            payload = json.loads(request.content.decode("utf-8"))
            signature_payload = json.loads(payload["signature_configuration"])
            assert signature_payload["logo_opacity"] == pytest.approx(0.0)
            assert signature_payload["type"] == "new"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-logo-opacity-zero.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.sign_pdf(
            input_file,
            signature_configuration={
                "type": "new",
                "name": "async-visible-zero",
                "location": make_signature_location(),
                "logo_opacity": 0.0,
            },
            credentials={"pfx": pfx_file, "passphrase": passphrase_file},
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async-logo-opacity-zero.pdf"


def test_sign_payload_requires_location_when_type_new() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))

    with pytest.raises(
        ValidationError,
        match=r"Missing location information for a new digital signature field",
    ):
        PdfSignPayload.model_validate(
            {
                "files": [input_file],
                "signature_configuration": {"type": "new", "name": "sig"},
                "credentials": {"pfx": pfx_file, "passphrase": passphrase_file},
            }
        )


def test_sign_payload_allows_existing_without_location() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))

    payload = PdfSignPayload.model_validate(
        {
            "files": [input_file],
            "signature_configuration": {"type": "existing", "name": "sig"},
            "credentials": {"pfx": pfx_file, "passphrase": passphrase_file},
        }
    )
    assert payload.signature_configuration.type == "existing"


def test_sign_payload_accepts_x509_ca_cert_mime_for_der_credentials() -> None:
    input_pdf = make_pdf_file(str(PdfRestFileID.generate()))
    certificate_file = PdfRestFile.model_validate(
        build_file_info_payload(
            str(PdfRestFileID.generate()),
            "certificate.der",
            "application/x-x509-ca-cert",
        )
    )
    private_key_file = PdfRestFile.model_validate(
        build_file_info_payload(
            str(PdfRestFileID.generate()),
            "private_key.der",
            "application/x-x509-ca-cert",
        )
    )

    payload = PdfSignPayload.model_validate(
        {
            "files": [input_pdf],
            "signature_configuration": {
                "type": "new",
                "name": "sig",
                "location": make_signature_location(),
            },
            "credentials": {
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
        }
    )

    assert payload.certificate is not None
    assert payload.private_key is not None
    assert payload.certificate[0].type == "application/x-x509-ca-cert"
    assert payload.private_key[0].type == "application/x-x509-ca-cert"


def test_sign_payload_accepts_pem_certificate_chain_mime_for_pem_credentials() -> None:
    input_pdf = make_pdf_file(str(PdfRestFileID.generate()))
    certificate_file = PdfRestFile.model_validate(
        build_file_info_payload(
            str(PdfRestFileID.generate()),
            "certificate.pem",
            "application/pem-certificate-chain",
        )
    )
    private_key_file = PdfRestFile.model_validate(
        build_file_info_payload(
            str(PdfRestFileID.generate()),
            "private_key.pem",
            "application/pem-certificate-chain",
        )
    )

    payload = PdfSignPayload.model_validate(
        {
            "files": [input_pdf],
            "signature_configuration": {
                "type": "new",
                "name": "sig",
                "location": make_signature_location(),
            },
            "credentials": {
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
        }
    )

    assert payload.certificate is not None
    assert payload.private_key is not None
    assert payload.certificate[0].type == "application/pem-certificate-chain"
    assert payload.private_key[0].type == "application/pem-certificate-chain"


def test_sign_payload_accepts_logo_tuple_sequence() -> None:
    input_pdf = make_pdf_file(str(PdfRestFileID.generate()))
    certificate_file = make_certificate_file(str(PdfRestFileID.generate()))
    private_key_file = make_private_key_file(str(PdfRestFileID.generate()))
    logo_file = make_logo_file(str(PdfRestFileID.generate()))

    payload = PdfSignPayload.model_validate(
        {
            "files": [input_pdf],
            "signature_configuration": {
                "type": "new",
                "name": "sig",
                "location": make_signature_location(),
            },
            "credentials": {
                "certificate": certificate_file,
                "private_key": private_key_file,
            },
            "logo": (logo_file,),
        }
    )

    assert payload.logo is not None
    assert len(payload.logo) == 1
    assert payload.logo[0].id == logo_file.id


@pytest.mark.parametrize(
    "logo_opacity",
    [
        pytest.param(0.0, id="zero"),
        pytest.param(0.01, id="min"),
        pytest.param(1.0, id="max"),
    ],
)
def test_sign_payload_accepts_logo_opacity_bounds(logo_opacity: float) -> None:
    input_pdf = make_pdf_file(str(PdfRestFileID.generate()))
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))

    payload = PdfSignPayload.model_validate(
        {
            "files": [input_pdf],
            "signature_configuration": {
                "type": "new",
                "name": "sig",
                "logo_opacity": logo_opacity,
                "location": make_signature_location(),
            },
            "credentials": {"pfx": pfx_file, "passphrase": passphrase_file},
        }
    )

    assert payload.signature_configuration.logo_opacity == pytest.approx(logo_opacity)


@pytest.mark.parametrize(
    "invalid_logo_opacity",
    [
        pytest.param(-0.01, id="below-min"),
        pytest.param(1.01, id="above-max"),
    ],
)
def test_sign_payload_rejects_logo_opacity_out_of_bounds(
    invalid_logo_opacity: float,
) -> None:
    input_pdf = make_pdf_file(str(PdfRestFileID.generate()))
    pfx_file = make_pfx_file(str(PdfRestFileID.generate()))
    passphrase_file = make_passphrase_file(str(PdfRestFileID.generate()))

    with pytest.raises(
        ValidationError,
        match=r"greater than or equal to 0|less than or equal to 1",
    ):
        PdfSignPayload.model_validate(
            {
                "files": [input_pdf],
                "signature_configuration": {
                    "type": "new",
                    "name": "sig",
                    "logo_opacity": invalid_logo_opacity,
                    "location": make_signature_location(),
                },
                "credentials": {"pfx": pfx_file, "passphrase": passphrase_file},
            }
        )
