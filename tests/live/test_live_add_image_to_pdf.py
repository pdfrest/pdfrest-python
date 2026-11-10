from __future__ import annotations

from typing import get_args

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile
from pdfrest.types import PdfAddImageObject, PdfContentStructureType

from ..resources import get_test_resource_path

IMAGE_RESOURCE_VARIANTS = (
    pytest.param(("test.jpg", "image/jpeg"), id="jpeg"),
    pytest.param(("test.png", "image/png"), id="png"),
    pytest.param(("test.tif", "image/tiff"), id="tiff"),
    pytest.param(("test.gif", "image/gif"), id="gif"),
)

_UNSUPPORTED_IMAGE_STRUCTURE_TYPES = frozenset({"Ruby", "Warichu"})
_UNSUPPORTED_IMAGE_STRUCTURE_TYPE_REASON = (
    "The deployed image-overlay service returns a fatal 400 for standalone "
    "Ruby and Warichu structure elements."
)

CONTENT_STRUCTURE_TYPE_CASES = tuple(
    pytest.param(
        value,
        marks=(
            pytest.mark.xfail(
                raises=PdfRestApiError,
                reason=_UNSUPPORTED_IMAGE_STRUCTURE_TYPE_REASON,
                strict=True,
            )
            if value in _UNSUPPORTED_IMAGE_STRUCTURE_TYPES
            else ()
        ),
        id=value,
    )
    for value in get_args(PdfContentStructureType)
)


@pytest.fixture(scope="module")
def uploaded_pdf_for_image_addition(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module", params=IMAGE_RESOURCE_VARIANTS)
def uploaded_image_variant(
    request: pytest.FixtureRequest,
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource_name, expected_mime = request.param
    resource = get_test_resource_path(resource_name)
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded_image = client.files.create_from_paths([resource])[0]

    assert uploaded_image.type == expected_mime
    return uploaded_image


@pytest.fixture(scope="module")
def uploaded_batch_images(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> tuple[PdfRestFile, PdfRestFile]:
    resources = [
        get_test_resource_path("test.png"),
        get_test_resource_path("test.jpg"),
    ]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded_images = client.files.create_from_paths(resources)

    assert [image.type for image in uploaded_images] == ["image/png", "image/jpeg"]
    return uploaded_images[0], uploaded_images[1]


def test_live_add_image_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_image_variant: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_image_to_pdf(
            uploaded_pdf_for_image_addition,
            image=uploaded_image_variant,
            x=25,
            y=50,
            page=1,
            width=72,
            height=36,
            tag_enabled=True,
            tag_language="en-US",
            tag_alt_text="Test image",
            tag_structure_type="Figure",
            output="live-added-image",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.name.startswith("live-added-image")
    assert output_file.size > 0
    assert response.warning is None
    assert uploaded_pdf_for_image_addition.id in response.input_ids
    assert uploaded_image_variant.id in response.input_ids


@pytest.mark.asyncio
async def test_live_async_add_image_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_image_variant: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_image_to_pdf(
            uploaded_pdf_for_image_addition,
            image=uploaded_image_variant,
            x=75,
            y=125,
            page=1,
            width=36,
            tag_enabled=True,
            tag_is_artifact=True,
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert uploaded_pdf_for_image_addition.id in response.input_ids
    assert uploaded_image_variant.id in response.input_ids


def test_live_add_images_to_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    first_image, second_image = uploaded_batch_images
    image_objects: list[PdfAddImageObject] = [
        PdfAddImageObject(
            image=first_image,
            page="1-last",
            x=25,
            y=50,
            width=72,
            tag_alt_text="Primary test image",
            tag_structure_type="Figure",
        ),
        PdfAddImageObject(
            image=second_image,
            page=1,
            x=125,
            y=50,
            height=36,
            tag_is_artifact=False,
        ),
    ]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=image_objects,
            tag_enabled=True,
            tag_language="en-US",
            output="live-added-images",
        )

    assert len(response.output_files) == 1
    assert response.output_file.type == "application/pdf"
    assert response.output_file.name.startswith("live-added-images")
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    assert response.input_ids == [
        uploaded_pdf_for_image_addition.id,
        first_image.id,
        second_image.id,
    ]


@pytest.mark.asyncio
async def test_live_async_add_images_to_pdf_reuses_uploaded_image(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    first_image, _ = uploaded_batch_images
    image_objects: list[PdfAddImageObject] = [
        PdfAddImageObject(image=first_image, page="all", x=25, y=50, width=72),
        PdfAddImageObject(image=first_image, page=1, x=125, y=50, width=36),
    ]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=image_objects,
            output="live-reused-image",
        )

    assert len(response.output_files) == 1
    assert response.output_file.type == "application/pdf"
    assert response.output_file.name.startswith("live-reused-image")
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    assert response.input_ids == [uploaded_pdf_for_image_addition.id, first_image.id]


def test_live_add_image_to_pdf_invalid_page(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_image_variant: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)page"),
    ):
        client.add_image_to_pdf(
            uploaded_pdf_for_image_addition,
            image=uploaded_image_variant,
            x=0,
            y=0,
            page=1,
            extra_body={"page": 0},
        )


@pytest.mark.asyncio
async def test_live_async_add_image_to_pdf_invalid_page(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_image_variant: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            await client.add_image_to_pdf(
                uploaded_pdf_for_image_addition,
                image=uploaded_image_variant,
                x=0,
                y=0,
                page=1,
                extra_body={"page": 0},
            )


def test_live_add_images_to_pdf_invalid_page_expression(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    image, _ = uploaded_batch_images
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)page"),
    ):
        client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(image=image, page=1, x=0, y=0),
            extra_body={
                "image_objects": [
                    {
                        "image_id": str(image.id),
                        "page": "last-2",
                        "x": 0,
                        "y": 0,
                    }
                ]
            },
        )


def test_live_add_images_to_pdf_invalid_tag_dependency(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    image, _ = uploaded_batch_images
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)tag_enabled"),
    ):
        client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(
                image=image,
                page=1,
                x=0,
                y=0,
                tag_alt_text="Test image",
            ),
            tag_enabled=True,
            extra_body={"tag_enabled": False},
        )


@pytest.mark.asyncio
async def test_live_async_add_images_to_pdf_invalid_page_expression(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    image, _ = uploaded_batch_images
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            await client.add_images_to_pdf(
                uploaded_pdf_for_image_addition,
                image_objects=PdfAddImageObject(image=image, page=1, x=0, y=0),
                extra_body={
                    "image_objects": [
                        {
                            "image_id": str(image.id),
                            "page": "last-2",
                            "x": 0,
                            "y": 0,
                        }
                    ]
                },
            )


@pytest.mark.asyncio
async def test_live_async_add_images_to_pdf_invalid_tag_dependency(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    image, _ = uploaded_batch_images
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)tag_enabled"):
            await client.add_images_to_pdf(
                uploaded_pdf_for_image_addition,
                image_objects=PdfAddImageObject(
                    image=image,
                    page=1,
                    x=0,
                    y=0,
                    tag_alt_text="Test image",
                ),
                tag_enabled=True,
                extra_body={"tag_enabled": False},
            )


def test_live_add_images_to_pdf_single_object_mime_contract(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_image_variant: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(
                image=uploaded_image_variant,
                page=1,
                x=0,
                y=0,
            ),
            output="live-single-image-object",
        )

    assert len(response.output_files) == 1
    assert response.output_file.type == "application/pdf"
    assert response.output_file.name.startswith("live-single-image-object")
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    assert response.input_ids == [
        uploaded_pdf_for_image_addition.id,
        uploaded_image_variant.id,
    ]


@pytest.mark.asyncio
async def test_live_async_add_images_to_pdf_single_object_mime_contract(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_image_variant: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(
                image=uploaded_image_variant,
                page=1,
                x=0,
                y=0,
            ),
            output="live-async-single-image-object",
        )

    assert len(response.output_files) == 1
    assert response.output_file.type == "application/pdf"
    assert response.output_file.name.startswith("live-async-single-image-object")
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    assert response.input_ids == [
        uploaded_pdf_for_image_addition.id,
        uploaded_image_variant.id,
    ]


@pytest.mark.parametrize("structure_type", CONTENT_STRUCTURE_TYPE_CASES)
def test_live_add_images_to_pdf_structure_type_contract(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
    structure_type: PdfContentStructureType,
) -> None:
    image, _ = uploaded_batch_images
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(
                image=image,
                page=1,
                x=0,
                y=0,
                tag_structure_type=structure_type,
            ),
            tag_enabled=True,
            output="live-image-structure-type",
        )

    assert len(response.output_files) == 1
    assert response.output_file.type == "application/pdf"
    assert response.output_file.name.startswith("live-image-structure-type")
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    assert response.input_ids == [uploaded_pdf_for_image_addition.id, image.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("structure_type", CONTENT_STRUCTURE_TYPE_CASES)
async def test_live_async_add_images_to_pdf_structure_type_contract(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
    structure_type: PdfContentStructureType,
) -> None:
    image, _ = uploaded_batch_images
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(
                image=image,
                page=1,
                x=0,
                y=0,
                tag_structure_type=structure_type,
            ),
            tag_enabled=True,
            output="live-async-image-structure-type",
        )

    assert len(response.output_files) == 1
    assert response.output_file.type == "application/pdf"
    assert response.output_file.name.startswith("live-async-image-structure-type")
    assert response.output_file.size > 0
    assert response.output_file.url
    assert response.warning is None
    assert response.input_ids == [uploaded_pdf_for_image_addition.id, image.id]


def test_live_add_images_to_pdf_invalid_structure_type(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    image, _ = uploaded_batch_images
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)tag_structure_type|structure"),
    ):
        client.add_images_to_pdf(
            uploaded_pdf_for_image_addition,
            image_objects=PdfAddImageObject(image=image, page=1, x=0, y=0),
            tag_enabled=True,
            extra_body={
                "image_objects": [
                    {
                        "image_id": str(image.id),
                        "page": 1,
                        "x": 0,
                        "y": 0,
                        "tag_structure_type": "DefinitelyNotAStructureType",
                    }
                ]
            },
        )


@pytest.mark.asyncio
async def test_live_async_add_images_to_pdf_invalid_structure_type(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_image_addition: PdfRestFile,
    uploaded_batch_images: tuple[PdfRestFile, PdfRestFile],
) -> None:
    image, _ = uploaded_batch_images
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)tag_structure_type|structure"):
            await client.add_images_to_pdf(
                uploaded_pdf_for_image_addition,
                image_objects=PdfAddImageObject(image=image, page=1, x=0, y=0),
                tag_enabled=True,
                extra_body={
                    "image_objects": [
                        {
                            "image_id": str(image.id),
                            "page": 1,
                            "x": 0,
                            "y": 0,
                            "tag_structure_type": "DefinitelyNotAStructureType",
                        }
                    ]
                },
            )
