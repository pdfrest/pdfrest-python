from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfConvertColorsPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)


def _make_icc_file() -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "profile.icc",
            "application/vnd.iccprofile",
        )
    )


def test_convert_colors_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    payload_dump = PdfConvertColorsPayload.model_validate(
        {"files": [input_file], "color_profile": "srgb", "output": "converted"}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-converted-colors"
        ):
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
                    output_id,
                    "converted.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_colors(
            input_file, color_profile="srgb", output="converted"
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    output_file = response.output_file
    assert output_file.name == "converted.pdf"
    assert output_file.type == "application/pdf"
    assert response.warning is None
    assert str(response.input_id) == str(input_file.id)


def test_convert_colors_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    profile_file = _make_icc_file()
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-converted-colors"
        ):
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "sync"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] == "yes"
            assert payload["color_profile"] == "custom"
            assert payload["profile_id"] == str(profile_file.id)
            assert payload["preserve_black"] is True
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
            assert request.headers["X-Debug"] == "sync"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "custom.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_colors(
            input_file,
            color_profile="custom",
            profile=profile_file,
            preserve_black=True,
            output="custom",
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"debug": "yes"},
            timeout=0.29,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "custom.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.29) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.29)


@pytest.mark.asyncio
async def test_async_convert_colors_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())

    payload_dump = PdfConvertColorsPayload.model_validate(
        {"files": [input_file], "color_profile": "srgb"}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-converted-colors"
        ):
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
                    output_id,
                    "async.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_colors(input_file, color_profile="srgb")

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async.pdf"
    assert response.output_file.type == "application/pdf"
    assert str(response.input_id) == str(input_file.id)


@pytest.mark.asyncio
async def test_async_convert_colors_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    profile_file = _make_icc_file()
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-converted-colors"
        ):
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["debug"] == "yes"
            assert payload["color_profile"] == "custom"
            assert payload["profile_id"] == str(profile_file.id)
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-custom.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_colors(
            input_file,
            color_profile="custom",
            profile=profile_file,
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async"},
            extra_body={"debug": "yes"},
            timeout=0.52,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async-custom.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.52) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.52)


def test_convert_colors_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    png_file = PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "example.png",
            "image/png",
        )
    )
    wrong_profile_file = PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "profile.txt",
            "text/plain",
        )
    )
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Must be a PDF file"),
    ):
        client.convert_colors(png_file, color_profile="srgb")

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError, match="List should have at most 1 item after validation"
        ),
    ):
        client.convert_colors(
            [pdf_file, make_pdf_file(PdfRestFileID.generate())],
            color_profile="srgb",
        )

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValueError, match="requires a profile"),
    ):
        client.convert_colors(pdf_file, color_profile="custom")

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValueError, match="only be provided when color_profile"),
    ):
        client.convert_colors(pdf_file, color_profile="srgb", profile=_make_icc_file())

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Profile must be an ICC file"),
    ):
        client.convert_colors(
            pdf_file,
            color_profile="custom",
            profile=wrong_profile_file,
        )
