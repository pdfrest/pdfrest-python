from __future__ import annotations

import json
import re
from typing import Literal

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfSetPageBoxesPayload
from pdfrest.types import (
    PdfInsetPageBoxDefinition,
    PdfInsetPageBoxPage,
    PdfMediaBoxDefinition,
    PdfMediaBoxPage,
    PdfPageBoxDefinition,
)

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)

InsetBoxType = Literal["crop", "bleed", "trim", "art"]
MarginField = Literal["top", "bottom", "left", "right"]


def _media_box(range_: str | int = "1-last") -> PdfMediaBoxDefinition:
    return PdfMediaBoxDefinition(
        box="media",
        pages=[
            PdfMediaBoxPage(
                range=range_,
                top=-18,
                bottom=0,
                left=-36,
                right=0,
            )
        ],
    )


def _inset_box(
    box: InsetBoxType = "crop", range_: str | int = "all"
) -> PdfInsetPageBoxDefinition:
    return PdfInsetPageBoxDefinition(
        box=box,
        pages=[
            PdfInsetPageBoxPage(
                range=range_,
                top=18,
                bottom=18,
                left=36,
                right=36,
            )
        ],
    )


def _assert_timeout(value: float | dict[str, float] | None, expected: float) -> None:
    assert value is not None
    if isinstance(value, dict):
        assert value
        assert all(component == pytest.approx(expected) for component in value.values())
    else:
        assert value == pytest.approx(expected)


def _response_handler(
    input_file: PdfRestFile,
    output_id: str,
    expected_body: dict[str, object],
    *,
    output_name: str = "page-boxes.pdf",
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/pdf-with-page-boxes-set":
            assert json.loads(request.content) == expected_body
            return httpx.Response(
                200, json={"inputId": [input_file.id], "outputId": [output_id]}
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(output_id, output_name, "application/pdf"),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    return httpx.MockTransport(handler)


def test_set_page_boxes_payload_serializes_exact_json_string() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())

    payload = PdfSetPageBoxesPayload.model_validate(
        {
            "file": input_file,
            "boxes": [
                PdfMediaBoxDefinition(
                    box="media",
                    pages=[
                        PdfMediaBoxPage(
                            range=1,
                            top=-18,
                            bottom=0,
                            left=-36,
                            right=0,
                        ),
                        PdfMediaBoxPage(
                            range="2-last",
                            top=0,
                            bottom=0,
                            left=0,
                            right=0,
                        ),
                    ],
                ),
                _inset_box("crop", "even"),
            ],
            "output": "updated-boxes",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert payload["id"] == str(input_file.id)
    assert payload["output"] == "updated-boxes"
    assert json.loads(payload["boxes"]) == {
        "boxes": [
            {
                "box": "media",
                "pages": [
                    {
                        "range": "1",
                        "top": -18.0,
                        "bottom": 0.0,
                        "left": -36.0,
                        "right": 0.0,
                    },
                    {
                        "range": "2-last",
                        "top": 0.0,
                        "bottom": 0.0,
                        "left": 0.0,
                        "right": 0.0,
                    },
                ],
            },
            {
                "box": "crop",
                "pages": [
                    {
                        "range": "even",
                        "top": 18.0,
                        "bottom": 18.0,
                        "left": 36.0,
                        "right": 36.0,
                    }
                ],
            },
        ]
    }


@pytest.mark.parametrize(
    "range_",
    [
        pytest.param(1, id="integer"),
        pytest.param("1", id="numeric-string"),
        pytest.param("1-3", id="ascending-range"),
        pytest.param("2-last", id="last-range"),
        pytest.param("all", id="all"),
        pytest.param("even", id="even"),
        pytest.param("odd", id="odd"),
    ],
)
def test_set_page_boxes_payload_accepts_page_selectors(range_: str | int) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())

    payload = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": _media_box(range_)}
    ).model_dump(mode="json", by_alias=True)

    assert json.loads(payload["boxes"])["boxes"][0]["pages"][0]["range"] == str(range_)


@pytest.mark.parametrize(
    "range_",
    [
        pytest.param(1, id="integer"),
        pytest.param("1", id="numeric-string"),
        pytest.param("1-3", id="ascending-range"),
        pytest.param("2-last", id="last-range"),
        pytest.param("all", id="all"),
        pytest.param("even", id="even"),
        pytest.param("odd", id="odd"),
    ],
)
def test_set_pdf_page_boxes_sends_each_page_selector(range_: str | int) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    definition = _media_box(range_)
    expected = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=_response_handler(input_file, output_id, expected),
    ) as client:
        response = client.set_pdf_page_boxes(input_file, boxes=definition)

    assert response.input_id == input_file.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "range_",
    [
        pytest.param(1, id="integer"),
        pytest.param("1", id="numeric-string"),
        pytest.param("1-3", id="ascending-range"),
        pytest.param("2-last", id="last-range"),
        pytest.param("all", id="all"),
        pytest.param("even", id="even"),
        pytest.param("odd", id="odd"),
    ],
)
async def test_async_set_pdf_page_boxes_sends_each_page_selector(
    range_: str | int,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    definition = _media_box(range_)
    expected = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=_response_handler(input_file, output_id, expected),
    ) as client:
        response = await client.set_pdf_page_boxes(input_file, boxes=definition)

    assert response.input_id == input_file.id


@pytest.mark.parametrize(
    "range_",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param("5-2", id="descending"),
        pytest.param("last", id="last-alone"),
        pytest.param("1,2", id="comma-list"),
        pytest.param("first", id="unknown-selector"),
        pytest.param(" 1 ", id="whitespace"),
    ],
)
def test_set_page_boxes_payload_rejects_invalid_page_selectors(
    range_: str | int,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    match = re.escape(f"The given page range is invalid. [{range_}].")

    with pytest.raises(ValidationError, match=match):
        PdfSetPageBoxesPayload.model_validate(
            {"file": input_file, "boxes": _media_box(range_)}
        )


@pytest.mark.parametrize(
    "ranges",
    [
        pytest.param(("1-3", "2-4"), id="overlapping-ranges"),
        pytest.param(("all", 1), id="all-and-page"),
        pytest.param(("even", 2), id="even-and-even-page"),
        pytest.param(("odd", 3), id="odd-and-odd-page"),
        pytest.param(("1-3", "3-last"), id="range-and-last-range"),
    ],
)
def test_set_page_boxes_payload_rejects_conflicting_selections(
    ranges: tuple[str | int, str | int],
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    definition = _media_box(ranges[0])
    definition["pages"] = [
        *definition["pages"],
        _media_box(ranges[1])["pages"][0],
    ]

    with pytest.raises(
        ValidationError,
        match="The box page settings conflict with each other",
    ):
        PdfSetPageBoxesPayload.model_validate({"file": input_file, "boxes": definition})


def test_set_page_boxes_payload_rejects_conflicts_across_definitions() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())

    with pytest.raises(
        ValidationError,
        match=r"Page selection \[2-4\] overlaps an earlier media selection",
    ):
        PdfSetPageBoxesPayload.model_validate(
            {
                "file": input_file,
                "boxes": [_media_box("1-3"), _media_box("2-4")],
            }
        )


@pytest.mark.parametrize(
    "ranges",
    [
        pytest.param(("odd", "even"), id="odd-and-even"),
        pytest.param(("1-3", "4-last"), id="disjoint-ranges"),
        pytest.param(("even", 1), id="even-and-odd-page"),
    ],
)
def test_set_page_boxes_payload_accepts_disjoint_selections(
    ranges: tuple[str | int, str | int],
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    definition = _media_box(ranges[0])
    definition["pages"] = [
        *definition["pages"],
        _media_box(ranges[1])["pages"][0],
    ]

    payload = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    )

    assert len(payload.boxes[0].pages) == 2


def test_set_page_boxes_payload_allows_same_selection_for_different_boxes() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())

    payload = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": [_media_box("all"), _inset_box("crop", "all")]}
    )

    assert len(payload.boxes) == 2


@pytest.mark.parametrize(
    "box",
    [
        pytest.param("crop", id="crop"),
        pytest.param("bleed", id="bleed"),
        pytest.param("trim", id="trim"),
        pytest.param("art", id="art"),
    ],
)
def test_set_pdf_page_boxes_supports_each_inset_box(box: InsetBoxType) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    definition = _inset_box(box)
    expected = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=_response_handler(input_file, output_id, expected),
    ) as client:
        response = client.set_pdf_page_boxes(input_file, boxes=definition)

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.input_id == input_file.id
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "box",
    [
        pytest.param("crop", id="crop"),
        pytest.param("bleed", id="bleed"),
        pytest.param("trim", id="trim"),
        pytest.param("art", id="art"),
    ],
)
async def test_async_set_pdf_page_boxes_supports_each_inset_box(
    box: InsetBoxType,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    definition = _inset_box(box)
    expected = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=_response_handler(input_file, output_id, expected),
    ) as client:
        response = await client.set_pdf_page_boxes(input_file, boxes=definition)

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.input_id == input_file.id
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None


@pytest.mark.parametrize(
    ("margin", "match"),
    [
        pytest.param(0, "greater than 0", id="zero"),
        pytest.param(-0.1, "greater than 0", id="negative"),
        pytest.param(float("inf"), "finite number", id="infinite"),
        pytest.param(float("nan"), "finite number", id="nan"),
    ],
)
@pytest.mark.parametrize(
    "field",
    [
        pytest.param("top", id="top"),
        pytest.param("bottom", id="bottom"),
        pytest.param("left", id="left"),
        pytest.param("right", id="right"),
    ],
)
def test_set_page_boxes_payload_rejects_invalid_inset_margins(
    margin: float,
    match: str,
    field: MarginField,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    box = _inset_box()
    box["pages"][0][field] = margin

    with pytest.raises(ValidationError, match=match):
        PdfSetPageBoxesPayload.model_validate({"file": input_file, "boxes": box})


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("top", id="top"),
        pytest.param("bottom", id="bottom"),
        pytest.param("left", id="left"),
        pytest.param("right", id="right"),
    ],
)
def test_set_page_boxes_payload_accepts_positive_inset_boundary(
    field: MarginField,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    box = _inset_box()
    box["pages"][0][field] = 0.1

    payload = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": box}
    ).model_dump(mode="json", by_alias=True)

    page = json.loads(payload["boxes"])["boxes"][0]["pages"][0]
    assert page[field] == pytest.approx(0.1)


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("top", id="top"),
        pytest.param("bottom", id="bottom"),
        pytest.param("left", id="left"),
        pytest.param("right", id="right"),
    ],
)
def test_set_pdf_page_boxes_sends_positive_inset_boundary(
    field: MarginField,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    definition = _inset_box()
    definition["pages"][0][field] = 0.1
    expected = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=_response_handler(input_file, output_id, expected),
    ) as client:
        response = client.set_pdf_page_boxes(input_file, boxes=definition)

    assert response.input_id == input_file.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        pytest.param("top", id="top"),
        pytest.param("bottom", id="bottom"),
        pytest.param("left", id="left"),
        pytest.param("right", id="right"),
    ],
)
async def test_async_set_pdf_page_boxes_sends_positive_inset_boundary(
    field: MarginField,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    definition = _inset_box()
    definition["pages"][0][field] = 0.1
    expected = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": definition}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=_response_handler(input_file, output_id, expected),
    ) as client:
        response = await client.set_pdf_page_boxes(input_file, boxes=definition)

    assert response.input_id == input_file.id


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("top", id="top"),
        pytest.param("bottom", id="bottom"),
        pytest.param("left", id="left"),
        pytest.param("right", id="right"),
    ],
)
@pytest.mark.parametrize(
    "margin",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
    ],
)
def test_set_pdf_page_boxes_rejects_invalid_inset_margin_before_transport(
    field: MarginField,
    margin: int,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    definition = _inset_box()
    definition["pages"][0][field] = margin

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(lambda _: pytest.fail("request was sent")),
        ) as client,
        pytest.raises(ValidationError, match=rf"{field}[\s\S]*greater than 0"),
    ):
        client.set_pdf_page_boxes(input_file, boxes=definition)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        pytest.param("top", id="top"),
        pytest.param("bottom", id="bottom"),
        pytest.param("left", id="left"),
        pytest.param("right", id="right"),
    ],
)
@pytest.mark.parametrize(
    "margin",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
    ],
)
async def test_async_set_pdf_page_boxes_rejects_invalid_inset_margin_before_transport(
    field: MarginField,
    margin: int,
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    definition = _inset_box()
    definition["pages"][0][field] = margin

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(lambda _: pytest.fail("request was sent")),
    ) as client:
        with pytest.raises(ValidationError, match=rf"{field}[\s\S]*greater than 0"):
            await client.set_pdf_page_boxes(input_file, boxes=definition)


def test_set_page_boxes_payload_accepts_signed_media_margins() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())

    payload = PdfSetPageBoxesPayload.model_validate(
        {"file": input_file, "boxes": _media_box()}
    ).model_dump(mode="json", by_alias=True)

    page = json.loads(payload["boxes"])["boxes"][0]["pages"][0]
    assert page["top"] == -18
    assert page["bottom"] == 0


@pytest.mark.parametrize(
    ("case", "match"),
    [
        pytest.param("empty", "at least 1 item", id="empty-boxes"),
        pytest.param(
            "descending",
            r"The given page range is invalid\. \[4\-2\]\.",
            id="descending-range",
        ),
        pytest.param(
            "overlap",
            "The box page settings conflict with each other",
            id="overlapping-ranges",
        ),
    ],
)
def test_set_pdf_page_boxes_rejects_invalid_definitions_before_transport(
    case: str, match: str
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    boxes: list[PdfPageBoxDefinition]
    if case == "empty":
        boxes = []
    elif case == "descending":
        boxes = [_media_box("4-2")]
    else:
        definition = _media_box("1-3")
        definition["pages"] = [
            *definition["pages"],
            _media_box("2-4")["pages"][0],
        ]
        boxes = [definition]

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(lambda _: pytest.fail("request was sent")),
        ) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.set_pdf_page_boxes(input_file, boxes=boxes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "match"),
    [
        pytest.param("empty", "at least 1 item", id="empty-boxes"),
        pytest.param(
            "descending",
            r"The given page range is invalid\. \[4\-2\]\.",
            id="descending-range",
        ),
        pytest.param(
            "overlap",
            "The box page settings conflict with each other",
            id="overlapping-ranges",
        ),
    ],
)
async def test_async_set_pdf_page_boxes_rejects_invalid_definitions_before_transport(
    case: str, match: str
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    boxes: list[PdfPageBoxDefinition]
    if case == "empty":
        boxes = []
    elif case == "descending":
        boxes = [_media_box("4-2")]
    else:
        definition = _media_box("1-3")
        definition["pages"] = [
            *definition["pages"],
            _media_box("2-4")["pages"][0],
        ]
        boxes = [definition]

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(lambda _: pytest.fail("request was sent")),
    ) as client:
        with pytest.raises(ValidationError, match=match):
            await client.set_pdf_page_boxes(input_file, boxes=boxes)


def test_set_pdf_page_boxes_request_customization() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    captured_timeout: float | dict[str, float] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_timeout
        assert request.url.params["trace"] == "sync"
        assert request.headers["X-Debug"] == "page-boxes"
        if request.method == "POST":
            captured_timeout = request.extensions.get("timeout")
            assert json.loads(request.content) == {
                "id": str(input_file.id),
                "boxes": PdfSetPageBoxesPayload.model_validate(
                    {"file": input_file, "boxes": _media_box()}
                ).model_dump(mode="json", by_alias=True)["boxes"],
                "output": "boxed-sync",
                "debug": True,
            }
            return httpx.Response(
                200, json={"inputId": [input_file.id], "outputId": [output_id]}
            )
        return httpx.Response(
            200,
            json=build_file_info_payload(
                output_id, "boxed-sync.pdf", "application/pdf"
            ),
        )

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.set_pdf_page_boxes(
            input_file,
            boxes=_media_box(),
            output="boxed-sync",
            extra_query={"trace": "sync"},
            extra_headers={"X-Debug": "page-boxes"},
            extra_body={"debug": True},
            timeout=0.71,
        )

    assert response.output_file.name == "boxed-sync.pdf"
    _assert_timeout(captured_timeout, 0.71)


@pytest.mark.asyncio
async def test_async_set_pdf_page_boxes_request_customization() -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    captured_timeout: float | dict[str, float] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_timeout
        assert request.url.params["trace"] == "async"
        assert request.headers["X-Debug"] == "page-boxes"
        if request.method == "POST":
            captured_timeout = request.extensions.get("timeout")
            assert json.loads(request.content) == {
                "id": str(input_file.id),
                "boxes": PdfSetPageBoxesPayload.model_validate(
                    {"file": input_file, "boxes": _media_box()}
                ).model_dump(mode="json", by_alias=True)["boxes"],
                "output": "boxed-async",
                "debug": True,
            }
            return httpx.Response(
                200, json={"inputId": [input_file.id], "outputId": [output_id]}
            )
        return httpx.Response(
            200,
            json=build_file_info_payload(
                output_id, "boxed-async.pdf", "application/pdf"
            ),
        )

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.set_pdf_page_boxes(
            input_file,
            boxes=_media_box(),
            output="boxed-async",
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "page-boxes"},
            extra_body={"debug": True},
            timeout=0.83,
        )

    assert response.output_file.name == "boxed-async.pdf"
    _assert_timeout(captured_timeout, 0.83)


@pytest.mark.parametrize(
    ("files", "match"),
    [
        pytest.param([], "at least 1 item", id="empty"),
        pytest.param("png", "Must be a PDF file", id="mime"),
        pytest.param("multiple", "at most 1 item", id="cardinality"),
    ],
)
def test_set_pdf_page_boxes_rejects_invalid_resources(
    files: list[PdfRestFile] | str, match: str
) -> None:
    pdf = make_pdf_file(PdfRestFileID.generate())
    file_argument: PdfRestFile | list[PdfRestFile]
    if files == "png":
        file_argument = PdfRestFile.model_validate(
            build_file_info_payload(PdfRestFileID.generate(), "image.png", "image/png")
        )
    elif files == "multiple":
        file_argument = [pdf, make_pdf_file(PdfRestFileID.generate())]
    else:
        file_argument = []

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(lambda _: pytest.fail("request was sent")),
        ) as client,
        pytest.raises(ValidationError, match=match),
    ):
        client.set_pdf_page_boxes(file_argument, boxes=_media_box())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("files", "match"),
    [
        pytest.param([], "at least 1 item", id="empty"),
        pytest.param("png", "Must be a PDF file", id="mime"),
        pytest.param("multiple", "at most 1 item", id="cardinality"),
    ],
)
async def test_async_set_pdf_page_boxes_rejects_invalid_resources(
    files: list[PdfRestFile] | str, match: str
) -> None:
    pdf = make_pdf_file(PdfRestFileID.generate())
    file_argument: PdfRestFile | list[PdfRestFile]
    if files == "png":
        file_argument = PdfRestFile.model_validate(
            build_file_info_payload(PdfRestFileID.generate(), "image.png", "image/png")
        )
    elif files == "multiple":
        file_argument = [pdf, make_pdf_file(PdfRestFileID.generate())]
    else:
        file_argument = []

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(lambda _: pytest.fail("request was sent")),
    ) as client:
        with pytest.raises(ValidationError, match=match):
            await client.set_pdf_page_boxes(file_argument, boxes=_media_box())
