from __future__ import annotations

import json
import re

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import JpegPdfRestPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    assert_conversion_payload,
    build_file_info_payload,
    make_pdf_file,
)
from .resources import get_test_resource_path

_TEST_PASSWORD = "open-sesame"  # noqa: S105 - Test-only password.


@pytest.mark.parametrize("color_model", ["rgb", "cmyk", "gray"])
def test_convert_to_jpeg_success(
    monkeypatch: pytest.MonkeyPatch, color_model: str
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    expected_name = f"converted-{color_model}-001.jpg"

    request_payload = JpegPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "output_prefix": "converted",
            "page_range": ["1", "2-3"],
            "resolution": 450,
            "password": _TEST_PASSWORD,
            "color_model": color_model,
            "jpeg_quality": 90,
            "smoothing": ["text", "image"],
        }
    ).model_dump(mode="json", by_alias=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(
                payload, request_payload, allowed_extras={"jpeg_quality"}
            )
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, expected_name, "image/jpeg"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_jpeg(
            input_file,
            output_prefix="converted",
            page_range=["1", "2-3"],
            resolution=450,
            password=_TEST_PASSWORD,
            color_model=color_model,  # type: ignore[arg-type]
            smoothing=["text", "image"],
            jpeg_quality=90,
        )

    assert seen == {"post": 1, "get": 1}
    output_file = response.output_files[0]
    assert output_file.name == expected_name
    assert output_file.type == "image/jpeg"
    assert str(output_file.url).endswith(output_id)


def test_convert_to_jpeg_defaults_included(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "8e9f0011-2222-4bcd-9f00-abcdefabcdef"

    request_payload = JpegPdfRestPayload.model_validate(
        {"files": input_file}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(
                payload, request_payload, allowed_extras={"jpeg_quality"}
            )
            assert payload["jpeg_quality"] == 75
            assert payload["resolution"] == 300
            assert payload["color_model"] == "rgb"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "example-001.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_jpeg(input_file)

    output_file = response.output_files[0]
    assert output_file.name == "example-001.jpg"
    assert output_file.type == "image/jpeg"


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_defaults_included(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "8e9f0011-2222-4bcd-9f00-abcdefabcdef"

    request_payload = JpegPdfRestPayload.model_validate(
        {"files": input_file}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(
                payload, request_payload, allowed_extras={"jpeg_quality"}
            )
            assert payload["jpeg_quality"] == 75
            assert payload["resolution"] == 300
            assert payload["color_model"] == "rgb"
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "example-001.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_jpeg(input_file)

    output_file = response.output_files[0]
    assert output_file.name == "example-001.jpg"
    assert output_file.type == "image/jpeg"


@pytest.mark.parametrize("resolution", [12, 2400])
def test_convert_to_jpeg_resolution_limits(
    monkeypatch: pytest.MonkeyPatch, resolution: int
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    request_payload = JpegPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "resolution": resolution,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(
                payload, request_payload, allowed_extras={"jpeg_quality"}
            )
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, f"example-resolution-{resolution}.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_jpeg(
            input_file,
            resolution=resolution,
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == f"example-resolution-{resolution}.jpg"


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", [12, 2400])
async def test_async_convert_to_jpeg_resolution_limits(
    monkeypatch: pytest.MonkeyPatch, resolution: int
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    request_payload = JpegPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "resolution": resolution,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(
                payload, request_payload, allowed_extras={"jpeg_quality"}
            )
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, f"example-resolution-{resolution}.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_jpeg(
            input_file,
            resolution=resolution,
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == f"example-resolution-{resolution}.jpg"


@pytest.mark.parametrize("invalid_resolution", [11, 2401])
def test_convert_to_jpeg_resolution_out_of_bounds(
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
        client.convert_to_jpeg(
            make_pdf_file(PdfRestFileID.generate(1)),
            resolution=invalid_resolution,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_resolution", [11, 2401])
async def test_async_convert_to_jpeg_resolution_out_of_bounds(
    monkeypatch: pytest.MonkeyPatch, invalid_resolution: int
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=r"less than or equal to 2400|greater than or equal to 12",
        ):
            await client.convert_to_jpeg(
                make_pdf_file(PdfRestFileID.generate(1)),
                resolution=invalid_resolution,
            )


@pytest.mark.parametrize(
    "invalid_color",
    [pytest.param("rgba", id="rgba"), pytest.param("lab", id="lab")],
)
def test_convert_to_jpeg_invalid_color_model(
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
            match=re.escape("Input should be 'rgb', 'cmyk' or 'gray'"),
        ),
    ):
        client.convert_to_jpeg(
            make_pdf_file(PdfRestFileID.generate(1)),
            color_model=invalid_color,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_color",
    [pytest.param("rgba", id="rgba"), pytest.param("lab", id="lab")],
)
async def test_async_convert_to_jpeg_invalid_color_model(
    monkeypatch: pytest.MonkeyPatch, invalid_color: str
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("Input should be 'rgb', 'cmyk' or 'gray'"),
        ):
            await client.convert_to_jpeg(
                make_pdf_file(PdfRestFileID.generate(1)),
                color_model=invalid_color,  # type: ignore[arg-type]
            )


def test_convert_to_jpeg_invalid_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=re.escape("Input should be greater than or equal to 1"),
        ),
    ):
        client.convert_to_jpeg(
            make_pdf_file(PdfRestFileID.generate(1)),
            jpeg_quality=0,
        )


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_invalid_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("Input should be greater than or equal to 1"),
        ):
            await client.convert_to_jpeg(
                make_pdf_file(PdfRestFileID.generate(1)),
                jpeg_quality=0,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "color_model",
    [
        pytest.param("rgb", id="rgb"),
        pytest.param("cmyk", id="cmyk"),
        pytest.param("gray", id="gray"),
    ],
)
async def test_async_convert_to_jpeg_success(
    monkeypatch: pytest.MonkeyPatch, color_model: str
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "9f001122-3333-4cde-af01-cdefabcdef12"

    request_payload = JpegPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "output_prefix": "async-output",
            "page_range": "1-2",
            "resolution": 500,
            "password": _TEST_PASSWORD,
            "color_model": color_model,
            "jpeg_quality": 85,
            "smoothing": ["all"],
        }
    ).model_dump(mode="json", by_alias=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(
                payload, request_payload, allowed_extras={"jpeg_quality"}
            )
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
                    output_id, "async-output-001.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_jpeg(
            [input_file],
            output_prefix="async-output",
            page_range="1-2",
            resolution=500,
            password=_TEST_PASSWORD,
            color_model=color_model,
            smoothing=["all"],
            jpeg_quality=85,
        )

    assert seen == {"post": 1, "get": 1}
    output_file = response.output_files[0]
    assert output_file.name == "async-output-001.jpg"
    assert output_file.type == "image/jpeg"


def test_convert_to_jpeg_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "abcdef01-4444-4def-9012-bbbbbbbbbbbb"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "jpeg"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] is True
            assert payload["resolution"] == 475
            assert payload["jpeg_quality"] == 82
            assert payload["id"] == str(input_file.id)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.url.params["format"] == "info"
            assert request.headers["X-Debug"] == "jpeg"
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "custom-001.jpg", "image/jpeg"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_jpeg(
            input_file,
            resolution=475,
            color_model="rgb",
            jpeg_quality=82,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "jpeg"},
            extra_body={"debug": True},
            timeout=0.42,
        )

    assert response.output_files[0].name == "custom-001.jpg"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.42) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.42)


def test_convert_to_jpeg_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match="less than or equal to 2400",
        ),
    ):
        client.convert_to_jpeg(
            make_pdf_file(PdfRestFileID.generate(1)),
            resolution=5000,
        )


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match="less than or equal to 2400",
        ):
            await client.convert_to_jpeg(
                make_pdf_file(PdfRestFileID.generate(1)),
                resolution=5000,
            )


def test_convert_to_jpeg_invalid_smoothing_value(
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
        client.convert_to_jpeg(
            make_pdf_file(PdfRestFileID.generate(1)),
            smoothing="invalid",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_invalid_smoothing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("Input should be 'none', 'all', 'text', 'line' or 'image'"),
        ):
            await client.convert_to_jpeg(
                make_pdf_file(PdfRestFileID.generate(1)),
                smoothing="invalid",  # type: ignore[arg-type]
            )


def test_convert_to_jpeg_multiple_files_rejected(
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
        client.convert_to_jpeg([first, second])


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_multiple_files_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    first = make_pdf_file(PdfRestFileID.generate(1))
    second = make_pdf_file(PdfRestFileID.generate(1))
    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("List should have at most 1 item after validation"),
        ):
            await client.convert_to_jpeg([first, second])


def test_convert_to_jpeg_empty_page_range_rejected(
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
        client.convert_to_jpeg(
            make_pdf_file(PdfRestFileID.generate(1)),
            page_range=[],
        )


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_empty_page_range_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("List should have at least 1 item after validation"),
        ):
            await client.convert_to_jpeg(
                make_pdf_file(PdfRestFileID.generate(1)),
                page_range=[],
            )


def test_convert_to_jpeg_sequence_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "cdef0123-5555-4ab0-9123-dededededede"

    request_payload = JpegPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "page_range": "1, 3",
            "smoothing": "text",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload, allowed_extras=set())
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "example-001.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_jpeg(
            [input_file],
            page_range="1, 3",
            smoothing="text",
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == "example-001.jpg"


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_sequence_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "cdef0123-7777-4ab0-9123-aaaaaaaabbbb"

    request_payload = JpegPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "page_range": "1, 3",
            "smoothing": "text",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload, allowed_extras=set())
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "example-async-001.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_jpeg(
            [input_file],
            page_range="1, 3",
            smoothing="text",
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == "example-async-001.jpg"


@pytest.mark.asyncio
async def test_async_convert_to_jpeg_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "def01234-6666-4bc1-9234-eeeeeeeeeeee"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/jpg":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "async-jpeg"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] is True
            assert payload["resolution"] == 440
            assert payload["jpeg_quality"] == 88
            assert payload["id"] == str(input_file.id)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "async-jpeg"
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-custom-001.jpg", "image/jpeg"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_jpeg(
            input_file,
            resolution=440,
            color_model="gray",
            jpeg_quality=88,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "async-jpeg"},
            extra_body={"debug": True},
            timeout=0.51,
        )

    assert response.output_files[0].name == "async-custom-001.jpg"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.51) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.51)


def test_live_convert_to_jpeg(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])
        response = client.convert_to_jpeg(
            uploaded[0],
            output_prefix="live-jpeg",
            page_range="1",
        )
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files


@pytest.mark.asyncio
async def test_live_async_convert_to_jpeg(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = await client.files.create_from_paths([resource])
        response = await client.convert_to_jpeg(
            uploaded[0],
            output_prefix="live-async-jpeg",
            page_range="1",
        )
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files
