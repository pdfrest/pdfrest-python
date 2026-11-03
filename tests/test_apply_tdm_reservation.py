from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfTdmReservationPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)

POLICY_URL = "https://rights.example/tdm-policy?version=2#terms"


@pytest.mark.parametrize(
    "policy",
    [
        pytest.param("https://example.com", id="origin"),
        pytest.param(
            "https://example.com/terms%20and%20conditions",
            id="percent-encoded-path",
        ),
    ],
)
def test_tdm_reservation_payload_preserves_policy_url(policy: str) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate(1))

    payload = PdfTdmReservationPayload.model_validate(
        {
            "file": input_file,
            "policy": policy,
            "output": "tdm-reserved",
        }
    )

    assert payload.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    ) == {
        "id": str(input_file.id),
        "policy": policy,
        "output": "tdm-reserved",
    }


def test_tdm_reservation_payload_requires_policy() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate(1))

    with pytest.raises(ValidationError, match=r"policy\s+Field required"):
        PdfTdmReservationPayload.model_validate({"file": input_file})


def test_apply_tdm_reservation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    payload_dump = PdfTdmReservationPayload.model_validate(
        {"file": input_file, "policy": POLICY_URL}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/tdm-reserved-pdf":
            seen["post"] += 1
            assert json.loads(request.content) == payload_dump
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "report_pdfrest_tdm_reserved_pdf.pdf",
                    "application/pdf",
                ),
            )
        message = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(message)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.apply_tdm_reservation(input_file, policy=POLICY_URL)

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert str(response.input_id) == str(input_file.id)
    assert response.output_file.name == "report_pdfrest_tdm_reserved_pdf.pdf"
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.warning is None


def test_apply_tdm_reservation_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["trace"] == "sync"
        assert request.headers["X-Debug"] == "sync"
        if request.method == "POST" and request.url.path == "/tdm-reserved-pdf":
            captured_timeout["value"] = request.extensions.get("timeout")
            assert json.loads(request.content) == {
                "id": str(input_file.id),
                "policy": POLICY_URL,
                "output": "reserved-sync",
                "debug": "yes",
            }
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "reserved-sync.pdf",
                    "application/pdf",
                ),
            )
        message = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(message)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.apply_tdm_reservation(
            input_file,
            policy=POLICY_URL,
            output="reserved-sync",
            extra_query={"trace": "sync"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"debug": "yes"},
            timeout=0.61,
        )

    assert response.output_file.name == "reserved-sync.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.61) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.61)


@pytest.mark.asyncio
async def test_async_apply_tdm_reservation_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())
    payload_dump = PdfTdmReservationPayload.model_validate(
        {"file": input_file, "policy": POLICY_URL}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/tdm-reserved-pdf":
            seen["post"] += 1
            assert json.loads(request.content) == payload_dump
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-report_pdfrest_tdm_reserved_pdf.pdf",
                    "application/pdf",
                ),
            )
        message = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(message)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.apply_tdm_reservation(input_file, policy=POLICY_URL)

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert str(response.input_id) == str(input_file.id)
    assert response.output_file.name == "async-report_pdfrest_tdm_reserved_pdf.pdf"
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.warning is None


@pytest.mark.asyncio
async def test_async_apply_tdm_reservation_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["trace"] == "async"
        assert request.headers["X-Debug"] == "async"
        if request.method == "POST" and request.url.path == "/tdm-reserved-pdf":
            captured_timeout["value"] = request.extensions.get("timeout")
            assert json.loads(request.content) == {
                "id": str(input_file.id),
                "policy": POLICY_URL,
                "output": "reserved-async",
                "flags": ["a", "b"],
            }
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "reserved-async.pdf",
                    "application/pdf",
                ),
            )
        message = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(message)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.apply_tdm_reservation(
            input_file,
            policy=POLICY_URL,
            output="reserved-async",
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async"},
            extra_body={"flags": ["a", "b"]},
            timeout=0.83,
        )

    assert response.output_file.name == "reserved-async.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.83) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.83)


@pytest.mark.parametrize(
    ("policy", "match"),
    [
        pytest.param("", "String should have at least 1 character", id="empty"),
        pytest.param("my-policy", "Must be a valid HTTP or HTTPS URL", id="bare-name"),
        pytest.param(
            "No AI training allowed",
            "Must be a valid HTTP or HTTPS URL",
            id="policy-text",
        ),
        pytest.param(
            "example.com/tdm-policy",
            "Must be a valid HTTP or HTTPS URL",
            id="missing-scheme",
        ),
        pytest.param(
            "ftp://example.com/tdm-policy",
            "Must be a valid HTTP or HTTPS URL",
            id="unsupported-scheme",
        ),
        pytest.param(
            " https://example.com/tdm-policy ",
            "Must be a valid HTTP or HTTPS URL",
            id="surrounding-whitespace",
        ),
        pytest.param(
            "https://example.com/%ZZ",
            "Must be a valid HTTP or HTTPS URL",
            id="invalid-percent-escape",
        ),
        pytest.param(
            "https://example.com\\tdm-policy",
            "Must be a valid HTTP or HTTPS URL",
            id="backslash",
        ),
    ],
)
def test_apply_tdm_reservation_rejects_invalid_policy(
    monkeypatch: pytest.MonkeyPatch,
    policy: str,
    match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    transport = httpx.MockTransport(lambda request: pytest.fail("request was sent"))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.apply_tdm_reservation(input_file, policy=policy)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "match"),
    [
        pytest.param("", "String should have at least 1 character", id="empty"),
        pytest.param("my-policy", "Must be a valid HTTP or HTTPS URL", id="bare-name"),
        pytest.param(
            "No AI training allowed",
            "Must be a valid HTTP or HTTPS URL",
            id="policy-text",
        ),
        pytest.param(
            "example.com/tdm-policy",
            "Must be a valid HTTP or HTTPS URL",
            id="missing-scheme",
        ),
        pytest.param(
            "ftp://example.com/tdm-policy",
            "Must be a valid HTTP or HTTPS URL",
            id="unsupported-scheme",
        ),
        pytest.param(
            "https://example.com/tdm policy",
            "Must be a valid HTTP or HTTPS URL",
            id="embedded-whitespace",
        ),
        pytest.param(
            "https://example.com/%ZZ",
            "Must be a valid HTTP or HTTPS URL",
            id="invalid-percent-escape",
        ),
        pytest.param(
            "https://example.com\\tdm-policy",
            "Must be a valid HTTP or HTTPS URL",
            id="backslash",
        ),
    ],
)
async def test_async_apply_tdm_reservation_rejects_invalid_policy(
    monkeypatch: pytest.MonkeyPatch,
    policy: str,
    match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    transport = httpx.MockTransport(lambda request: pytest.fail("request was sent"))

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=transport,
    ) as client:
        with pytest.raises(ValidationError, match=match):
            await client.apply_tdm_reservation(input_file, policy=policy)


@pytest.mark.parametrize(
    ("files", "match"),
    [
        pytest.param("empty", "at least 1 item", id="empty"),
        pytest.param("png", "Must be a PDF file", id="non-pdf-file"),
        pytest.param(
            "multiple",
            "List should have at most 1 item after validation",
            id="multiple-files",
        ),
    ],
)
def test_apply_tdm_reservation_rejects_incompatible_resources(
    monkeypatch: pytest.MonkeyPatch,
    files: str,
    match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    png_file = PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "example.png",
            "image/png",
        )
    )
    files_argument = {
        "empty": [],
        "png": png_file,
        "multiple": [pdf_file, make_pdf_file(PdfRestFileID.generate())],
    }[files]
    transport = httpx.MockTransport(lambda request: pytest.fail("request was sent"))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.apply_tdm_reservation(files_argument, policy=POLICY_URL)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("files", "match"),
    [
        pytest.param("empty", "at least 1 item", id="empty"),
        pytest.param("png", "Must be a PDF file", id="non-pdf-file"),
        pytest.param(
            "multiple",
            "List should have at most 1 item after validation",
            id="multiple-files",
        ),
    ],
)
async def test_async_apply_tdm_reservation_rejects_incompatible_resources(
    monkeypatch: pytest.MonkeyPatch,
    files: str,
    match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(2))
    png_file = PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "example.png",
            "image/png",
        )
    )
    files_argument = {
        "empty": [],
        "png": png_file,
        "multiple": [pdf_file, make_pdf_file(PdfRestFileID.generate())],
    }[files]
    transport = httpx.MockTransport(lambda request: pytest.fail("request was sent"))

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=transport,
    ) as client:
        with pytest.raises(ValidationError, match=match):
            await client.apply_tdm_reservation(files_argument, policy=POLICY_URL)
