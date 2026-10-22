from __future__ import annotations

from typing import TypedDict, cast, get_args

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile
from pdfrest.models._internal import ConvertPdfToPostscriptPayload
from pdfrest.types import PostScriptLevel

from ..resources import get_test_resource_path

POSTSCRIPT_LEVELS = cast(
    tuple[PostScriptLevel, ...],
    get_args(ConvertPdfToPostscriptPayload.model_fields["ps_level"].annotation),
)
SCALE_SCHEMA = ConvertPdfToPostscriptPayload.model_json_schema()["properties"]["scale"]
SCALE_EXCLUSIVE_MINIMUM = cast(float, SCALE_SCHEMA["exclusiveMinimum"])
SCALE_NEAR_BOUNDARY = SCALE_EXCLUSIVE_MINIMUM + 0.0001


class PostscriptLiveOptions(TypedDict, total=False):
    binary_output: bool
    scale: float
    output: str


POSTSCRIPT_OPTION_CASES = [
    pytest.param(
        PostscriptLiveOptions(binary_output=False),
        "report_pdfrest_postscript",
        b"%%DocumentData: Clean7Bit",
        id="text-safe-output",
    ),
    pytest.param(
        PostscriptLiveOptions(scale=SCALE_NEAR_BOUNDARY),
        "report_pdfrest_postscript",
        b"%%BoundingBox: 305 395 307 397",
        id="scale-near-exclusive-minimum",
    ),
    pytest.param(
        PostscriptLiveOptions(output="live-postscript-custom"),
        "live-postscript-custom",
        None,
        id="custom-output",
    ),
]


def _postscript_level_id(ps_level: PostScriptLevel) -> str:
    return f"level-{ps_level}"


@pytest.fixture(scope="module")
def uploaded_pdf_for_postscript(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("20-pages.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths(resource)[0]


@pytest.fixture(scope="module")
def uploaded_single_page_pdf_for_postscript(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths(resource)[0]


@pytest.fixture(scope="module")
def uploaded_annotated_pdf_for_postscript(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("printable-annotation.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths(resource)[0]


def _normalize_postscript_for_comparison(output_bytes: bytes) -> bytes:
    return b"\n".join(
        line
        for line in output_bytes.splitlines()
        if not line.startswith(b"%%CreationDate:")
    )


def _assert_postscript_response(
    output: PdfRestFile,
    output_bytes: bytes,
    output_prefix: str,
    ps_level: PostScriptLevel,
    expected_pages: int,
) -> None:
    assert output.name.startswith(output_prefix)
    assert output.name.endswith(".ps")
    assert output.type == "application/postscript"
    assert output.size == len(output_bytes)
    assert output.size > 0
    assert f"/resource/{output.id}" in str(output.url)
    assert output_bytes.startswith(b"%!PS-Adobe")
    assert f"%%LanguageLevel: {ps_level}".encode() in output_bytes.splitlines()
    assert output_bytes.count(b"%%Page:") == expected_pages


@pytest.mark.parametrize(
    "ps_level",
    POSTSCRIPT_LEVELS,
    ids=_postscript_level_id,
)
def test_live_convert_pdf_to_postscript_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_single_page_pdf_for_postscript: PdfRestFile,
    ps_level: PostScriptLevel,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_pdf_to_postscript(
            uploaded_single_page_pdf_for_postscript,
            ps_level=ps_level,
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert str(response.input_id) == str(uploaded_single_page_pdf_for_postscript.id)
    assert response.warning is None
    _assert_postscript_response(
        response.output_file,
        output_bytes,
        "report_pdfrest_postscript",
        ps_level,
        1,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ps_level",
    POSTSCRIPT_LEVELS,
    ids=_postscript_level_id,
)
async def test_live_async_convert_pdf_to_postscript_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_single_page_pdf_for_postscript: PdfRestFile,
    ps_level: PostScriptLevel,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_pdf_to_postscript(
            uploaded_single_page_pdf_for_postscript,
            ps_level=ps_level,
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert str(response.input_id) == str(uploaded_single_page_pdf_for_postscript.id)
    assert response.warning is None
    _assert_postscript_response(
        response.output_file,
        output_bytes,
        "report_pdfrest_postscript",
        ps_level,
        1,
    )


def test_live_convert_pdf_to_postscript_page_range(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_pdf_to_postscript(
            uploaded_pdf_for_postscript,
            page_range="2-3",
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert str(response.input_id) == str(uploaded_pdf_for_postscript.id)
    assert response.warning is None
    _assert_postscript_response(
        response.output_file,
        output_bytes,
        "20-pages_pdfrest_postscript",
        3,
        2,
    )


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_postscript_page_range(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_pdf_to_postscript(
            uploaded_pdf_for_postscript,
            page_range="4-5",
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert str(response.input_id) == str(uploaded_pdf_for_postscript.id)
    assert response.warning is None
    _assert_postscript_response(
        response.output_file,
        output_bytes,
        "20-pages_pdfrest_postscript",
        3,
        2,
    )


def test_live_convert_pdf_to_postscript_print_annotations(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_annotated_pdf_for_postscript: PdfRestFile,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with_annotations = client.convert_pdf_to_postscript(
            uploaded_annotated_pdf_for_postscript,
            binary_output=False,
            print_annotations=True,
        )
        with_annotations_bytes = client.files.read_bytes(with_annotations.output_file)
        without_annotations = client.convert_pdf_to_postscript(
            uploaded_annotated_pdf_for_postscript,
            binary_output=False,
            print_annotations=False,
        )
        without_annotations_bytes = client.files.read_bytes(
            without_annotations.output_file
        )

    assert str(with_annotations.input_id) == str(
        uploaded_annotated_pdf_for_postscript.id
    )
    assert str(without_annotations.input_id) == str(
        uploaded_annotated_pdf_for_postscript.id
    )
    assert with_annotations.warning is None
    assert without_annotations.warning is None
    _assert_postscript_response(
        with_annotations.output_file,
        with_annotations_bytes,
        "printable-annotation_pdfrest_postscript",
        3,
        1,
    )
    _assert_postscript_response(
        without_annotations.output_file,
        without_annotations_bytes,
        "printable-annotation_pdfrest_postscript",
        3,
        1,
    )
    assert _normalize_postscript_for_comparison(
        with_annotations_bytes
    ) != _normalize_postscript_for_comparison(without_annotations_bytes)


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_postscript_print_annotations(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_annotated_pdf_for_postscript: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with_annotations = await client.convert_pdf_to_postscript(
            uploaded_annotated_pdf_for_postscript,
            binary_output=False,
            print_annotations=True,
        )
        with_annotations_bytes = await client.files.read_bytes(
            with_annotations.output_file
        )
        without_annotations = await client.convert_pdf_to_postscript(
            uploaded_annotated_pdf_for_postscript,
            binary_output=False,
            print_annotations=False,
        )
        without_annotations_bytes = await client.files.read_bytes(
            without_annotations.output_file
        )

    assert str(with_annotations.input_id) == str(
        uploaded_annotated_pdf_for_postscript.id
    )
    assert str(without_annotations.input_id) == str(
        uploaded_annotated_pdf_for_postscript.id
    )
    assert with_annotations.warning is None
    assert without_annotations.warning is None
    _assert_postscript_response(
        with_annotations.output_file,
        with_annotations_bytes,
        "printable-annotation_pdfrest_postscript",
        3,
        1,
    )
    _assert_postscript_response(
        without_annotations.output_file,
        without_annotations_bytes,
        "printable-annotation_pdfrest_postscript",
        3,
        1,
    )
    assert _normalize_postscript_for_comparison(
        with_annotations_bytes
    ) != _normalize_postscript_for_comparison(without_annotations_bytes)


@pytest.mark.parametrize(
    ("options", "output_prefix", "expected_marker"),
    POSTSCRIPT_OPTION_CASES,
)
def test_live_convert_pdf_to_postscript_options(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_single_page_pdf_for_postscript: PdfRestFile,
    options: PostscriptLiveOptions,
    output_prefix: str,
    expected_marker: bytes | None,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_pdf_to_postscript(
            uploaded_single_page_pdf_for_postscript,
            **options,
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert str(response.input_id) == str(uploaded_single_page_pdf_for_postscript.id)
    assert response.warning is None
    _assert_postscript_response(
        response.output_file,
        output_bytes,
        output_prefix,
        3,
        1,
    )
    if expected_marker is not None:
        assert expected_marker in output_bytes.splitlines()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "output_prefix", "expected_marker"),
    POSTSCRIPT_OPTION_CASES,
)
async def test_live_async_convert_pdf_to_postscript_options(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_single_page_pdf_for_postscript: PdfRestFile,
    options: PostscriptLiveOptions,
    output_prefix: str,
    expected_marker: bytes | None,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_pdf_to_postscript(
            uploaded_single_page_pdf_for_postscript,
            **options,
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert str(response.input_id) == str(uploaded_single_page_pdf_for_postscript.id)
    assert response.warning is None
    _assert_postscript_response(
        response.output_file,
        output_bytes,
        output_prefix,
        3,
        1,
    )
    if expected_marker is not None:
        assert expected_marker in output_bytes.splitlines()


def test_live_convert_pdf_to_postscript_rejects_invalid_level(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match="ps_level must be 2 or 3"),
    ):
        client.convert_pdf_to_postscript(
            uploaded_pdf_for_postscript,
            extra_body={"ps_level": 4},
        )


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_postscript_rejects_invalid_level(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match="ps_level must be 2 or 3"):
            await client.convert_pdf_to_postscript(
                uploaded_pdf_for_postscript,
                extra_body={"ps_level": 4},
            )


def test_live_convert_pdf_to_postscript_rejects_invalid_page_range(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match="invalid page range"),
    ):
        client.convert_pdf_to_postscript(
            uploaded_pdf_for_postscript,
            extra_body={"page_range": "1,,3"},
        )


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_postscript_rejects_invalid_page_range(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match="invalid page range"):
            await client.convert_pdf_to_postscript(
                uploaded_pdf_for_postscript,
                extra_body={"page_range": "1,,3"},
            )


def test_live_convert_pdf_to_postscript_rejects_invalid_scale(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match="scale must be greater than zero"),
    ):
        client.convert_pdf_to_postscript(
            uploaded_pdf_for_postscript,
            extra_body={"scale": SCALE_EXCLUSIVE_MINIMUM},
        )


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_postscript_rejects_invalid_scale(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_postscript: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError,
            match="scale must be greater than zero",
        ):
            await client.convert_pdf_to_postscript(
                uploaded_pdf_for_postscript,
                extra_body={"scale": SCALE_EXCLUSIVE_MINIMUM},
            )
