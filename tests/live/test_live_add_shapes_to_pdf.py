from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile

from ..resources import get_test_resource_path


@pytest.fixture(scope="module")
def uploaded_pdf_for_shape_addition(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([get_test_resource_path("report.pdf")])[0]


def _line() -> dict[str, object]:
    return {
        "type": "line",
        "page": 1,
        "x1": 72,
        "y1": 576,
        "x2": 540,
        "y2": 576,
        "stroke_color": (26, 72, 112),
        "stroke_width": 1.5,
    }


def _rectangle() -> dict[str, object]:
    return {
        "type": "rectangle",
        "page": "all",
        "x": 54,
        "y": 540,
        "width": 504,
        "height": 108,
        "fill_color": (0, 0, 0, 12),
        "opacity": 0.75,
    }


def _server_line() -> dict[str, object]:
    line = _line()
    line["stroke_color_rgb"] = "26,72,112"
    del line["stroke_color"]
    return line


def _server_rectangle() -> dict[str, object]:
    rectangle = _rectangle()
    rectangle["fill_color_cmyk"] = "0,0,0,12"
    del rectangle["fill_color"]
    return rectangle


def test_live_add_shapes_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_shape_addition: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_shapes_to_pdf(
            uploaded_pdf_for_shape_addition,
            shape_objects=[_line(), _rectangle()],
            output="live-added-shapes",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.name.startswith("live-added-shapes")
    assert output_file.size > 0
    assert response.warning is None
    assert uploaded_pdf_for_shape_addition.id in response.input_ids


@pytest.mark.asyncio
async def test_live_async_add_shapes_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_shape_addition: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_shapes_to_pdf(
            uploaded_pdf_for_shape_addition,
            shape_objects={
                **_rectangle(),
                "tag_actual_text": "Decorative panel",
                "tag_structure_type": "Figure",
            },
            tag_enabled=True,
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert uploaded_pdf_for_shape_addition.id in response.input_ids


def test_live_add_shapes_to_pdf_invalid_page(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_shape_addition: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)page"),
    ):
        client.add_shapes_to_pdf(
            uploaded_pdf_for_shape_addition,
            shape_objects=_line(),
            extra_body={
                "shape_objects": [
                    {
                        **_server_line(),
                        "page": 0,
                    }
                ]
            },
        )


@pytest.mark.asyncio
async def test_live_async_add_shapes_to_pdf_invalid_page(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_shape_addition: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            await client.add_shapes_to_pdf(
                uploaded_pdf_for_shape_addition,
                shape_objects=_rectangle(),
                extra_body={
                    "shape_objects": [
                        {
                            **_server_rectangle(),
                            "page": 0,
                        }
                    ]
                },
            )
