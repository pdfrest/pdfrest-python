from __future__ import annotations

import json
from typing import Any, cast, get_args

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfConvertColorsPayload
from pdfrest.types import PdfPresetColorProfile, PdfRenderingIntent

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


ALL_COLOR_PROFILES: tuple[PdfPresetColorProfile, ...] = cast(
    tuple[PdfPresetColorProfile, ...],
    get_args(PdfPresetColorProfile),
)
ALL_RENDERING_INTENTS: tuple[PdfRenderingIntent, ...] = cast(
    tuple[PdfRenderingIntent, ...],
    get_args(PdfRenderingIntent),
)


@pytest.mark.parametrize(
    "rendering_intent",
    [
        pytest.param(rendering_intent, id=f"rendering-intent-{rendering_intent}")
        for rendering_intent in ALL_RENDERING_INTENTS
    ],
)
def test_convert_colors_payload_rendering_intent_serialization(
    rendering_intent: PdfRenderingIntent,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate(1))

    payload = PdfConvertColorsPayload.model_validate(
        {
            "files": input_file,
            "color_profile": "srgb",
            "rendering_intent": rendering_intent,
        }
    )

    assert payload.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    ) == {
        "id": str(input_file.id),
        "color_profile": "srgb",
        "rendering_intent": rendering_intent,
    }


@pytest.mark.parametrize(
    "color_profile",
    [
        pytest.param(color_profile, id=f"color-profile-{color_profile}")
        for color_profile in ALL_COLOR_PROFILES
    ],
)
def test_convert_colors_success(
    monkeypatch: pytest.MonkeyPatch,
    color_profile: PdfPresetColorProfile,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    payload_options: dict[str, Any] = {
        "files": [input_file],
        "color_profile": color_profile,
        "preserve_black": False,
        "output": "converted",
    }
    client_options: dict[str, Any] = {
        "color_profile": color_profile,
        "output": "converted",
    }

    payload_dump = PdfConvertColorsPayload.model_validate(payload_options).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )

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
        response = client.convert_colors(input_file, **client_options)

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    output_file = response.output_file
    assert output_file.name == "converted.pdf"
    assert output_file.type == "application/pdf"
    assert response.warning is None
    assert str(response.input_id) == str(input_file.id)


@pytest.mark.parametrize(
    "rendering_intent",
    [
        pytest.param(rendering_intent, id=f"rendering-intent-{rendering_intent}")
        for rendering_intent in ALL_RENDERING_INTENTS
    ],
)
def test_convert_colors_rendering_intents(
    monkeypatch: pytest.MonkeyPatch,
    rendering_intent: PdfRenderingIntent,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-converted-colors"
        ):
            seen["post"] += 1
            assert json.loads(request.content.decode("utf-8")) == {
                "id": str(input_file.id),
                "color_profile": "srgb",
                "preserve_black": "false",
                "rendering_intent": rendering_intent,
            }
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "rendering-intent.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.convert_colors(
            input_file,
            color_profile="srgb",
            rendering_intent=rendering_intent,
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_file.name == "rendering-intent.pdf"


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
            assert payload["preserve_black"] == "true"
            assert payload["rendering_intent"] == "perceptual"
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
            color_profile=profile_file,
            preserve_black=True,
            rendering_intent="perceptual",
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


@pytest.mark.parametrize(
    "color_profile",
    [
        pytest.param(color_profile, id=f"color-profile-{color_profile}")
        for color_profile in ALL_COLOR_PROFILES
    ],
)
@pytest.mark.asyncio
async def test_async_convert_colors_success(
    monkeypatch: pytest.MonkeyPatch,
    color_profile: PdfPresetColorProfile,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())

    payload_options: dict[str, Any] = {
        "files": [input_file],
        "color_profile": color_profile,
        "preserve_black": False,
    }
    client_options: dict[str, Any] = {"color_profile": color_profile}

    payload_dump = PdfConvertColorsPayload.model_validate(payload_options).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )

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
        response = await client.convert_colors(input_file, **client_options)

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async.pdf"
    assert response.output_file.type == "application/pdf"
    assert str(response.input_id) == str(input_file.id)


@pytest.mark.parametrize(
    "rendering_intent",
    [
        pytest.param(rendering_intent, id=f"rendering-intent-{rendering_intent}")
        for rendering_intent in ALL_RENDERING_INTENTS
    ],
)
@pytest.mark.asyncio
async def test_async_convert_colors_rendering_intents(
    monkeypatch: pytest.MonkeyPatch,
    rendering_intent: PdfRenderingIntent,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-converted-colors"
        ):
            seen["post"] += 1
            assert json.loads(request.content.decode("utf-8")) == {
                "id": str(input_file.id),
                "color_profile": "srgb",
                "preserve_black": "false",
                "rendering_intent": rendering_intent,
            }
            return httpx.Response(
                200,
                json={"inputId": [input_file.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-rendering-intent.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.convert_colors(
            input_file,
            color_profile="srgb",
            rendering_intent=rendering_intent,
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_file.name == "async-rendering-intent.pdf"


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
            assert payload["preserve_black"] == "false"
            assert payload["rendering_intent"] == "relative_colorimetric"
            assert payload["output"] == "async-custom"
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
            color_profile=profile_file,
            rendering_intent="relative_colorimetric",
            output="async-custom",
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
        pytest.raises(
            ValueError,
            match="A custom color profile requires an uploaded ICC file",
        ),
    ):
        client.convert_colors(pdf_file, color_profile=cast(Any, "custom"))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError, match="List should have at most 1 item after validation"
        ),
    ):
        client.convert_colors(
            pdf_file,
            color_profile=[_make_icc_file(), _make_icc_file()],
        )

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Profile must be an ICC file"),
    ):
        client.convert_colors(
            pdf_file,
            color_profile=wrong_profile_file,
        )


def test_convert_colors_payload_profile_dependency_validation() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))

    with pytest.raises(
        ValueError,
        match="A profile can only be provided by passing an uploaded ICC file",
    ):
        PdfConvertColorsPayload.model_validate(
            {
                "files": [pdf_file],
                "color_profile": "srgb",
                "custom_profile": _make_icc_file(),
            }
        )

    with pytest.raises(
        ValueError,
        match=r"Provide the custom profile file via color_profile only",
    ):
        PdfConvertColorsPayload.model_validate(
            {
                "files": [pdf_file],
                "color_profile": _make_icc_file(),
                "custom_profile": _make_icc_file(),
            }
        )


@pytest.mark.asyncio
async def test_async_convert_colors_validation(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="Must be a PDF file"):
            await client.convert_colors(png_file, color_profile="srgb")

        with pytest.raises(
            ValidationError, match="List should have at most 1 item after validation"
        ):
            await client.convert_colors(
                [pdf_file, make_pdf_file(PdfRestFileID.generate())],
                color_profile="srgb",
            )

        with pytest.raises(
            ValueError,
            match="A custom color profile requires an uploaded ICC file",
        ):
            await client.convert_colors(pdf_file, color_profile=cast(Any, "custom"))

        with pytest.raises(
            ValidationError, match="List should have at most 1 item after validation"
        ):
            await client.convert_colors(
                pdf_file,
                color_profile=[_make_icc_file(), _make_icc_file()],
            )

        with pytest.raises(ValidationError, match="Profile must be an ICC file"):
            await client.convert_colors(
                pdf_file,
                color_profile=wrong_profile_file,
            )


def test_convert_colors_rejects_invalid_color_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    invalid_color_profile = cast(Any, "not-a-color-profile")
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Input should be"),
    ):
        client.convert_colors(pdf_file, color_profile=invalid_color_profile)


@pytest.mark.asyncio
async def test_async_convert_colors_rejects_invalid_color_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    invalid_color_profile = cast(Any, "not-a-color-profile")
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="Input should be"):
            await client.convert_colors(pdf_file, color_profile=invalid_color_profile)


def test_convert_colors_rejects_invalid_rendering_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=r"(?s)rendering_intent.*Input should be",
        ),
    ):
        client.convert_colors(
            pdf_file,
            color_profile="srgb",
            rendering_intent=cast(Any, "not-an-intent"),
        )


@pytest.mark.asyncio
async def test_async_convert_colors_rejects_invalid_rendering_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(2))
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(RuntimeError))

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=r"(?s)rendering_intent.*Input should be",
        ):
            await client.convert_colors(
                pdf_file,
                color_profile="srgb",
                rendering_intent=cast(Any, "not-an-intent"),
            )
