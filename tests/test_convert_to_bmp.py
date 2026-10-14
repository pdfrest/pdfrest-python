from __future__ import annotations

import json
import re

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import BmpPdfRestPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    assert_conversion_payload,
    build_file_info_payload,
    make_pdf_file,
)
from .resources import get_test_resource_path

_TEST_PASSWORD = "open-sesame"  # noqa: S105 - Test-only password.


@pytest.mark.parametrize("color_model", ["rgb", "gray"])
def test_convert_to_bmp_success(
    monkeypatch: pytest.MonkeyPatch, color_model: str
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    expected_name = f"converted-{color_model}-001.bmp"

    request_payload = BmpPdfRestPayload.model_validate(
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
        if request.method == "POST" and request.url.path == "/bmp":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, expected_name, "image/bmp"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_bmp(
            input_file,
            output_prefix="converted",
            page_range=["1", "2-3"],
            resolution=600,
            password=_TEST_PASSWORD,
            color_model=color_model,  # type: ignore[arg-type]
            smoothing=["text", "image"],
        )

    assert seen == {"post": 1, "get": 1}
    output_file = response.output_files[0]
    assert output_file.name == expected_name
    assert output_file.type == "image/bmp"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert response.warning is None


def test_convert_to_bmp_defaults_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "2c3d4e5f-2345-4bcd-8ef0-abcdefabcdef"

    request_payload = BmpPdfRestPayload.model_validate(
        {"files": input_file}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/bmp":
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "example-001.bmp", "image/bmp"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_bmp(input_file)

    output_file = response.output_files[0]
    assert output_file.name == "example-001.bmp"
    assert output_file.type == "image/bmp"
    assert response.warning is None


@pytest.mark.parametrize("resolution", [12, 2400])
def test_convert_to_bmp_resolution_limits(
    monkeypatch: pytest.MonkeyPatch, resolution: int
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    request_payload = BmpPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "resolution": resolution,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/bmp":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, f"example-resolution-{resolution}.bmp", "image/bmp"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_bmp(
            input_file,
            resolution=resolution,
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == f"example-resolution-{resolution}.bmp"


@pytest.mark.parametrize("invalid_resolution", [11, 2401])
def test_convert_to_bmp_resolution_out_of_bounds(
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
        client.convert_to_bmp(
            make_pdf_file(PdfRestFileID.generate(1)),
            resolution=invalid_resolution,
        )


@pytest.mark.parametrize(
    "invalid_color",
    [
        pytest.param("rgba", id="rgba"),
        pytest.param("cmyk", id="cmyk"),
        pytest.param("lab", id="lab"),
    ],
)
def test_convert_to_bmp_invalid_color_models(
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
            match=re.escape("Input should be 'rgb' or 'gray'"),
        ),
    ):
        client.convert_to_bmp(
            make_pdf_file(PdfRestFileID.generate(1)),
            color_model=invalid_color,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_async_convert_to_bmp_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "3d4e5f60-3456-4cde-8f01-cdefabcdef12"

    request_payload = BmpPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "output_prefix": "async-output",
            "page_range": "1-2",
            "resolution": 450,
            "password": _TEST_PASSWORD,
            "color_model": "gray",
            "smoothing": ["all"],
        }
    ).model_dump(mode="json", by_alias=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/bmp":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
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
                    output_id, "async-output-001.bmp", "image/bmp"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_bmp(
            [input_file],
            output_prefix="async-output",
            page_range="1-2",
            resolution=450,
            password=_TEST_PASSWORD,
            color_model="gray",
            smoothing=["all"],
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    output_file = response.output_files[0]
    assert output_file.name == "async-output-001.bmp"
    assert output_file.type == "image/bmp"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert response.warning is None


def test_convert_to_bmp_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "4e5f6071-4567-4def-90ab-abcdefabcdef"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/bmp":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "bmp"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] is True
            assert payload["resolution"] == 500
            assert payload["id"] == str(input_file.id)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "bmp"
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "custom-001.bmp", "image/bmp"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_bmp(
            input_file,
            resolution=500,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "bmp"},
            extra_body={"debug": True},
            timeout=0.4,
        )

    assert response.output_files[0].name == "custom-001.bmp"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.4) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.4)


def test_convert_to_bmp_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
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
        client.convert_to_bmp(
            make_pdf_file(PdfRestFileID.generate(1)),
            resolution=5000,
        )


def test_convert_to_bmp_invalid_smoothing_value(
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
        client.convert_to_bmp(
            make_pdf_file(PdfRestFileID.generate(1)),
            smoothing="invalid",  # type: ignore[arg-type]
        )


def test_convert_to_bmp_multiple_files_rejected(
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
        client.convert_to_bmp([first, second])


def test_convert_to_bmp_empty_page_range_rejected(
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
        client.convert_to_bmp(
            make_pdf_file(PdfRestFileID.generate(1)),
            page_range=[],
        )


def test_convert_to_bmp_sequence_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "5f607182-5678-4ef0-91bc-cdefabcdef99"

    request_payload = BmpPdfRestPayload.model_validate(
        {
            "files": [input_file],
            "page_range": "1, 3",
            "smoothing": "text",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/bmp":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert_conversion_payload(payload, request_payload)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, "example-001.bmp", "image/bmp"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_to_bmp(
            [input_file],
            page_range="1, 3",
            smoothing="text",
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == "example-001.bmp"


@pytest.mark.asyncio
async def test_async_convert_to_bmp_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = "6a7b8c9d-6789-4012-a1b2-c3d4e5f6a7b8"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/bmp":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "async-bmp"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] is True
            assert payload["resolution"] == 475
            assert payload["id"] == str(input_file.id)
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "async-bmp"
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-custom-001.bmp", "image/bmp"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_to_bmp(
            input_file,
            resolution=475,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "async-bmp"},
            extra_body={"debug": True},
            timeout=0.55,
        )

    assert response.output_files[0].name == "async-custom-001.bmp"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.55) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.55)


def test_live_convert_to_bmp(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])
        response = client.convert_to_bmp(
            uploaded[0],
            output_prefix="live-bmp",
            page_range="1",
        )
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files


@pytest.mark.asyncio
async def test_live_async_convert_to_bmp(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = await client.files.create_from_paths([resource])
        response = await client.convert_to_bmp(
            uploaded[0],
            output_prefix="live-async-bmp",
            page_range="1",
        )
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files
