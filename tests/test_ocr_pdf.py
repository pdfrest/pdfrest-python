from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import OcrPdfPayload

from .graphics_test_helpers import ASYNC_API_KEY, VALID_API_KEY, make_pdf_file


def test_ocr_payload_rejects_non_pdf() -> None:
    file_id = str(PdfRestFileID.generate())
    text_file = PdfRestFile.model_validate(
        {
            "id": file_id,
            "name": "notes.txt",
            "url": f"https://api.pdfrest.com/resource/{file_id}",
            "type": "text/plain",
            "size": 64,
            "modified": "2024-01-01T00:00:00Z",
            "scheduledDeletionTimeUtc": None,
        }
    )
    with pytest.raises(ValidationError, match="Must be a PDF file"):
        OcrPdfPayload.model_validate({"files": [text_file]})


def test_ocr_payload_invalid_page_range() -> None:
    file_repr = make_pdf_file(PdfRestFileID.generate(1))
    with pytest.raises(
        ValidationError, match="The start page must be less than or equal to the end"
    ):
        OcrPdfPayload.model_validate({"files": [file_repr], "pages": ["5-2"]})


def test_ocr_payload_languages() -> None:
    file_repr = make_pdf_file(PdfRestFileID.generate(1))
    payload = OcrPdfPayload.model_validate(
        {"files": [file_repr], "languages": ["English", "German"]}
    )
    assert payload.languages == ["English", "German"]
    assert (
        payload.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude_unset=True
        )["languages"]
        == "English,German"
    )


def test_ocr_payload_invalid_language() -> None:
    file_repr = make_pdf_file(PdfRestFileID.generate(1))
    with pytest.raises(ValidationError, match="ChineseSimplified"):
        OcrPdfPayload.model_validate({"files": [file_repr], "languages": ["Klingon"]})


def test_ocr_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    payload_dump = OcrPdfPayload.model_validate(
        {
            "files": [input_file],
            "pages": ["1-3"],
            "output": "ocr",
            "languages": ["English"],
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    output_id = str(PdfRestFileID.generate())

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-ocr-text":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "inputId": str(input_file.id),
                    "outputId": output_id,
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=make_pdf_file(output_id, "ocr.pdf").model_dump(
                    mode="json", by_alias=True
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.ocr_pdf(
            input_file,
            pages=["1-3"],
            output="ocr",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.id == output_id
    assert response.output_file.name == "ocr.pdf"
    assert response.input_id == input_file.id


def test_ocr_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    payload_dump = OcrPdfPayload.model_validate(
        {"files": [input_file], "languages": ["English"]}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-ocr-text":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "sync"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump | {"debug": True}
            return httpx.Response(
                200,
                json={
                    "outputId": output_id,
                    "inputId": str(input_file.id),
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "sync"
            return httpx.Response(
                200,
                json=make_pdf_file(output_id, "custom-ocr.pdf").model_dump(
                    mode="json", by_alias=True
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.ocr_pdf(
            input_file,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"debug": True},
            timeout=0.4,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.id == output_id
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.4) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_async_ocr_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    payload_dump = OcrPdfPayload.model_validate(
        {"files": [input_file], "languages": ["English"]}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    output_id = str(PdfRestFileID.generate())

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-ocr-text":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "outputId": output_id,
                    "inputId": str(input_file.id),
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=make_pdf_file(output_id, "async-ocr.pdf").model_dump(
                    mode="json", by_alias=True
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.ocr_pdf(input_file)

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.id == output_id
    assert response.input_id == input_file.id
