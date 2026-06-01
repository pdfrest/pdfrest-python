from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfToPdfaPayload
from pdfrest.types import PdfAType

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)


@pytest.mark.parametrize(
    "output_type",
    [
        pytest.param("PDF/A-1b", id="pdfa-1b"),
        pytest.param("PDF/A-2b", id="pdfa-2b"),
        pytest.param("PDF/A-2u", id="pdfa-2u"),
        pytest.param("PDF/A-3b", id="pdfa-3b"),
        pytest.param("PDF/A-3u", id="pdfa-3u"),
    ],
)
def test_convert_to_pdfa_success(
    monkeypatch: pytest.MonkeyPatch, output_type: PdfAType
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    payload_dump = PdfToPdfaPayload.model_validate(
        {
            "files": [input_file],
            "output_type": output_type,
            "output": "archive",
            "rasterize_if_errors_encountered": "off",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdfa":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "archive.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_pdfa(
            input_file,
            output_type=output_type,
            output="archive",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "archive.pdf"
    assert response.output_file.type == "application/pdf"
    assert str(response.input_id) == str(input_file.id)
    assert response.warning is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_type",
    [
        pytest.param("PDF/A-1b", id="pdfa-1b"),
        pytest.param("PDF/A-2b", id="pdfa-2b"),
        pytest.param("PDF/A-2u", id="pdfa-2u"),
        pytest.param("PDF/A-3b", id="pdfa-3b"),
        pytest.param("PDF/A-3u", id="pdfa-3u"),
    ],
)
async def test_async_convert_to_pdfa_success(
    monkeypatch: pytest.MonkeyPatch, output_type: PdfAType
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())
    payload_dump = PdfToPdfaPayload.model_validate(
        {
            "files": [input_file],
            "output_type": output_type,
            "rasterize_if_errors_encountered": "off",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdfa":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "async.pdf", "application/pdf"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_pdfa(
            input_file,
            output_type=output_type,
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async.pdf"
    assert response.output_file.type == "application/pdf"
    assert str(response.input_id) == str(input_file.id)


def test_convert_to_pdfa_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdfa":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "sync"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["output_type"] == "PDF/A-3b"
            assert payload["rasterize_if_errors_encountered"] == "on"
            assert payload["debug"] == "yes"
            assert payload["id"] == str(input_file.id)
            assert payload["output"] == "custom"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "sync"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "custom.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_pdfa(
            input_file,
            output_type="pdf/a-3b",
            output="custom",
            rasterize_if_errors_encountered="on",
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"debug": "yes"},
            timeout=0.33,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "custom.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.33) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.33)


@pytest.mark.asyncio
async def test_async_convert_to_pdfa_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdfa":
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["output_type"] == "PDF/A-2u"
            assert payload["id"] == str(input_file.id)
            assert payload["output"] == "async-custom"
            assert payload["extra"] == {"note": "async"}
            assert payload["rasterize_if_errors_encountered"] == "off"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-custom.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_pdfa(
            input_file,
            output_type="pdf/a-2u",
            output="async-custom",
            rasterize_if_errors_encountered="off",
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async"},
            extra_body={"extra": {"note": "async"}},
            timeout=0.72,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async-custom.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.72) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.72)


def test_convert_to_pdfa_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    png_file = PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "example.png",
            "image/png",
        )
    )
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=(
                "Input should be 'PDF/A-1b', 'PDF/A-2b', 'PDF/A-2u', "
                "'PDF/A-3b' or 'PDF/A-3u'"
            ),
        ),
    ):
        client.convert_to_pdfa(pdf_file, output_type=None)  # type: ignore[arg-type]

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Must be a PDF file"),
    ):
        client.convert_to_pdfa(png_file, output_type="PDF/A-2b")

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="PDF/A-1b"),
    ):
        client.convert_to_pdfa(pdf_file, output_type="PDF/A-4")  # type: ignore[arg-type]

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError, match="List should have at most 1 item after validation"
        ),
    ):
        client.convert_to_pdfa(
            [pdf_file, make_pdf_file(PdfRestFileID.generate())],
            output_type="PDF/A-2b",
        )


@pytest.mark.asyncio
async def test_async_convert_to_pdfa_validation(
    monkeypatch: pytest.MonkeyPatch,
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
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=(
                "Input should be 'PDF/A-1b', 'PDF/A-2b', 'PDF/A-2u', "
                "'PDF/A-3b' or 'PDF/A-3u'"
            ),
        ):
            await client.convert_to_pdfa(
                pdf_file,
                output_type=None,  # type: ignore[arg-type]
            )

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="Must be a PDF file"):
            await client.convert_to_pdfa(png_file, output_type="PDF/A-2b")

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="PDF/A-1b"):
            await client.convert_to_pdfa(
                pdf_file,
                output_type="PDF/A-4",  # type: ignore[arg-type]
            )

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError, match="List should have at most 1 item after validation"
        ):
            await client.convert_to_pdfa(
                [pdf_file, make_pdf_file(PdfRestFileID.generate())],
                output_type="PDF/A-2b",
            )
