from __future__ import annotations

from typing import cast, get_args

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile
from pdfrest.types import PdfPresetColorProfile, PdfRenderingIntent

from ..resources import get_test_resource_path

ALL_COLOR_PROFILES: tuple[PdfPresetColorProfile, ...] = cast(
    tuple[PdfPresetColorProfile, ...],
    get_args(PdfPresetColorProfile),
)
ALL_RENDERING_INTENTS: tuple[PdfRenderingIntent, ...] = cast(
    tuple[PdfRenderingIntent, ...],
    get_args(PdfRenderingIntent),
)


@pytest.fixture(scope="module")
def uploaded_pdf_for_color_conversion(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def uploaded_custom_profile_for_color_conversion(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("custom.icc")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.mark.parametrize(
    "color_profile",
    [
        pytest.param(color_profile, id=f"color-profile-{color_profile}")
        for color_profile in ALL_COLOR_PROFILES
    ],
)
def test_live_convert_colors_color_profiles_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
    color_profile: PdfPresetColorProfile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile=color_profile,
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_color_conversion.id)


@pytest.mark.parametrize(
    "rendering_intent",
    [
        pytest.param(rendering_intent, id=f"rendering-intent-{rendering_intent}")
        for rendering_intent in ALL_RENDERING_INTENTS
    ],
)
def test_live_convert_colors_rendering_intents_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
    rendering_intent: PdfRenderingIntent,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile="srgb",
            rendering_intent=rendering_intent,
        )

    assert len(response.output_files) == 1
    output_file = response.output_file
    assert output_file.name.endswith(".pdf")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert str(output_file.id) in str(output_file.url)
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_color_conversion.id)


def test_live_convert_colors_custom_profile_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    pdf_resource = get_test_resource_path("report.pdf")
    profile_resource = get_test_resource_path("custom.icc")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded_pdf = client.files.create_from_paths([pdf_resource])[0]
        uploaded_profile = client.files.create_from_paths([profile_resource])[0]
        response = client.convert_colors(
            uploaded_pdf,
            color_profile=uploaded_profile,
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    input_ids = {str(file_id) for file_id in response.input_ids}
    assert str(uploaded_pdf.id) in input_ids
    assert str(uploaded_profile.id) in input_ids


@pytest.mark.parametrize(
    "output_name",
    [
        pytest.param(None, id="default-output"),
        pytest.param("converted-colors", id="custom-output"),
    ],
)
def test_live_convert_colors_output_prefix(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
    output_name: str | None,
) -> None:
    kwargs: dict[str, str] = {"color_profile": "srgb"}
    if output_name is not None:
        kwargs["output"] = output_name

    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_colors(uploaded_pdf_for_color_conversion, **kwargs)

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_color_conversion.id)
    if output_name is not None:
        assert output_file.name.startswith(output_name)
    else:
        assert output_file.name.endswith(".pdf")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "color_profile",
    [
        pytest.param(color_profile, id=f"color-profile-{color_profile}")
        for color_profile in ALL_COLOR_PROFILES
    ],
)
async def test_live_async_convert_colors_color_profiles_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
    color_profile: PdfPresetColorProfile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile=color_profile,
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_color_conversion.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rendering_intent",
    [
        pytest.param(rendering_intent, id=f"rendering-intent-{rendering_intent}")
        for rendering_intent in ALL_RENDERING_INTENTS
    ],
)
async def test_live_async_convert_colors_rendering_intents_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
    rendering_intent: PdfRenderingIntent,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile="srgb",
            rendering_intent=rendering_intent,
        )

    assert len(response.output_files) == 1
    output_file = response.output_file
    assert output_file.name.endswith(".pdf")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert str(output_file.id) in str(output_file.url)
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_color_conversion.id)


@pytest.mark.asyncio
async def test_live_async_convert_colors_custom_profile_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    pdf_resource = get_test_resource_path("report.pdf")
    profile_resource = get_test_resource_path("custom.icc")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded_pdf = (await client.files.create_from_paths([pdf_resource]))[0]
        uploaded_profile = (await client.files.create_from_paths([profile_resource]))[0]
        response = await client.convert_colors(
            uploaded_pdf,
            color_profile=uploaded_profile,
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    input_ids = {str(file_id) for file_id in response.input_ids}
    assert str(uploaded_pdf.id) in input_ids
    assert str(uploaded_profile.id) in input_ids


@pytest.mark.asyncio
async def test_live_async_convert_colors_output_prefix(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile="srgb",
            output="async",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_color_conversion.id)


def test_live_convert_colors_invalid_color_profile(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)(color|profile)"),
    ):
        client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile="srgb",
            extra_body={"color_profile": "not-a-color-profile"},
        )


@pytest.mark.asyncio
async def test_live_async_convert_colors_invalid_color_profile(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)(color|profile)"):
            await client.convert_colors(
                uploaded_pdf_for_color_conversion,
                color_profile="srgb",
                extra_body={"color_profile": "not-a-color-profile"},
            )


def test_live_convert_colors_invalid_rendering_intent(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)(rendering|intent)"),
    ):
        client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile="srgb",
            extra_body={"rendering_intent": "not-an-intent"},
        )


@pytest.mark.asyncio
async def test_live_async_convert_colors_invalid_rendering_intent(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)(rendering|intent)"):
            await client.convert_colors(
                uploaded_pdf_for_color_conversion,
                color_profile="srgb",
                extra_body={"rendering_intent": "not-an-intent"},
            )


def test_live_convert_colors_invalid_file_id(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)(id|file)"),
    ):
        client.convert_colors(
            uploaded_pdf_for_color_conversion,
            color_profile="srgb",
            extra_body={"id": "00000000-0000-0000-0000-000000000000"},
        )


@pytest.mark.asyncio
async def test_live_async_convert_colors_invalid_file_id(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_color_conversion: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)(id|file)"):
            await client.convert_colors(
                uploaded_pdf_for_color_conversion,
                color_profile="srgb",
                extra_body={"id": "ffffffff-ffff-ffff-ffff-ffffffffffff"},
            )
