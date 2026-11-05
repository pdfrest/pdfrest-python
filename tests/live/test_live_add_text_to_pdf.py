from __future__ import annotations

import pytest
from pydantic_core import to_json

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile

from ..resources import get_test_resource_path


@pytest.fixture(scope="module")
def uploaded_pdf_for_text(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


def _default_text_object() -> dict[str, object]:
    return {
        "font": "courier",
        "max_width": 200,
        "opacity": 1,
        "page": 1,
        "rotation": 0,
        "text": "Live add text",
        "text_color_rgb": (0, 0, 0),
        "text_size": 14,
        "x": 72,
        "y": 144,
    }


def _serialize_text_object_for_extra_body(
    text_object: dict[str, object],
) -> dict[str, object]:
    serialized = dict(text_object)
    # PdfAddTextObjectModel coercion: numeric placement/size fields are floats on
    # serialization even when callers provide integers.
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
    # Match add-text wire format where each non-string value is JSON-quoted.
    for key, value in list(serialized.items()):
        if not isinstance(value, str):
            serialized[key] = to_json(value).decode()
    return serialized


def test_live_add_text_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_text: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_text_to_pdf(
            uploaded_pdf_for_text,
            text_objects=[_default_text_object()],
            tag_enabled=True,
            tag_language="en-US",
            output="live-added-text",
        )
        tagged_info = client.query_pdf_info(response.output_file, queries="tagged")

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.name.startswith("live-added-text")
    assert output_file.size > 0
    assert response.warning is None
    assert uploaded_pdf_for_text.id in response.input_ids
    assert tagged_info.tagged is True


@pytest.mark.asyncio
async def test_live_async_add_text_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_text: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_text_to_pdf(
            uploaded_pdf_for_text,
            text_objects=[_default_text_object()],
            tag_enabled=True,
            tag_language="en-US",
        )
        tagged_info = await client.query_pdf_info(
            response.output_file,
            queries="tagged",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert uploaded_pdf_for_text.id in response.input_ids
    assert tagged_info.tagged is True


def test_live_add_text_to_pdf_invalid_page(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_text: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)page"),
    ):
        client.add_text_to_pdf(
            uploaded_pdf_for_text,
            text_objects=[_default_text_object()],
            extra_body={
                "text_objects": to_json(
                    [
                        _serialize_text_object_for_extra_body(
                            {
                                **_default_text_object(),
                                "page": 0,
                            }
                        )
                    ]
                ).decode()
            },
        )


@pytest.mark.asyncio
async def test_live_async_add_text_to_pdf_invalid_page(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_text: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            await client.add_text_to_pdf(
                uploaded_pdf_for_text,
                text_objects=[_default_text_object()],
                extra_body={
                    "text_objects": to_json(
                        [
                            _serialize_text_object_for_extra_body(
                                {
                                    **_default_text_object(),
                                    "page": 0,
                                }
                            )
                        ]
                    ).decode()
                },
            )
