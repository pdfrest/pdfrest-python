from __future__ import annotations

import json
from typing import Any, Literal

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestInfoResponse
from pdfrest.types import (
    PdfInsetPageBoxDefinition,
    PdfInsetPageBoxPage,
    PdfMediaBoxDefinition,
    PdfMediaBoxPage,
    PdfPageBoxDefinition,
)

from ..resources import get_test_resource_path

BoxType = Literal["media", "crop", "bleed", "trim", "art"]
PageSelector = Literal["1-3", "even", "odd"] | int

_BOX_INFO_KEYS: dict[BoxType, str] = {
    "media": "MediaBox",
    "crop": "CropBox",
    "bleed": "BleedBox",
    "trim": "TrimBox",
    "art": "ArtBox",
}


@pytest.fixture(scope="module")
def uploaded_pdf_for_page_boxes(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        return client.files.create_from_paths([get_test_resource_path("report.pdf")])[0]


@pytest.fixture(scope="module")
def uploaded_multi_page_pdf_for_page_boxes(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        return client.files.create_from_paths([get_test_resource_path("20-pages.pdf")])[
            0
        ]


def _box_definition(box: BoxType) -> PdfPageBoxDefinition:
    if box == "media":
        return PdfMediaBoxDefinition(
            box="media",
            pages=[PdfMediaBoxPage(range="all", top=-9, bottom=0, left=-9, right=0)],
        )
    return PdfInsetPageBoxDefinition(
        box=box,
        pages=[PdfInsetPageBoxPage(range="all", top=9, bottom=9, left=9, right=9)],
    )


def _page_box_info(response: PdfRestInfoResponse) -> dict[str, Any]:
    assert response.model_extra is not None
    page_boxes = response.model_extra.get("page_boxes")
    assert isinstance(page_boxes, dict)
    return page_boxes


def _assert_box_geometry(response: PdfRestInfoResponse, box: BoxType) -> None:
    first_page = _page_box_info(response)["1"]
    assert isinstance(first_page, dict)
    if box == "media":
        assert first_page["MediaBox"] == [-9, 801, 612, 0]
        assert first_page["CropBox"] == {
            "Box": [-9, 801, 612, 0],
            "MatchesMediaBox": True,
        }
        return

    assert first_page[_BOX_INFO_KEYS[box]] == {
        "Box": [9, 783, 603, 9],
        "MatchesMediaBox": False,
    }
    assert first_page["MediaBox"] == [0, 792, 612, 0]


def _assert_crop_selection(
    response: PdfRestInfoResponse,
    *,
    selected_page: int,
    unselected_page: int,
) -> None:
    page_boxes = _page_box_info(response)
    assert page_boxes[str(selected_page)]["CropBox"] == {
        "Box": [9, 783, 603, 9],
        "MatchesMediaBox": False,
    }
    assert page_boxes[str(unselected_page)]["CropBox"] == {
        "Box": [0, 792, 612, 0],
        "MatchesMediaBox": True,
    }


def _positive_boundary_definition() -> PdfInsetPageBoxDefinition:
    return PdfInsetPageBoxDefinition(
        box="crop",
        pages=[
            PdfInsetPageBoxPage(
                range="all",
                top=0.1,
                bottom=0.1,
                left=0.1,
                right=0.1,
            )
        ],
    )


def _assert_positive_boundary_geometry(response: PdfRestInfoResponse) -> None:
    first_page = _page_box_info(response)["1"]
    assert first_page["CropBox"]["Box"] == pytest.approx(
        [0.1, 791.9, 611.9, 0.1], abs=1e-4
    )
    assert first_page["CropBox"]["MatchesMediaBox"] is False


@pytest.mark.parametrize(
    "box",
    [
        pytest.param("media", id="media"),
        pytest.param("crop", id="crop"),
        pytest.param("bleed", id="bleed"),
        pytest.param("trim", id="trim"),
        pytest.param("art", id="art"),
    ],
)
def test_live_set_pdf_page_boxes(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_page_boxes: PdfRestFile,
    box: BoxType,
) -> None:
    output_name = f"page-box-{box}"
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        response = client.set_pdf_page_boxes(
            uploaded_pdf_for_page_boxes,
            boxes=_box_definition(box),
            output=output_name,
        )
        page_box_info = client.query_pdf_info(
            response.output_file,
            queries="page_count",
            extra_body={"queries": "page_boxes"},
        )

    assert response.input_id == uploaded_pdf_for_page_boxes.id
    assert response.output_file.name.startswith(output_name)
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    _assert_box_geometry(page_box_info, box)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "box",
    [
        pytest.param("media", id="media"),
        pytest.param("crop", id="crop"),
        pytest.param("bleed", id="bleed"),
        pytest.param("trim", id="trim"),
        pytest.param("art", id="art"),
    ],
)
async def test_live_async_set_pdf_page_boxes(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_page_boxes: PdfRestFile,
    box: BoxType,
) -> None:
    output_name = f"async-page-box-{box}"
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        response = await client.set_pdf_page_boxes(
            uploaded_pdf_for_page_boxes,
            boxes=_box_definition(box),
            output=output_name,
        )
        page_box_info = await client.query_pdf_info(
            response.output_file,
            queries="page_count",
            extra_body={"queries": "page_boxes"},
        )

    assert response.input_id == uploaded_pdf_for_page_boxes.id
    assert response.output_file.name.startswith(output_name)
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    _assert_box_geometry(page_box_info, box)


@pytest.mark.parametrize(
    ("selector", "selected_page", "unselected_page"),
    [
        pytest.param(1, 1, 2, id="page-number"),
        pytest.param("1-3", 2, 4, id="range"),
        pytest.param("even", 2, 1, id="even"),
        pytest.param("odd", 1, 2, id="odd"),
    ],
)
def test_live_set_pdf_page_boxes_applies_page_selectors(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_multi_page_pdf_for_page_boxes: PdfRestFile,
    selector: PageSelector,
    selected_page: int,
    unselected_page: int,
) -> None:
    definition = PdfInsetPageBoxDefinition(
        box="crop",
        pages=[
            PdfInsetPageBoxPage(
                range=selector,
                top=9,
                bottom=9,
                left=9,
                right=9,
            )
        ],
    )
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        output_file = client.set_pdf_page_boxes(
            uploaded_multi_page_pdf_for_page_boxes,
            boxes=definition,
        ).output_file
        page_box_info = client.query_pdf_info(
            output_file,
            queries="page_count",
            extra_body={"queries": "page_boxes"},
        )

    _assert_crop_selection(
        page_box_info,
        selected_page=selected_page,
        unselected_page=unselected_page,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "selected_page", "unselected_page"),
    [
        pytest.param(1, 1, 2, id="page-number"),
        pytest.param("1-3", 2, 4, id="range"),
        pytest.param("even", 2, 1, id="even"),
        pytest.param("odd", 1, 2, id="odd"),
    ],
)
async def test_live_async_set_pdf_page_boxes_applies_page_selectors(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_multi_page_pdf_for_page_boxes: PdfRestFile,
    selector: PageSelector,
    selected_page: int,
    unselected_page: int,
) -> None:
    definition = PdfInsetPageBoxDefinition(
        box="crop",
        pages=[
            PdfInsetPageBoxPage(
                range=selector,
                top=9,
                bottom=9,
                left=9,
                right=9,
            )
        ],
    )
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        output_file = (
            await client.set_pdf_page_boxes(
                uploaded_multi_page_pdf_for_page_boxes,
                boxes=definition,
            )
        ).output_file
        page_box_info = await client.query_pdf_info(
            output_file,
            queries="page_count",
            extra_body={"queries": "page_boxes"},
        )

    _assert_crop_selection(
        page_box_info,
        selected_page=selected_page,
        unselected_page=unselected_page,
    )


def test_live_set_pdf_page_boxes_accepts_positive_inset_boundary(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_page_boxes: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        output_file = client.set_pdf_page_boxes(
            uploaded_pdf_for_page_boxes,
            boxes=_positive_boundary_definition(),
        ).output_file
        page_box_info = client.query_pdf_info(
            output_file,
            queries="page_count",
            extra_body={"queries": "page_boxes"},
        )

    _assert_positive_boundary_geometry(page_box_info)


@pytest.mark.asyncio
async def test_live_async_set_pdf_page_boxes_accepts_positive_inset_boundary(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_page_boxes: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        output_file = (
            await client.set_pdf_page_boxes(
                uploaded_pdf_for_page_boxes,
                boxes=_positive_boundary_definition(),
            )
        ).output_file
        page_box_info = await client.query_pdf_info(
            output_file,
            queries="page_count",
            extra_body={"queries": "page_boxes"},
        )

    _assert_positive_boundary_geometry(page_box_info)


@pytest.mark.parametrize(
    ("raw_boxes", "match"),
    [
        pytest.param(
            {
                "boxes": [
                    {
                        "box": "media",
                        "pages": [
                            {
                                "range": "5-1",
                                "top": 0,
                                "bottom": 0,
                                "left": 0,
                                "right": 0,
                            }
                        ],
                    }
                ]
            },
            r"The given page range is invalid\. \[5\-1\]\.",
            id="descending-range",
        ),
        pytest.param(
            {
                "boxes": [
                    {
                        "box": "media",
                        "pages": [
                            {
                                "range": "1-3",
                                "top": 0,
                                "bottom": 0,
                                "left": 0,
                                "right": 0,
                            },
                            {
                                "range": "3-4",
                                "top": 0,
                                "bottom": 0,
                                "left": 0,
                                "right": 0,
                            },
                        ],
                    }
                ]
            },
            r"The box page settings conflict with each other",
            id="overlapping-ranges",
        ),
    ],
)
def test_live_set_pdf_page_boxes_rejects_invalid_page_selections(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_multi_page_pdf_for_page_boxes: PdfRestFile,
    raw_boxes: dict[str, Any],
    match: str,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
        ) as client,
        pytest.raises(PdfRestApiError, match=match),
    ):
        client.set_pdf_page_boxes(
            uploaded_multi_page_pdf_for_page_boxes,
            boxes=_box_definition("media"),
            extra_body={"boxes": json.dumps(raw_boxes)},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_boxes", "match"),
    [
        pytest.param(
            {
                "boxes": [
                    {
                        "box": "media",
                        "pages": [
                            {
                                "range": "5-1",
                                "top": 0,
                                "bottom": 0,
                                "left": 0,
                                "right": 0,
                            }
                        ],
                    }
                ]
            },
            r"The given page range is invalid\. \[5\-1\]\.",
            id="descending-range",
        ),
        pytest.param(
            {
                "boxes": [
                    {
                        "box": "media",
                        "pages": [
                            {
                                "range": "1-3",
                                "top": 0,
                                "bottom": 0,
                                "left": 0,
                                "right": 0,
                            },
                            {
                                "range": "3-4",
                                "top": 0,
                                "bottom": 0,
                                "left": 0,
                                "right": 0,
                            },
                        ],
                    }
                ]
            },
            r"The box page settings conflict with each other",
            id="overlapping-ranges",
        ),
    ],
)
async def test_live_async_set_pdf_page_boxes_rejects_invalid_page_selections(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_multi_page_pdf_for_page_boxes: PdfRestFile,
    raw_boxes: dict[str, Any],
    match: str,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        with pytest.raises(PdfRestApiError, match=match):
            await client.set_pdf_page_boxes(
                uploaded_multi_page_pdf_for_page_boxes,
                boxes=_box_definition("media"),
                extra_body={"boxes": json.dumps(raw_boxes)},
            )


def test_live_set_pdf_page_boxes_rejects_unknown_box(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_page_boxes: PdfRestFile,
) -> None:
    invalid_boxes = json.dumps(
        {
            "boxes": [
                {
                    "box": "invalid",
                    "pages": [
                        {
                            "range": "all",
                            "top": 9,
                            "bottom": 9,
                            "left": 9,
                            "right": 9,
                        }
                    ],
                }
            ]
        }
    )
    with (
        PdfRestClient(
            api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)(invalid|box|option)"),
    ):
        client.set_pdf_page_boxes(
            uploaded_pdf_for_page_boxes,
            boxes=_box_definition("media"),
            extra_body={"boxes": invalid_boxes},
        )


@pytest.mark.asyncio
async def test_live_async_set_pdf_page_boxes_rejects_unknown_box(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_page_boxes: PdfRestFile,
) -> None:
    invalid_boxes = json.dumps(
        {
            "boxes": [
                {
                    "box": "invalid",
                    "pages": [
                        {
                            "range": "all",
                            "top": 9,
                            "bottom": 9,
                            "left": 9,
                            "right": 9,
                        }
                    ],
                }
            ]
        }
    )
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)(invalid|box|option)"):
            await client.set_pdf_page_boxes(
                uploaded_pdf_for_page_boxes,
                boxes=_box_definition("media"),
                extra_body={"boxes": invalid_boxes},
            )
