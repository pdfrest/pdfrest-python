from __future__ import annotations

import json
import re

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfAddShapesPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_image_file,
    make_pdf_file,
)


def make_line(**overrides: object) -> dict[str, object]:
    line: dict[str, object] = {
        "type": "line",
        "page": 1,
        "x1": 72,
        "y1": 576,
        "x2": 540,
        "y2": 576,
        "stroke_color": (26, 72, 112),
        "stroke_width": 1.5,
    }
    line.update(overrides)
    return line


def make_rectangle(**overrides: object) -> dict[str, object]:
    rectangle: dict[str, object] = {
        "type": "rectangle",
        "page": "all",
        "x": 54,
        "y": 540,
        "width": 504,
        "height": 108,
        "fill_color": (0, 0, 0, 12),
        "opacity": 0.75,
    }
    rectangle.update(overrides)
    return rectangle


def test_add_shapes_payload_serializes_line_and_rectangle() -> None:
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))

    payload = PdfAddShapesPayload.model_validate(
        {
            "files": pdf_file,
            "shape_objects": [
                make_line(
                    tag_actual_text="Section divider",
                    tag_structure_type="Figure",
                ),
                make_rectangle(tag_is_artifact=True),
            ],
            "tag_enabled": True,
            "output": "added-shapes",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert payload == {
        "id": str(pdf_file.id),
        "shape_objects": [
            {
                "type": "line",
                "page": 1,
                "x1": 72.0,
                "y1": 576.0,
                "x2": 540.0,
                "y2": 576.0,
                "stroke_color_rgb": "26,72,112",
                "stroke_width": 1.5,
                "tag_actual_text": "Section divider",
                "tag_structure_type": "Figure",
            },
            {
                "type": "rectangle",
                "page": "all",
                "x": 54.0,
                "y": 540.0,
                "width": 504.0,
                "height": 108.0,
                "fill_color_cmyk": "0,0,0,12",
                "opacity": 0.75,
                "tag_is_artifact": True,
            },
        ],
        "tag_enabled": True,
        "output": "added-shapes",
    }


def test_add_shapes_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    expected_payload = PdfAddShapesPayload.model_validate(
        {
            "files": pdf_file,
            "shape_objects": [make_line(), make_rectangle(tag_is_artifact=True)],
            "tag_enabled": True,
            "output": "with-shapes",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-shapes":
            seen["post"] += 1
            assert json.loads(request.content) == expected_payload
            return httpx.Response(
                200, json={"inputId": [pdf_file.id], "outputId": [output_id]}
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "with-shapes.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.add_shapes_to_pdf(
            pdf_file,
            shape_objects=[make_line(), make_rectangle(tag_is_artifact=True)],
            tag_enabled=True,
            output="with-shapes",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "with-shapes.pdf"
    assert response.output_file.type == "application/pdf"
    assert response.input_id == pdf_file.id


@pytest.mark.asyncio
async def test_async_add_shapes_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-shapes":
            seen["post"] += 1
            payload = json.loads(request.content)
            assert payload["id"] == str(pdf_file.id)
            assert payload["shape_objects"] == [
                {
                    "type": "rectangle",
                    "page": 1,
                    "x": 10.0,
                    "y": 20.0,
                    "width": 30.0,
                    "height": 40.0,
                    "fill_color_rgb": "245,247,250",
                    "tag_actual_text": "Decorative panel",
                    "tag_structure_type": "Figure",
                }
            ]
            assert payload["tag_enabled"] is True
            assert payload["output"] == "async-with-shapes"
            return httpx.Response(
                200, json={"inputId": [pdf_file.id], "outputId": [output_id]}
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-with-shapes.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.add_shapes_to_pdf(
            pdf_file,
            shape_objects=make_rectangle(
                page=1,
                x=10,
                y=20,
                width=30,
                height=40,
                fill_color=(245, 247, 250),
                opacity=None,
                tag_actual_text="Decorative panel",
                tag_structure_type="Figure",
            ),
            tag_enabled=True,
            output="async-with-shapes",
        )

    assert seen == {"post": 1, "get": 1}
    assert response.output_file.name == "async-with-shapes.pdf"


def test_add_shapes_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-shapes":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            payload = json.loads(request.content)
            assert payload["output"] == "overridden-shapes"
            captured_timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200, json={"inputId": [pdf_file.id], "outputId": [output_id]}
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Debug"] == "1"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "overridden-shapes.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.add_shapes_to_pdf(
            pdf_file,
            shape_objects=make_line(),
            extra_query={"trace": "true"},
            extra_headers={"X-Debug": "1"},
            extra_body={"output": "overridden-shapes"},
            timeout=0.25,
        )

    assert response.output_file.name == "overridden-shapes.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(0.25) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_async_add_shapes_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    pdf_file = make_pdf_file(PdfRestFileID.generate(1))
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-added-shapes":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Test"] == "async"
            assert json.loads(request.content)["output"] == "async-custom-shapes"
            captured_timeout["value"] = request.extensions.get("timeout")
            return httpx.Response(
                200, json={"inputId": [pdf_file.id], "outputId": [output_id]}
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["trace"] == "true"
            assert request.headers["X-Test"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "async-custom-shapes.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.add_shapes_to_pdf(
            pdf_file,
            shape_objects=make_line(),
            extra_query={"trace": "true"},
            extra_headers={"X-Test": "async"},
            extra_body={"output": "async-custom-shapes"},
            timeout=1.0,
        )

    assert response.output_file.name == "async-custom-shapes.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(
            component == pytest.approx(1.0) for component in timeout_value.values()
        )
    else:
        assert timeout_value == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("shape_objects", "tag_enabled", "match"),
    [
        pytest.param([], None, "at least 1 item", id="empty-shapes"),
        pytest.param(
            make_line(stroke_color=(0, 0)),
            None,
            re.escape("stroke_color must include exactly 3 (RGB) or 4 (CMYK) values."),
            id="line-color-channel-count",
        ),
        pytest.param(
            make_rectangle(fill_color=(0, 0)),
            None,
            re.escape("fill_color must include exactly 3 (RGB) or 4 (CMYK) values."),
            id="rectangle-color-channel-count",
        ),
        pytest.param(
            make_rectangle(width=0),
            None,
            "greater than 0",
            id="zero-width",
        ),
        pytest.param(
            make_line(tag_actual_text="Tagged line"),
            False,
            re.escape("tag_enabled must be true when tag options are provided."),
            id="tagging-not-enabled",
        ),
    ],
)
def test_add_shapes_to_pdf_rejects_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
    shape_objects: object,
    tag_enabled: bool | None,
    match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.add_shapes_to_pdf(
            make_pdf_file(PdfRestFileID.generate(1)),
            shape_objects=shape_objects,  # type: ignore[arg-type]
            tag_enabled=tag_enabled,
        )


@pytest.mark.asyncio
async def test_async_add_shapes_to_pdf_rejects_non_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match="Must be a PDF file"):
            await client.add_shapes_to_pdf(
                make_image_file(PdfRestFileID.generate(1)),
                shape_objects=make_line(),
            )


def test_add_shapes_to_pdf_rejects_non_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match="Must be a PDF file"),
    ):
        client.add_shapes_to_pdf(
            make_image_file(PdfRestFileID.generate(1)),
            shape_objects=make_line(),
        )


def test_add_shapes_to_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match="at most 1 item"),
    ):
        client.add_shapes_to_pdf(
            [
                make_pdf_file(PdfRestFileID.generate(1)),
                make_pdf_file(PdfRestFileID.generate(2)),
            ],
            shape_objects=make_line(),
        )


@pytest.mark.asyncio
async def test_async_add_shapes_to_pdf_rejects_multiple_input_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match="at most 1 item"):
            await client.add_shapes_to_pdf(
                [
                    make_pdf_file(PdfRestFileID.generate(1)),
                    make_pdf_file(PdfRestFileID.generate(2)),
                ],
                shape_objects=make_line(),
            )


@pytest.mark.parametrize(
    ("shape", "match"),
    [
        pytest.param(make_line(x1=-1), "greater than or equal to 0", id="x1-below"),
        pytest.param(make_line(y2=-1), "greater than or equal to 0", id="y2-below"),
        pytest.param(make_line(page=0), "greater than or equal to 1", id="page-below"),
        pytest.param(
            make_line(opacity=-0.01), "greater than or equal to 0", id="opacity-below"
        ),
        pytest.param(
            make_line(opacity=1.01), "less than or equal to 1", id="opacity-above"
        ),
        pytest.param(
            make_line(stroke_width=0), "greater than 0", id="stroke-width-zero"
        ),
        pytest.param(
            make_line(stroke_color=(-1, 0, 0)),
            "greater than or equal to 0",
            id="rgb-below",
        ),
        pytest.param(
            make_line(stroke_color=(256, 0, 0)),
            "less than or equal to 255",
            id="rgb-above",
        ),
        pytest.param(make_rectangle(width=0), "greater than 0", id="width-zero"),
        pytest.param(make_rectangle(height=0), "greater than 0", id="height-zero"),
        pytest.param(
            make_rectangle(fill_color=(-1, 0, 0, 0)),
            "greater than or equal to 0",
            id="cmyk-below",
        ),
        pytest.param(
            make_rectangle(fill_color=(101, 0, 0, 0)),
            "less than or equal to 100",
            id="cmyk-above",
        ),
    ],
)
def test_add_shapes_payload_rejects_out_of_range_values(
    shape: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        PdfAddShapesPayload.model_validate(
            {
                "files": make_pdf_file(PdfRestFileID.generate(1)),
                "shape_objects": shape,
            }
        )


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(
            make_line(
                page=1,
                x1=0,
                y1=0,
                x2=0,
                y2=0,
                opacity=0,
                stroke_color=(0, 255, 0),
            ),
            id="line-lower-bounds",
        ),
        pytest.param(
            make_rectangle(
                x=0,
                y=0,
                width=0.01,
                height=0.01,
                opacity=1,
                fill_color=(0, 100, 0, 100),
            ),
            id="rectangle-upper-bounds",
        ),
    ],
)
def test_add_shapes_payload_accepts_boundary_values(shape: dict[str, object]) -> None:
    payload = PdfAddShapesPayload.model_validate(
        {
            "files": make_pdf_file(PdfRestFileID.generate(1)),
            "shape_objects": shape,
        }
    )

    assert payload.shape_objects[0].model_dump(mode="json", exclude_none=True)
