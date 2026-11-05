from __future__ import annotations

import json
import re

import httpx
import pytest
from pydantic import ValidationError
from pydantic_core import to_json

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfAddTextPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_image_file,
    make_pdf_file,
)


def make_text_object(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "font": "courier",
        "max_width": 200,
        "opacity": 0.75,
        "page": 1,
        "rotation": 0,
        "text": "Hello, PDF!",
        "text_color_rgb": (0, 0, 0),
        "text_size": 12,
        "x": 72,
        "y": 144,
    }
    base.update(overrides)
    return base


def _serialize_text_object_for_request(
    text_object: dict[str, object],
) -> dict[str, object]:
    serialized = dict(text_object)
    # PdfAddTextObjectModel defines these fields as floats, so Pydantic serializes
    # integer inputs as 200.0/45.0/etc. Mirror that to keep wire assertions exact.
    for key in ("max_width", "rotation", "text_size", "x", "y"):
        value = serialized.get(key)
        if isinstance(value, int):
            serialized[key] = float(value)
    rgb = serialized.get("text_color_rgb")
    if isinstance(rgb, (list, tuple)):
        serialized["text_color_rgb"] = ",".join(str(channel) for channel in rgb)
    cmyk = serialized.get("text_color_cmyk")
    if isinstance(cmyk, (list, tuple)):
        serialized["text_color_cmyk"] = ",".join(str(channel) for channel in cmyk)
    if "is_right_to_left" in serialized:
        serialized["is_rtl"] = serialized.pop("is_right_to_left")
    # Add-text payloads now quote non-string values inside the text_objects JSON.
    for key, value in list(serialized.items()):
        if not isinstance(value, str):
            serialized[key] = to_json(value).decode()
    return serialized


@pytest.mark.parametrize(
    ("tag_language", "expected_language"),
    [
        pytest.param("en", "en", id="language"),
        pytest.param("EN-us", "EN-us", id="region"),
        pytest.param("zh-hant", "zh-hant", id="script"),
        pytest.param("es-419", "es-419", id="numeric-region"),
        pytest.param("eng-US", "eng-US", id="alpha3-language"),
        pytest.param("zz", "zz", id="service-compatible-language"),
        pytest.param("en-AB", "en-AB", id="service-compatible-region"),
    ],
)
def test_add_text_payload_serializes_tag_controls(
    tag_language: str,
    expected_language: str,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    text_object = make_text_object()

    payload = PdfAddTextPayload.model_validate(
        {
            "files": pdf_file,
            "text_objects": text_object,
            "tag_enabled": True,
            "tag_language": tag_language,
            "output": "tagged-text",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert payload == {
        "id": str(pdf_file.id),
        "text_objects": to_json(
            [_serialize_text_object_for_request(text_object)]
        ).decode(),
        "tag_enabled": True,
        "tag_language": expected_language,
        "output": "tagged-text",
    }


def test_add_text_payload_omits_unspecified_tag_controls() -> None:
    payload = PdfAddTextPayload.model_validate(
        {
            "files": make_pdf_file(PdfRestFileID.generate(1)),
            "text_objects": make_text_object(),
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert "tag_enabled" not in payload
    assert "tag_language" not in payload


def test_add_text_payload_omits_explicit_none_tag_controls() -> None:
    payload = PdfAddTextPayload.model_validate(
        {
            "files": make_pdf_file(PdfRestFileID.generate(1)),
            "text_objects": make_text_object(),
            "tag_enabled": None,
            "tag_language": None,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert "tag_enabled" not in payload
    assert "tag_language" not in payload


@pytest.mark.parametrize(
    "tag_language",
    [
        pytest.param("", id="empty"),
        pytest.param("e", id="short-language"),
        pytest.param("english", id="long-language"),
        pytest.param("en_US", id="underscore"),
        pytest.param("en-Latn-US", id="multiple-subtags"),
    ],
)
def test_add_text_payload_rejects_invalid_tag_language(tag_language: str) -> None:
    with pytest.raises(
        ValidationError,
        match="tag_language must be a valid BCP 47 language tag",
    ):
        PdfAddTextPayload.model_validate(
            {
                "files": make_pdf_file(PdfRestFileID.generate(1)),
                "text_objects": make_text_object(),
                "tag_enabled": True,
                "tag_language": tag_language,
            }
        )


def test_add_text_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-text":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {
                "id": str(pdf_file.id),
                "text_objects": to_json(
                    [
                        _serialize_text_object_for_request(
                            make_text_object(is_right_to_left=True)
                        )
                    ]
                ).decode(),
                "output": "with-text",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "with-text.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_text_to_pdf(
            pdf_file,
            text_objects=[make_text_object(is_right_to_left=True)],
            output="with-text",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "with-text.pdf"
    assert response.output_file.type == "application/pdf"
    assert str(pdf_file.id) in [str(file_id) for file_id in response.input_ids]
    assert response.warning is None


def test_add_text_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}
    overridden_text_object = make_text_object(page=2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-text":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["rotation"] == 15
            assert payload["tag_enabled"] is True
            assert payload["tag_language"] == "es-419"
            assert (
                payload["text_objects"]
                == to_json(
                    [_serialize_text_object_for_request(overridden_text_object)],
                ).decode()
            )
            captured_timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "custom-text.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_text_to_pdf(
            pdf_file,
            text_objects=[make_text_object(rotation=15)],
            tag_enabled=True,
            tag_language="es-419",
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "1"},
            extra_body={
                "rotation": 15,
                "text_objects": to_json(
                    [_serialize_text_object_for_request(overridden_text_object)],
                ).decode(),
            },
            timeout=0.25,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files[0].name == "custom-text.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.25) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.25)


def test_add_text_to_pdf_requires_tagging_for_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(
            ValidationError,
            match=re.escape("tag_enabled must be true when tag options are provided."),
        ),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=make_text_object(),
            tag_language="en-US",
        )


def test_add_text_to_pdf_rejects_invalid_tag_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(
            ValidationError,
            match="tag_language must be a valid BCP 47 language tag",
        ),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=make_text_object(),
            tag_enabled=True,
            tag_language="en-Latn-US",
        )


def test_add_text_to_pdf_requires_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    text_object = make_text_object()
    text_object.pop("text_color_rgb")

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match=re.escape(
                "Either text_color_rgb or text_color_cmyk must be provided."
            ),
        ),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=[text_object],
        )


def test_add_text_to_pdf_pdf_mime_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Must be a PDF file"),
    ):
        client.add_text_to_pdf(
            make_image_file(PdfRestFileID.generate(1)),
            text_objects=[make_text_object()],
        )


def test_add_text_to_pdf_page_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="greater than or equal to 1"),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=[make_text_object(page=0)],
        )


def test_add_text_to_pdf_rejects_both_color_modes(
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
            match=re.escape("Provide only one of text_color_rgb or text_color_cmyk."),
        ),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=[make_text_object(text_color_cmyk=(0, 0, 0, 0))],
        )


def test_add_text_to_pdf_rgb_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError,
            match="less than or equal to 255",
        ),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=[make_text_object(text_color_rgb=(0, 0, 256))],
        )


def test_add_text_to_pdf_text_size_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="greater than or equal to 5"),
    ):
        client.add_text_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            text_objects=[make_text_object(text_size=4)],
        )


def test_add_text_to_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="at most 1 item"),
    ):
        client.add_text_to_pdf(
            [
                make_pdf_file(PdfRestFileID.generate(1)),
                make_pdf_file(PdfRestFileID.generate(2)),
            ],
            text_objects=[make_text_object()],
        )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-text":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {
                "id": str(pdf_file.id),
                "text_objects": to_json(
                    [
                        _serialize_text_object_for_request(
                            make_text_object(page="all", is_right_to_left=True)
                        )
                    ]
                ).decode(),
                "output": "async-with-text",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-with-text.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_text_to_pdf(
            pdf_file,
            text_objects=[make_text_object(page="all", is_right_to_left=True)],
            output="async-with-text",
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == "async-with-text.pdf"


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}
    overridden_text_object = make_text_object(page=3)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-text":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Test"] == "async"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["text_size"] == 18
            assert payload["tag_enabled"] is True
            assert payload["tag_language"] == "es-419"
            assert (
                payload["text_objects"]
                == to_json(
                    [_serialize_text_object_for_request(overridden_text_object)],
                ).decode()
            )
            captured_timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Test"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-custom-text.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_text_to_pdf(
            pdf_file,
            text_objects=[make_text_object(text_size=18)],
            tag_enabled=True,
            tag_language="es-419",
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "async"},
            extra_body={
                "text_size": 18,
                "text_objects": to_json(
                    [_serialize_text_object_for_request(overridden_text_object)],
                ).decode(),
            },
            timeout=1.0,
        )

    assert response.output_files[0].name == "async-custom-text.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(1.0) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_requires_tagging_for_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("tag_enabled must be true when tag options are provided."),
        ):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=make_text_object(),
                tag_enabled=False,
                tag_language="en-US",
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_rejects_invalid_tag_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            ValidationError,
            match="tag_language must be a valid BCP 47 language tag",
        ):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=make_text_object(),
                tag_enabled=True,
                tag_language="en_US",
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_invalid_cmyk_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match="less than or equal to 100",
        ):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=[
                    make_text_object(
                        text_color_rgb=None, text_color_cmyk=(0, 0, 0, 101)
                    )
                ],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_pdf_mime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="Must be a PDF file"):
            await client.add_text_to_pdf(
                make_image_file(PdfRestFileID.generate(1)),
                text_objects=[make_text_object()],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_page_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=[make_text_object(page=0)],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_rejects_both_color_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape("Provide only one of text_color_rgb or text_color_cmyk."),
        ):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=[make_text_object(text_color_cmyk=(0, 0, 0, 0))],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_requires_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    text_object = make_text_object()
    text_object.pop("text_color_rgb")

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match=re.escape(
                "Either text_color_rgb or text_color_cmyk must be provided."
            ),
        ):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=[text_object],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_rgb_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError,
            match="less than or equal to 255",
        ):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=[make_text_object(text_color_rgb=(0, 0, 256))],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_text_size_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="greater than or equal to 5"):
            await client.add_text_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                text_objects=[make_text_object(text_size=4)],
            )


@pytest.mark.asyncio
async def test_async_add_text_to_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="at most 1 item"):
            await client.add_text_to_pdf(
                [
                    make_pdf_file(PdfRestFileID.generate(1)),
                    make_pdf_file(PdfRestFileID.generate(2)),
                ],
                text_objects=[make_text_object()],
            )
