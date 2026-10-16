from __future__ import annotations

import json
import re

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PngPdfRestPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    assert_conversion_payload,
    build_file_info_payload,
    make_pdf_file,
)

_TEST_PASSWORD = "open-sesame"  # noqa: S105 - Test-only password.


@pytest.mark.parametrize("color_model", ["rgb", "rgba", "gray"])
def test_convert_to_png_success(
    monkeypatch: pytest.MonkeyPatch, color_model: str
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    expected_name = f"converted-{color_model}-001.png"

    request_payload = PngPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "output_prefix": "converted",
            "page_range": ["1", "2-3"],
            "resolution": 600,
            "password": _TEST_PASSWORD,
            "color_model": color_model,
            "smoothing": ["text", "image"],
        }
    ).model_dump(mode="json", by_alias=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            seen["post"] += 1
            assert request.headers["wsn"] == "pdfrest-python"
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
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
                json=build_file_info_payload(output_id, expected_name, "image/png"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_png(
            input_file,
            output_prefix="converted",
            page_range=["1", "2-3"],
            resolution=600,
            password=_TEST_PASSWORD,
            color_model=color_model,  # type: ignore[arg-type]
            smoothing=["text", "image"],
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert len(response.output_files) == 1
    output_file = response.output_files[0]
    assert output_file.name == expected_name
    assert output_file.type == "image/png"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert str(response.input_id) == str(input_file.id)
    assert response.warning is None


def test_convert_to_png_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "9f4a9b10-3c55-4e6d-a111-1234567890ab"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] is True
            assert payload["resolution"] == 450
            assert payload["id"] == str(input_file.id)
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "custom-001.png", "image/png"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_png(
            input_file,
            resolution=450,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "1"},
            extra_body={"debug": True},
            timeout=0.25,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files[0].name == "custom-001.png"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.25) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.25)


@pytest.mark.parametrize("resolution", [12, 2400])
def test_convert_to_png_resolution_limits(
    monkeypatch: pytest.MonkeyPatch, resolution: int
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    request_payload = PngPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "resolution": resolution,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, f"example-resolution-{resolution}.png", "image/png"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_png(
            input_file,
            resolution=resolution,
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == f"example-resolution-{resolution}.png"


@pytest.mark.parametrize(
    "invalid_resolution",
    [11, 2401],
)
def test_convert_to_png_resolution_out_of_bounds(
    monkeypatch: pytest.MonkeyPatch, invalid_resolution: int
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=r"less than or equal to 2400|greater than or equal to 12",
        ),
    ):
        client.convert_to_png(
            make_pdf_file(PdfRestFileID.generate(1)),
            resolution=invalid_resolution,
        )


def test_convert_to_png_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="greater than or equal to 12"),
    ):
        client.convert_to_png(
            make_pdf_file(PdfRestFileID.generate(1)),
            resolution=5,
        )


@pytest.mark.asyncio
async def test_async_convert_to_png_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "2c134412-aaaa-4bbb-8ccc-dddddddddddd"

    request_payload = PngPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "output_prefix": "async-output",
            "page_range": "1-2",
            "resolution": 450,
            "password": _TEST_PASSWORD,
            "color_model": "rgb",
            "smoothing": ["all"],
        }
    ).model_dump(mode="json", by_alias=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
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
                    output_id, "async-output-001.png", "image/png"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_png(
            [input_file],
            output_prefix="async-output",
            page_range="1-2",
            resolution=450,
            password=_TEST_PASSWORD,
            color_model="rgb",
            smoothing=["all"],
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    output_file = response.output_files[0]
    assert output_file.name == "async-output-001.png"
    assert output_file.name.startswith("async-output")
    assert output_file.type == "image/png"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert str(response.input_id) == str(input_file.id)
    assert response.warning is None


@pytest.mark.asyncio
async def test_async_convert_to_png_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "abcdb5f9-1234-4c67-98ef-abcdefabcdef"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "async"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] is True
            assert payload["resolution"] == 500
            assert payload["id"] == str(input_file.id)
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-custom-001.png", "image/png"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_png(
            input_file,
            resolution=500,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "async"},
            extra_body={"debug": True},
            timeout=0.6,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files[0].name == "async-custom-001.png"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.6) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_async_convert_to_png_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="less than or equal to 2400"):
            await client.convert_to_png(
                make_pdf_file(PdfRestFileID.generate(1)),
                resolution=9000,
            )


def test_convert_to_png_sequence_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "1f9c6d0a-5ec4-4f6c-b1f2-bbbbbbbbbbbb"

    request_payload = PngPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "page_range": "1, 3",
            "smoothing": "text",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "example-001.png", "image/png"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_png(
            [input_file],
            page_range="1, 3",
            smoothing="text",
        )

    assert seen == {"post": 1, "get": 1}
    output_file = response.output_files[0]
    assert output_file.name == "example-001.png"
    assert output_file.name.startswith("example")
    assert output_file.type == "image/png"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert response.warning is None


def test_convert_to_png_defaults_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "2ab0c1d2-3e4f-4a5b-8c9d-dddddddddddd"

    request_payload = PngPdfRestPayload.model_validate(
        {
            "files": input_file,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/png":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "example-001.png", "image/png"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_png(input_file)

    assert seen == {"post": 1, "get": 1}
    output_file = response.output_files[0]
    assert output_file.name == "example-001.png"
    assert output_file.name.startswith("example")
    assert output_file.type == "image/png"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert response.warning is None


@pytest.mark.parametrize(
    "invalid_color",
    [pytest.param("cmyk", id="cmyk"), pytest.param("lab", id="lab")],
)
def test_convert_to_png_invalid_color_model(
    monkeypatch: pytest.MonkeyPatch, invalid_color: str
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=re.escape("Input should be 'rgb', 'rgba' or 'gray'"),
        ),
    ):
        client.convert_to_png(
            make_pdf_file(PdfRestFileID.generate(1)),
            color_model=invalid_color,  # type: ignore[arg-type]
        )


def test_convert_to_png_invalid_smoothing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=re.escape("Input should be 'none', 'all', 'text', 'line' or 'image'"),
        ),
    ):
        client.convert_to_png(
            make_pdf_file(PdfRestFileID.generate(1)),
            smoothing="invalid",  # type: ignore[arg-type]
        )


def test_convert_to_png_multiple_files_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    first = make_pdf_file(PdfRestFileID.generate(1))
    second = make_pdf_file(PdfRestFileID.generate(1))
    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=re.escape("List should have at most 1 item after validation"),
        ),
    ):
        client.convert_to_png([first, second])


def test_convert_to_png_empty_page_range_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=re.escape("List should have at least 1 item after validation"),
        ),
    ):
        client.convert_to_png(
            make_pdf_file(PdfRestFileID.generate(1)),
            page_range=[],
        )
