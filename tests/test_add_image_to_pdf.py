from __future__ import annotations

import json
import re
from typing import cast, get_args

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfAddImagePayload, PdfAddImagesPayload
from pdfrest.types import PdfAddImageObject, PdfContentStructureType

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_image_file,
    make_pdf_file,
)

IMAGE_MIME_VARIANTS = (
    pytest.param("image/jpeg", "logo.jpg", id="jpeg"),
    pytest.param("image/png", "logo.png", id="png"),
    pytest.param("image/tiff", "logo.tif", id="tiff"),
    pytest.param("image/gif", "logo.gif", id="gif"),
)

CONTENT_STRUCTURE_TYPE_CASES = tuple(
    pytest.param(value, id=value) for value in get_args(PdfContentStructureType)
)


@pytest.mark.parametrize(("image_mime_type", "image_name"), IMAGE_MIME_VARIANTS)
def test_add_image_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
    image_mime_type: str,
    image_name: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(
        PdfRestFileID.generate(2),
        mime_type=image_mime_type,
        name=image_name,
    )
    output_id = str(PdfRestFileID.generate())

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-image":
            seen["post"] += 1
            assert request.headers["wsn"] == "pdfrest-python"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["id"] == str(pdf_file.id)
            assert payload["image_id"] == str(image_file.id)
            assert payload["x"] == 12
            assert payload["y"] == 34
            assert payload["page"] == 3
            assert payload["output"] == "with-image"
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id, image_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "with-image.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_image_to_pdf(
            pdf_file,
            image=image_file,
            x=12,
            y=34,
            page=3,
            output="with-image",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert len(response.input_ids) == 2
    assert pdf_file.id in response.input_ids
    assert image_file.id in response.input_ids
    output_file = response.output_file
    assert output_file.name == "with-image.pdf"
    assert output_file.type == "application/pdf"
    assert output_file.size == 256
    assert str(output_file.url).endswith(output_id)
    assert response.warning is None


def test_add_image_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    output_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-image":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["x"] == 100
            assert payload["y"] == 200
            assert payload["page"] == 1
            assert payload["id"] == str(pdf_file.id)
            assert payload["image_id"] == str(image_file.id)
            captured_timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id, image_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "custom-with-image.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_image_to_pdf(
            pdf_file,
            image=image_file,
            x=100,
            y=200,
            page=1,
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "1"},
            extra_body={"page": 1},
            timeout=0.5,
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files[0].name == "custom-with-image.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.5) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.5)


def test_add_image_to_pdf_pdf_mime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Must be a PDF file"),
    ):
        client.add_image_to_pdf(
            make_image_file(PdfRestFileID.generate(1)),
            image=make_image_file(PdfRestFileID.generate(2)),
            x=1,
            y=2,
            page=1,
        )


def test_add_image_to_pdf_image_mime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(
            ValidationError, match=re.escape("Image must be JPEG, PNG, TIFF, or GIF")
        ),
    ):
        client.add_image_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image=make_pdf_file(PdfRestFileID.generate(2)),
            x=1,
            y=2,
            page=1,
        )


def test_add_image_to_pdf_page_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="greater than or equal to 1"),
    ):
        client.add_image_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image=make_image_file(PdfRestFileID.generate(2)),
            x=0,
            y=0,
            page=0,
        )


def test_add_image_to_pdf_rejects_multiple_input_files(
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
        client.add_image_to_pdf(
            [
                make_pdf_file(PdfRestFileID.generate(1)),
                make_pdf_file(PdfRestFileID.generate(2)),
            ],
            image=make_image_file(PdfRestFileID.generate(2)),
            x=1,
            y=1,
            page=1,
        )


def test_add_image_to_pdf_rejects_multiple_images(
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
        client.add_image_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image=[
                make_image_file(PdfRestFileID.generate(2)),
                make_image_file(PdfRestFileID.generate(2), name="secondary.png"),
            ],
            x=1,
            y=1,
            page=1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("image_mime_type", "image_name"), IMAGE_MIME_VARIANTS)
async def test_async_add_image_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
    image_mime_type: str,
    image_name: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(
        PdfRestFileID.generate(2),
        mime_type=image_mime_type,
        name=image_name,
    )
    output_id = str(PdfRestFileID.generate())

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-image":
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["id"] == str(pdf_file.id)
            assert payload["image_id"] == str(image_file.id)
            assert payload["x"] == 5
            assert payload["y"] == 6
            assert payload["page"] == 7
            assert payload["output"] == "async-with-image"
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id, image_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-with-image.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_image_to_pdf(
            pdf_file,
            image=image_file,
            x=5,
            y=6,
            page=7,
            output="async-with-image",
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_files[0].name == "async-with-image.pdf"
    assert len(response.input_ids) == 2


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-image":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Test"] == "async"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["x"] == 15
            assert payload["y"] == 25
            captured_timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id, image_file.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Test"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-custom-with-image.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_image_to_pdf(
            pdf_file,
            image=image_file,
            x=15,
            y=25,
            page=1,
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "async"},
            extra_body={"x": 15},
            timeout=1.0,
        )

    assert response.output_files[0].name == "async-custom-with-image.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(1.0) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_invalid_image_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(
            ValidationError, match=re.escape("Image must be JPEG, PNG, TIFF, or GIF")
        ):
            await client.add_image_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image=make_pdf_file(PdfRestFileID.generate(2)),
                x=1,
                y=1,
                page=1,
            )


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_invalid_pdf_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="Must be a PDF file"):
            await client.add_image_to_pdf(
                make_image_file(PdfRestFileID.generate(1)),
                image=make_image_file(PdfRestFileID.generate(2)),
                x=1,
                y=2,
                page=1,
            )


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_page_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            await client.add_image_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image=make_image_file(PdfRestFileID.generate(2)),
                x=0,
                y=0,
                page=0,
            )


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="at most 1 item"):
            await client.add_image_to_pdf(
                [
                    make_pdf_file(PdfRestFileID.generate(1)),
                    make_pdf_file(PdfRestFileID.generate(2)),
                ],
                image=make_image_file(PdfRestFileID.generate(2)),
                x=1,
                y=1,
                page=1,
            )


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_rejects_multiple_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        with pytest.raises(ValidationError, match="at most 1 item"):
            await client.add_image_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image=[
                    make_image_file(PdfRestFileID.generate(2)),
                    make_image_file(PdfRestFileID.generate(2), name="secondary.png"),
                ],
                x=1,
                y=1,
                page=1,
            )


def _assert_timeout(timeout: object, expected: float) -> None:
    assert timeout is not None
    if isinstance(timeout, dict):
        assert all(
            component == pytest.approx(expected) for component in timeout.values()
        )
    else:
        assert timeout == pytest.approx(expected)


def test_add_image_payload_serializes_size_and_tagging() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))

    body = PdfAddImagePayload.model_validate(
        {
            "file": pdf_file,
            "image": image_file,
            "x": -12,
            "y": 34,
            "page": 2,
            "width": 144,
            "height": 72,
            "tag_enabled": True,
            "tag_language": "en-US",
            "tag_alt_text": "Company logo",
            "tag_is_artifact": False,
            "tag_structure_type": "Figure",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert body == {
        "id": str(pdf_file.id),
        "image_id": str(image_file.id),
        "x": -12,
        "y": 34,
        "page": 2,
        "width": 144.0,
        "height": 72.0,
        "tag_enabled": True,
        "tag_language": "en-US",
        "tag_alt_text": "Company logo",
        "tag_is_artifact": False,
        "tag_structure_type": "Figure",
    }


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        pytest.param(1, 1, id="integer"),
        pytest.param("1", "1", id="numeric-string"),
        pytest.param("all", "all", id="all"),
        pytest.param("last", "last", id="last"),
        pytest.param("2-4,6-last", "2-4,6-last", id="combined-ranges"),
        pytest.param(" 2 , 4-7 , LAST ", "2,4-7,last", id="normalized"),
    ],
)
def test_add_images_payload_page_selectors(
    page: int | str, expected: int | str
) -> None:
    image_file = make_image_file(PdfRestFileID.generate(2))
    payload = PdfAddImagesPayload.model_validate(
        {
            "file": make_pdf_file(PdfRestFileID.generate(1)),
            "image_objects": {
                "image": image_file,
                "page": page,
                "x": 0,
                "y": 0,
            },
        }
    )

    body = payload.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )
    assert body["image_objects"][0]["page"] == expected


def test_add_images_payload_serializes_single_and_reused_images() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    first_image = make_image_file(PdfRestFileID.generate(2))
    second_image = make_image_file(
        PdfRestFileID.generate(), mime_type="image/jpeg", name="second.jpg"
    )
    image_objects: list[PdfAddImageObject] = [
        PdfAddImageObject(
            image=first_image,
            page="1-last",
            x=0,
            y=10,
            width=72,
            tag_alt_text="Primary logo",
            tag_structure_type="Figure",
        ),
        PdfAddImageObject(
            image=first_image,
            page=1,
            x=100,
            y=10,
            height=36,
            tag_is_artifact=False,
        ),
        PdfAddImageObject(image=second_image, page="all", x=0, y=0),
    ]

    body = PdfAddImagesPayload.model_validate(
        {
            "file": pdf_file,
            "image_objects": image_objects,
            "tag_enabled": True,
            "tag_language": "en-US",
            "output": "branded-pages",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert body == {
        "id": str(pdf_file.id),
        "image_objects": [
            {
                "image_id": str(first_image.id),
                "page": "1-last",
                "x": 0,
                "y": 10,
                "width": 72.0,
                "tag_alt_text": "Primary logo",
                "tag_structure_type": "Figure",
            },
            {
                "image_id": str(first_image.id),
                "page": 1,
                "x": 100,
                "y": 10,
                "height": 36.0,
                "tag_is_artifact": False,
            },
            {
                "image_id": str(second_image.id),
                "page": "all",
                "x": 0,
                "y": 0,
            },
        ],
        "tag_enabled": True,
        "tag_language": "en-US",
        "output": "branded-pages",
    }


@pytest.mark.parametrize(
    ("image_object", "match"),
    [
        pytest.param(
            {"page": "last-2", "x": 0, "y": 0},
            "Input should be a valid integer",
            id="last-first",
        ),
        pytest.param(
            {"page": "4-2", "x": 0, "y": 0},
            "start page must be less",
            id="descending-range",
        ),
        pytest.param(
            {"page": "even", "x": 0, "y": 0},
            "Input should be a valid integer",
            id="unsupported-selector",
        ),
        pytest.param(
            {"page": [1, 2], "x": 0, "y": 0},
            "positive integer or string expression",
            id="list-selector",
        ),
        pytest.param(
            {"page": 1, "x": -1, "y": 0},
            "greater than or equal to 0",
            id="negative-x",
        ),
        pytest.param(
            {"page": 1, "x": 0, "y": 0, "width": 0},
            "greater than 0",
            id="zero-width",
        ),
        pytest.param(
            {"page": 1, "x": 0, "y": 0, "tag_alt_text": ""},
            "at least 1 character",
            id="empty-alt-text",
        ),
    ],
)
def test_add_images_payload_rejects_invalid_placement(
    image_object: dict[str, object], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        PdfAddImagesPayload.model_validate(
            {
                "file": make_pdf_file(PdfRestFileID.generate(1)),
                "image_objects": {
                    "image": make_image_file(PdfRestFileID.generate(2)),
                    **image_object,
                },
                "tag_enabled": True,
            }
        )


def _image_operation_transport(
    expected_body: dict[str, object],
    input_ids: list[PdfRestFileID],
    *,
    header_name: str,
    header_value: str,
    timeout: dict[str, object],
) -> httpx.MockTransport:
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/pdf-with-added-image"
            assert request.url.params["trace"] == "true"
            assert request.headers[header_name] == header_value
            assert json.loads(request.content) == expected_body
            timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200,
                json={"inputId": input_ids, "outputId": [output_id]},
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        return httpx.Response(
            200,
            json=build_file_info_payload(output_id, "branded.pdf", "application/pdf"),
        )

    return httpx.MockTransport(handler)


def test_add_image_to_pdf_size_and_tagging_options() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    timeout: dict[str, object] = {}
    expected_body: dict[str, object] = {
        "id": str(pdf_file.id),
        "image_id": str(image_file.id),
        "x": -5,
        "y": 10,
        "page": 1,
        "width": 72.0,
        "height": 36.0,
        "tag_enabled": True,
        "tag_language": "en-US",
        "tag_alt_text": "Company logo",
        "tag_is_artifact": False,
        "tag_structure_type": "Figure",
    }
    transport = _image_operation_transport(
        expected_body,
        [pdf_file.id, image_file.id],
        header_name="X-Test",
        header_value="sync-legacy",
        timeout=timeout,
    )

    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_image_to_pdf(
            pdf_file,
            image=image_file,
            x=-5,
            y=10,
            page=1,
            width=72,
            height=36,
            tag_enabled=True,
            tag_language="en-US",
            tag_alt_text="Company logo",
            tag_is_artifact=False,
            tag_structure_type="Figure",
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "sync-legacy"},
            timeout=0.25,
        )

    assert response.output_file.name == "branded.pdf"
    assert response.input_ids == [pdf_file.id, image_file.id]
    _assert_timeout(timeout["value"], 0.25)


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_size_and_tagging_options() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    timeout: dict[str, object] = {}
    expected_body: dict[str, object] = {
        "id": str(pdf_file.id),
        "image_id": str(image_file.id),
        "x": 5,
        "y": 10,
        "page": 1,
        "width": 72.0,
        "tag_enabled": True,
        "tag_language": "fr",
        "tag_alt_text": "Logo",
        "tag_is_artifact": True,
        "tag_structure_type": "Figure",
    }
    transport = _image_operation_transport(
        expected_body,
        [pdf_file.id, image_file.id],
        header_name="X-Test",
        header_value="async-legacy",
        timeout=timeout,
    )

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_image_to_pdf(
            pdf_file,
            image=image_file,
            x=5,
            y=10,
            page=1,
            width=72,
            tag_enabled=True,
            tag_language="fr",
            tag_alt_text="Logo",
            tag_is_artifact=True,
            tag_structure_type="Figure",
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "async-legacy"},
            timeout=0.75,
        )

    assert response.output_file.name == "branded.pdf"
    assert response.input_ids == [pdf_file.id, image_file.id]
    _assert_timeout(timeout["value"], 0.75)


def test_add_image_to_pdf_rejects_tag_metadata_without_tagging() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(
            ValidationError,
            match="tag_enabled must be true when tag options are provided",
        ),
    ):
        client.add_image_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image=make_image_file(PdfRestFileID.generate(2)),
            x=0,
            y=0,
            page=1,
            tag_alt_text="Logo",
        )


@pytest.mark.asyncio
async def test_async_add_image_to_pdf_rejects_tag_metadata_without_tagging() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(
            ValidationError,
            match="tag_enabled must be true when tag options are provided",
        ):
            await client.add_image_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image=make_image_file(PdfRestFileID.generate(2)),
                x=0,
                y=0,
                page=1,
                tag_is_artifact=False,
            )


def test_add_images_to_pdf_multiple_images_and_customization() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    first_image = make_image_file(PdfRestFileID.generate(2))
    second_image = make_image_file(
        PdfRestFileID.generate(), mime_type="image/gif", name="second.gif"
    )
    timeout: dict[str, object] = {}
    expected_body: dict[str, object] = {
        "id": str(pdf_file.id),
        "image_objects": [
            {
                "image_id": str(first_image.id),
                "page": "1-last",
                "x": 0,
                "y": 0,
                "width": 72.0,
                "tag_alt_text": "Logo",
            },
            {
                "image_id": str(second_image.id),
                "page": 2,
                "x": 100,
                "y": 200,
                "height": 36.0,
                "tag_is_artifact": True,
            },
        ],
        "tag_enabled": True,
        "tag_language": "en-US",
        "output": "branded-pages",
    }
    transport = _image_operation_transport(
        expected_body,
        [pdf_file.id, first_image.id, second_image.id],
        header_name="X-Test",
        header_value="sync-batch",
        timeout=timeout,
    )

    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_images_to_pdf(
            pdf_file,
            image_objects=[
                PdfAddImageObject(
                    image=first_image,
                    page="1-last",
                    x=0,
                    y=0,
                    width=72,
                    tag_alt_text="Logo",
                ),
                PdfAddImageObject(
                    image=second_image,
                    page=2,
                    x=100,
                    y=200,
                    height=36,
                    tag_is_artifact=True,
                ),
            ],
            tag_enabled=True,
            tag_language="en-US",
            output="branded-pages",
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "sync-batch"},
            extra_body={"output": "branded-pages"},
            timeout=1.25,
        )

    assert response.output_file.name == "branded.pdf"
    assert response.input_ids == [pdf_file.id, first_image.id, second_image.id]
    _assert_timeout(timeout["value"], 1.25)


@pytest.mark.asyncio
async def test_async_add_images_to_pdf_single_reused_image_and_customization() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    timeout: dict[str, object] = {}
    expected_body: dict[str, object] = {
        "id": str(pdf_file.id),
        "image_objects": [
            {
                "image_id": str(image_file.id),
                "page": "all",
                "x": 0,
                "y": 0,
                "tag_structure_type": "Figure",
            },
            {
                "image_id": str(image_file.id),
                "page": 1,
                "x": 72,
                "y": 72,
            },
        ],
        "tag_enabled": True,
        "tag_language": "en-US",
        "output": "branded-pages",
    }
    transport = _image_operation_transport(
        expected_body,
        [pdf_file.id, image_file.id],
        header_name="X-Test",
        header_value="async-batch",
        timeout=timeout,
    )

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_images_to_pdf(
            pdf_file,
            image_objects=[
                PdfAddImageObject(
                    image=image_file,
                    page="all",
                    x=0,
                    y=0,
                    tag_structure_type="Figure",
                ),
                PdfAddImageObject(image=image_file, page=1, x=72, y=72),
            ],
            tag_enabled=True,
            tag_language="en-US",
            output="branded-pages",
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "async-batch"},
            extra_body={"tag_enabled": True},
            timeout=1.5,
        )

    assert response.output_file.name == "branded.pdf"
    assert response.input_ids == [pdf_file.id, image_file.id]
    _assert_timeout(timeout["value"], 1.5)


def test_add_images_to_pdf_rejects_tag_metadata_without_tagging() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(
            ValidationError,
            match="tag_enabled must be true when tag options are provided",
        ),
    ):
        client.add_images_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image_objects=PdfAddImageObject(
                image=make_image_file(PdfRestFileID.generate(2)),
                page=1,
                x=0,
                y=0,
                tag_alt_text="Logo",
            ),
        )


@pytest.mark.asyncio
async def test_async_add_images_to_pdf_rejects_tag_metadata_without_tagging() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(
            ValidationError,
            match="tag_enabled must be true when tag options are provided",
        ):
            await client.add_images_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image_objects=PdfAddImageObject(
                    image=make_image_file(PdfRestFileID.generate(2)),
                    page=1,
                    x=0,
                    y=0,
                    tag_is_artifact=False,
                ),
            )


@pytest.mark.parametrize(
    ("files", "image_objects", "match"),
    [
        pytest.param(
            [
                make_pdf_file(PdfRestFileID.generate(1)),
                make_pdf_file(PdfRestFileID.generate(2)),
            ],
            PdfAddImageObject(
                image=make_image_file(PdfRestFileID.generate()),
                page=1,
                x=0,
                y=0,
            ),
            "at most 1 item",
            id="multiple-pdfs",
        ),
        pytest.param(
            make_pdf_file(PdfRestFileID.generate(1)),
            [],
            "at least 1 item",
            id="no-placements",
        ),
        pytest.param(
            make_pdf_file(PdfRestFileID.generate(1)),
            PdfAddImageObject(
                image=[
                    make_image_file(PdfRestFileID.generate(2)),
                    make_image_file(PdfRestFileID.generate()),
                ],
                page=1,
                x=0,
                y=0,
            ),
            "at most 1 item",
            id="multiple-images-per-placement",
        ),
        pytest.param(
            make_pdf_file(PdfRestFileID.generate(1)),
            PdfAddImageObject(
                image=make_pdf_file(PdfRestFileID.generate(2)),
                page=1,
                x=0,
                y=0,
            ),
            "Image must be JPEG, PNG, TIFF, or GIF",
            id="invalid-image-mime",
        ),
    ],
)
def test_add_images_to_pdf_cardinality_and_mime_validation(
    files: object, image_objects: object, match: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.add_images_to_pdf(
            files,
            image_objects=image_objects,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("files", "image_objects", "match"),
    [
        pytest.param(
            [
                make_pdf_file(PdfRestFileID.generate(1)),
                make_pdf_file(PdfRestFileID.generate(2)),
            ],
            PdfAddImageObject(
                image=make_image_file(PdfRestFileID.generate()),
                page=1,
                x=0,
                y=0,
            ),
            "at most 1 item",
            id="multiple-pdfs",
        ),
        pytest.param(
            make_pdf_file(PdfRestFileID.generate(1)),
            [],
            "at least 1 item",
            id="no-placements",
        ),
        pytest.param(
            make_pdf_file(PdfRestFileID.generate(1)),
            PdfAddImageObject(
                image=[
                    make_image_file(PdfRestFileID.generate(2)),
                    make_image_file(PdfRestFileID.generate()),
                ],
                page=1,
                x=0,
                y=0,
            ),
            "at most 1 item",
            id="multiple-images-per-placement",
        ),
        pytest.param(
            make_pdf_file(PdfRestFileID.generate(1)),
            PdfAddImageObject(
                image=make_pdf_file(PdfRestFileID.generate(2)),
                page=1,
                x=0,
                y=0,
            ),
            "Image must be JPEG, PNG, TIFF, or GIF",
            id="invalid-image-mime",
        ),
    ],
)
async def test_async_add_images_to_pdf_cardinality_and_mime_validation(
    files: object, image_objects: object, match: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match=match):
            await client.add_images_to_pdf(
                files,
                image_objects=image_objects,
            )


def _single_batch_transport(
    pdf_file: PdfRestFile,
    image_file: PdfRestFile,
    expected_image_object: dict[str, object],
) -> httpx.MockTransport:
    output_id = str(PdfRestFileID.generate())
    expected_body: dict[str, object] = {
        "id": str(pdf_file.id),
        "image_objects": [expected_image_object],
    }
    if "tag_structure_type" in expected_image_object:
        expected_body["tag_enabled"] = True

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/pdf-with-added-image"
            assert json.loads(request.content) == expected_body
            return httpx.Response(
                200,
                json={
                    "inputId": [pdf_file.id, image_file.id],
                    "outputId": [output_id],
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        return httpx.Response(
            200,
            json=build_file_info_payload(
                output_id, "single-image.pdf", "application/pdf"
            ),
        )

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(("image_mime_type", "image_name"), IMAGE_MIME_VARIANTS)
def test_add_images_to_pdf_single_object_mime_contract(
    image_mime_type: str,
    image_name: str,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(
        PdfRestFileID.generate(2), mime_type=image_mime_type, name=image_name
    )
    expected_image_object = {
        "image_id": str(image_file.id),
        "page": 1,
        "x": 0,
        "y": 0,
    }
    transport = _single_batch_transport(pdf_file, image_file, expected_image_object)

    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_images_to_pdf(
            pdf_file,
            image_objects=PdfAddImageObject(
                image=image_file,
                page=1,
                x=0,
                y=0,
            ),
        )

    assert response.input_ids == [pdf_file.id, image_file.id]
    assert response.output_file.name == "single-image.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(("image_mime_type", "image_name"), IMAGE_MIME_VARIANTS)
async def test_async_add_images_to_pdf_single_object_mime_contract(
    image_mime_type: str,
    image_name: str,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(
        PdfRestFileID.generate(2), mime_type=image_mime_type, name=image_name
    )
    expected_image_object = {
        "image_id": str(image_file.id),
        "page": 1,
        "x": 0,
        "y": 0,
    }
    transport = _single_batch_transport(pdf_file, image_file, expected_image_object)

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_images_to_pdf(
            pdf_file,
            image_objects=PdfAddImageObject(
                image=image_file,
                page=1,
                x=0,
                y=0,
            ),
        )

    assert response.input_ids == [pdf_file.id, image_file.id]
    assert response.output_file.name == "single-image.pdf"


@pytest.mark.parametrize("structure_type", CONTENT_STRUCTURE_TYPE_CASES)
def test_add_images_payload_structure_type_contract(
    structure_type: PdfContentStructureType,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))

    body = PdfAddImagesPayload.model_validate(
        {
            "file": pdf_file,
            "image_objects": PdfAddImageObject(
                image=image_file,
                page=1,
                x=0,
                y=0,
                tag_structure_type=structure_type,
            ),
            "tag_enabled": True,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert body == {
        "id": str(pdf_file.id),
        "image_objects": [
            {
                "image_id": str(image_file.id),
                "page": 1,
                "x": 0,
                "y": 0,
                "tag_structure_type": structure_type,
            }
        ],
        "tag_enabled": True,
    }


@pytest.mark.parametrize("structure_type", CONTENT_STRUCTURE_TYPE_CASES)
def test_add_images_to_pdf_structure_type_contract(
    structure_type: PdfContentStructureType,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    expected_image_object = {
        "image_id": str(image_file.id),
        "page": 1,
        "x": 0,
        "y": 0,
        "tag_structure_type": structure_type,
    }
    transport = _single_batch_transport(pdf_file, image_file, expected_image_object)

    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_images_to_pdf(
            pdf_file,
            image_objects=PdfAddImageObject(
                image=image_file,
                page=1,
                x=0,
                y=0,
                tag_structure_type=structure_type,
            ),
            tag_enabled=True,
        )

    assert response.input_ids == [pdf_file.id, image_file.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("structure_type", CONTENT_STRUCTURE_TYPE_CASES)
async def test_async_add_images_to_pdf_structure_type_contract(
    structure_type: PdfContentStructureType,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    expected_image_object = {
        "image_id": str(image_file.id),
        "page": 1,
        "x": 0,
        "y": 0,
        "tag_structure_type": structure_type,
    }
    transport = _single_batch_transport(pdf_file, image_file, expected_image_object)

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_images_to_pdf(
            pdf_file,
            image_objects=PdfAddImageObject(
                image=image_file,
                page=1,
                x=0,
                y=0,
                tag_structure_type=structure_type,
            ),
            tag_enabled=True,
        )

    assert response.input_ids == [pdf_file.id, image_file.id]


VALID_IMAGE_PLACEMENT_BOUNDARIES = (
    pytest.param("page", 1, id="page-minimum"),
    pytest.param("x", 0, id="x-minimum"),
    pytest.param("y", 0, id="y-minimum"),
    pytest.param("width", 0.01, id="width-positive"),
    pytest.param("height", 0.01, id="height-positive"),
)

INVALID_IMAGE_PLACEMENT_BOUNDARIES = (
    pytest.param("page", 0, "greater than or equal to 1", id="page-below-minimum"),
    pytest.param("x", -1, "greater than or equal to 0", id="x-below-minimum"),
    pytest.param("y", -1, "greater than or equal to 0", id="y-below-minimum"),
    pytest.param("width", 0, "greater than 0", id="width-zero"),
    pytest.param("height", 0, "greater than 0", id="height-zero"),
    pytest.param("width", float("inf"), "finite number", id="width-infinite"),
    pytest.param("height", float("inf"), "finite number", id="height-infinite"),
)


@pytest.mark.parametrize(("field", "value"), VALID_IMAGE_PLACEMENT_BOUNDARIES)
def test_add_images_to_pdf_accepts_placement_boundaries(
    field: str,
    value: int | float,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    image_object: dict[str, object] = {
        "image": image_file,
        "page": 1,
        "x": 0,
        "y": 0,
        field: value,
    }
    expected_image_object = {
        "image_id": str(image_file.id),
        "page": 1,
        "x": 0,
        "y": 0,
    }
    expected_image_object[field] = value
    transport = _single_batch_transport(pdf_file, image_file, expected_image_object)

    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_images_to_pdf(
            pdf_file,
            image_objects=cast(PdfAddImageObject, cast(object, image_object)),
        )

    assert response.input_ids == [pdf_file.id, image_file.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), VALID_IMAGE_PLACEMENT_BOUNDARIES)
async def test_async_add_images_to_pdf_accepts_placement_boundaries(
    field: str,
    value: int | float,
) -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    image_file = make_image_file(PdfRestFileID.generate(2))
    image_object: dict[str, object] = {
        "image": image_file,
        "page": 1,
        "x": 0,
        "y": 0,
        field: value,
    }
    expected_image_object = {
        "image_id": str(image_file.id),
        "page": 1,
        "x": 0,
        "y": 0,
    }
    expected_image_object[field] = value
    transport = _single_batch_transport(pdf_file, image_file, expected_image_object)

    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_images_to_pdf(
            pdf_file,
            image_objects=cast(PdfAddImageObject, cast(object, image_object)),
        )

    assert response.input_ids == [pdf_file.id, image_file.id]


@pytest.mark.parametrize(
    ("field", "value", "match"), INVALID_IMAGE_PLACEMENT_BOUNDARIES
)
def test_add_images_to_pdf_rejects_invalid_placement_boundaries(
    field: str,
    value: int | float,
    match: str,
) -> None:
    image_object: dict[str, object] = {
        "image": make_image_file(PdfRestFileID.generate(2)),
        "page": 1,
        "x": 0,
        "y": 0,
        field: value,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid placement must be rejected before transport execution.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.add_images_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image_objects=cast(PdfAddImageObject, cast(object, image_object)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "match"), INVALID_IMAGE_PLACEMENT_BOUNDARIES
)
async def test_async_add_images_to_pdf_rejects_invalid_placement_boundaries(
    field: str,
    value: int | float,
    match: str,
) -> None:
    image_object: dict[str, object] = {
        "image": make_image_file(PdfRestFileID.generate(2)),
        "page": 1,
        "x": 0,
        "y": 0,
        field: value,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid placement must be rejected before transport execution.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match=match):
            await client.add_images_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image_objects=cast(PdfAddImageObject, cast(object, image_object)),
            )


@pytest.mark.parametrize("field", [pytest.param("width"), pytest.param("height")])
@pytest.mark.parametrize(
    "value",
    [pytest.param(float("inf"), id="infinite"), pytest.param(float("nan"), id="nan")],
)
def test_add_image_to_pdf_rejects_non_finite_dimensions(
    field: str,
    value: float,
) -> None:
    dimensions = {
        "width": value if field == "width" else None,
        "height": value if field == "height" else None,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid dimensions must be rejected before transport execution.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match="finite number"),
    ):
        client.add_image_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image=make_image_file(PdfRestFileID.generate(2)),
            page=1,
            x=0,
            y=0,
            width=dimensions["width"],
            height=dimensions["height"],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [pytest.param("width"), pytest.param("height")])
@pytest.mark.parametrize(
    "value",
    [pytest.param(float("inf"), id="infinite"), pytest.param(float("nan"), id="nan")],
)
async def test_async_add_image_to_pdf_rejects_non_finite_dimensions(
    field: str,
    value: float,
) -> None:
    dimensions = {
        "width": value if field == "width" else None,
        "height": value if field == "height" else None,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid dimensions must be rejected before transport execution.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match="finite number"):
            await client.add_image_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image=make_image_file(PdfRestFileID.generate(2)),
                page=1,
                x=0,
                y=0,
                width=dimensions["width"],
                height=dimensions["height"],
            )


def test_add_images_to_pdf_rejects_invalid_structure_type() -> None:
    image_object = cast(
        PdfAddImageObject,
        cast(
            object,
            {
                "image": make_image_file(PdfRestFileID.generate(2)),
                "page": 1,
                "x": 0,
                "y": 0,
                "tag_structure_type": "DefinitelyNotAStructureType",
            },
        ),
    )

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail(
            "Invalid structure type must be rejected before transport execution."
        )

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match="tag_structure_type"),
    ):
        client.add_images_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            image_objects=image_object,
            tag_enabled=True,
        )


@pytest.mark.asyncio
async def test_async_add_images_to_pdf_rejects_invalid_structure_type() -> None:
    image_object = cast(
        PdfAddImageObject,
        cast(
            object,
            {
                "image": make_image_file(PdfRestFileID.generate(2)),
                "page": 1,
                "x": 0,
                "y": 0,
                "tag_structure_type": "DefinitelyNotAStructureType",
            },
        ),
    )

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail(
            "Invalid structure type must be rejected before transport execution."
        )

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match="tag_structure_type"):
            await client.add_images_to_pdf(
                make_pdf_file(PdfRestFileID.generate(1)),
                image_objects=image_object,
                tag_enabled=True,
            )
