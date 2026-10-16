from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple, get_args

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile
from pdfrest.models._internal import (
    BasePdfRestGraphicPayload,
    BmpPdfRestPayload,
    GifPdfRestPayload,
    JpegPdfRestPayload,
    PngPdfRestPayload,
    TiffPdfRestPayload,
)

from ..resources import get_test_resource_path


class _GraphicEndpointSpec(NamedTuple):
    method_name: str
    payload_model: type[BasePdfRestGraphicPayload[Any]]


PNG_PAYLOAD_ONLY: dict[str, _GraphicEndpointSpec] = {
    "png": _GraphicEndpointSpec("convert_to_png", PngPdfRestPayload),
}

PAYLOAD_MODELS: dict[str, _GraphicEndpointSpec] = {
    **PNG_PAYLOAD_ONLY,
    "bmp": _GraphicEndpointSpec("convert_to_bmp", BmpPdfRestPayload),
    "gif": _GraphicEndpointSpec("convert_to_gif", GifPdfRestPayload),
    "jpeg": _GraphicEndpointSpec("convert_to_jpeg", JpegPdfRestPayload),
    "tiff": _GraphicEndpointSpec("convert_to_tiff", TiffPdfRestPayload),
}

_EXPECTED_FILE_FORMATS: dict[str, tuple[str, str]] = {
    "png": ("image/png", ".png"),
    "bmp": ("image/bmp", ".bmp"),
    "gif": ("image/gif", ".gif"),
    "jpeg": ("image/jpeg", ".jpg"),
    "tiff": ("image/tiff", ".tif"),
}
_GRAPHIC_PASSWORD = "graphic-password"  # noqa: S105 - Test-only password.
_WRONG_GRAPHIC_PASSWORD = "wrong-password"  # noqa: S105 - Test-only password.


def _enumerate_color_models(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
) -> Iterable[str]:
    field = payload_model.model_fields["color_model"]
    return get_args(field.annotation) or ()


def _resolution_bounds(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
) -> tuple[int, int]:
    field = payload_model.model_fields["resolution"]
    ge = field.metadata[0].ge if field.metadata else 12
    le = field.metadata[1].le if len(field.metadata) > 1 else 2400
    return int(ge), int(le)


def _valid_color_cases() -> list[Any]:
    cases = []
    for label, spec in PAYLOAD_MODELS.items():
        for color_model in _enumerate_color_models(spec.payload_model):
            cases.append(
                pytest.param(label, spec, color_model, id=f"{label}-{color_model}")
            )
    return cases


def _invalid_color_cases() -> list[Any]:
    cases = []
    candidates = ("lab", "rgba", "cmyk", "xyz", "ultraviolet", "infrared-spectrum")
    for label, spec in PAYLOAD_MODELS.items():
        allowed = set(_enumerate_color_models(spec.payload_model))
        seen: set[str] = set()
        for value in (*candidates, "not-a-color-model"):
            if value in allowed or value in seen:
                continue
            seen.add(value)
            cases.append(pytest.param(label, spec, value, id=f"{label}-{value}"))
    return cases


_SMOOTHING_VALUES: tuple[str, ...] = ("none", "all", "text", "line", "image")


def _valid_smoothing_cases() -> list[Any]:
    cases = []
    for label, spec in PAYLOAD_MODELS.items():
        for smoothing in _SMOOTHING_VALUES:
            cases.append(
                pytest.param(label, spec, smoothing, id=f"{label}-{smoothing}")
            )
    return cases


def _invalid_smoothing_cases() -> list[Any]:
    cases = []
    invalid_inputs: tuple[Any, ...] = (
        "quantum",
        "super-smooth",
        "line, hyperreal",
    )
    for label, spec in PAYLOAD_MODELS.items():
        for candidate in invalid_inputs:
            case_id = (
                f"{label}-{'-'.join(candidate)}"
                if isinstance(candidate, list)
                else f"{label}-{candidate}"
            )
            cases.append(pytest.param(label, spec, candidate, id=case_id))
    return cases


def _expected_file_format(label: str) -> tuple[str, str]:
    return _EXPECTED_FILE_FORMATS[label]


def _assert_output_files(
    output_files: Sequence[PdfRestFile],
    *,
    expected_mime: str,
    expected_suffix: str,
) -> None:
    assert output_files
    assert all(file_info.name.endswith(expected_suffix) for file_info in output_files)
    assert all(file_info.type == expected_mime for file_info in output_files)
    assert all(file_info.size > 0 for file_info in output_files)


@pytest.fixture(scope="module")
def uploaded_20_page_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("20-pages.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.fixture(scope="module")
def encrypted_pdf_for_graphics(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        return client.add_open_password(
            uploaded,
            new_open_password=_GRAPHIC_PASSWORD,
            output="graphic-password-source",
        ).output_file


@pytest.mark.parametrize(
    ("endpoint_label", "spec"),
    PAYLOAD_MODELS.items(),
    ids=list(PAYLOAD_MODELS),
)
def test_live_graphic_password(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    encrypted_pdf_for_graphics: PdfRestFile,
    endpoint_label: str,
    spec: _GraphicEndpointSpec,
) -> None:
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        client_method = getattr(client, spec.method_name)
        response = client_method(
            encrypted_pdf_for_graphics,
            password=_GRAPHIC_PASSWORD,
            output_prefix=f"live-password-{endpoint_label}",
        )

    expected_mime, expected_suffix = _expected_file_format(endpoint_label)
    _assert_output_files(
        response.output_files,
        expected_mime=expected_mime,
        expected_suffix=expected_suffix,
    )
    assert str(response.input_id) == str(encrypted_pdf_for_graphics.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint_label", "spec"),
    PAYLOAD_MODELS.items(),
    ids=list(PAYLOAD_MODELS),
)
async def test_live_async_graphic_password(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    encrypted_pdf_for_graphics: PdfRestFile,
    endpoint_label: str,
    spec: _GraphicEndpointSpec,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        client_method = getattr(client, spec.method_name)
        response = await client_method(
            encrypted_pdf_for_graphics,
            password=_GRAPHIC_PASSWORD,
            output_prefix=f"live-async-password-{endpoint_label}",
        )

    expected_mime, expected_suffix = _expected_file_format(endpoint_label)
    _assert_output_files(
        response.output_files,
        expected_mime=expected_mime,
        expected_suffix=expected_suffix,
    )
    assert str(response.input_id) == str(encrypted_pdf_for_graphics.id)


def test_live_graphic_invalid_password(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    encrypted_pdf_for_graphics: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)password"),
    ):
        client.convert_to_png(
            encrypted_pdf_for_graphics,
            password=_WRONG_GRAPHIC_PASSWORD,
        )


@pytest.mark.asyncio
async def test_live_async_graphic_invalid_password(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    encrypted_pdf_for_graphics: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)password"):
            await client.convert_to_png(
                encrypted_pdf_for_graphics,
                password=_WRONG_GRAPHIC_PASSWORD,
            )


def test_live_convert_to_png_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        response = client.convert_to_png(
            uploaded,
            output_prefix="live-png",
            resolution=150,
        )

    _assert_output_files(
        response.output_files,
        expected_mime="image/png",
        expected_suffix=".png",
    )
    assert str(response.input_id) == str(uploaded.id)


@pytest.mark.asyncio
async def test_live_async_convert_to_png_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        response = await client.convert_to_png(
            uploaded,
            output_prefix="async-png",
            resolution=150,
        )

    _assert_output_files(
        response.output_files,
        expected_mime="image/png",
        expected_suffix=".png",
    )
    assert str(response.input_id) == str(uploaded.id)


@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "color_model"),
    _valid_color_cases(),
)
def test_live_graphic_valid_color_models(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    color_model: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    payload_model = spec.payload_model
    resolution = _resolution_bounds(payload_model)[0]
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        client_method = getattr(client, spec.method_name)
        expected_mime, expected_suffix = _expected_file_format(_endpoint_label)
        response = client_method(
            uploaded,
            color_model=color_model,
            resolution=resolution,
        )
        _assert_output_files(
            response.output_files,
            expected_mime=expected_mime,
            expected_suffix=expected_suffix,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "color_model"),
    _valid_color_cases(),
)
async def test_live_async_graphic_valid_color_models(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    color_model: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    payload_model = spec.payload_model
    resolution = _resolution_bounds(payload_model)[0]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        client_method = getattr(client, spec.method_name)
        expected_mime, expected_suffix = _expected_file_format(_endpoint_label)
        response = await client_method(
            uploaded,
            color_model=color_model,
            resolution=resolution,
        )
        _assert_output_files(
            response.output_files,
            expected_mime=expected_mime,
            expected_suffix=expected_suffix,
        )


@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "invalid_color"),
    _invalid_color_cases(),
)
def test_live_graphic_invalid_color_model(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    invalid_color: str,
) -> None:
    payload_model = spec.payload_model

    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        client_method = getattr(client, spec.method_name)
        resolution = _resolution_bounds(payload_model)[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)color"):
            client_method(
                uploaded,
                resolution=resolution,
                extra_body={"color_model": invalid_color},
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "invalid_color"),
    _invalid_color_cases(),
)
async def test_live_async_graphic_invalid_color_model(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    invalid_color: str,
) -> None:
    payload_model = spec.payload_model

    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        client_method = getattr(client, spec.method_name)
        resolution = _resolution_bounds(payload_model)[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)color"):
            await client_method(
                uploaded,
                resolution=resolution,
                extra_body={"color_model": invalid_color},
            )


@pytest.mark.parametrize(
    ("_endpoint_label", "spec"),
    PNG_PAYLOAD_ONLY.items(),
    ids=list(PNG_PAYLOAD_ONLY),
)
@pytest.mark.parametrize(
    ("bound", "offset", "should_raise"),
    [
        pytest.param("min", 0, False, id="min"),
        pytest.param("max", 0, False, id="max"),
        pytest.param("min", -1, True, id="below-min"),
        pytest.param("max", 1, True, id="above-max"),
    ],
)
def test_live_graphic_resolution_bounds(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    bound: str,
    offset: int,
    should_raise: bool,
) -> None:
    payload_model = spec.payload_model
    min_res, max_res = _resolution_bounds(payload_model)
    resource = get_test_resource_path("report.pdf")

    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        client_method = getattr(client, spec.method_name)
        base_resolution = min_res if bound == "min" else max_res
        call_kwargs: dict[str, Any] = {"resolution": base_resolution}

        if should_raise:
            call_kwargs["extra_body"] = {"resolution": base_resolution + offset}
            with pytest.raises(PdfRestApiError, match=r"(?i)resolution"):
                client_method(uploaded, **call_kwargs)
        else:
            response = client_method(uploaded, **call_kwargs)
            _assert_output_files(
                response.output_files,
                expected_mime="image/png",
                expected_suffix=".png",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("_endpoint_label", "spec"),
    PNG_PAYLOAD_ONLY.items(),
    ids=list(PNG_PAYLOAD_ONLY),
)
@pytest.mark.parametrize(
    ("bound", "offset", "should_raise"),
    [
        pytest.param("min", 0, False, id="min"),
        pytest.param("max", 0, False, id="max"),
        pytest.param("min", -1, True, id="below-min"),
        pytest.param("max", 1, True, id="above-max"),
    ],
)
async def test_live_async_graphic_resolution_bounds(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    bound: str,
    offset: int,
    should_raise: bool,
) -> None:
    payload_model = spec.payload_model
    min_res, max_res = _resolution_bounds(payload_model)
    resource = get_test_resource_path("report.pdf")

    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        client_method = getattr(client, spec.method_name)
        base_resolution = min_res if bound == "min" else max_res
        call_kwargs: dict[str, Any] = {"resolution": base_resolution}

        if should_raise:
            call_kwargs["extra_body"] = {"resolution": base_resolution + offset}
            with pytest.raises(PdfRestApiError, match=r"(?i)resolution"):
                await client_method(uploaded, **call_kwargs)
        else:
            response = await client_method(uploaded, **call_kwargs)
            _assert_output_files(
                response.output_files,
                expected_mime="image/png",
                expected_suffix=".png",
            )


@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "smoothing_value"),
    _valid_smoothing_cases(),
)
def test_live_graphic_valid_smoothing(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    smoothing_value: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        client_method = getattr(client, spec.method_name)
        expected_mime, expected_suffix = _expected_file_format(_endpoint_label)
        response = client_method(
            uploaded,
            smoothing=smoothing_value,
        )
        _assert_output_files(
            response.output_files,
            expected_mime=expected_mime,
            expected_suffix=expected_suffix,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "smoothing_value"),
    _valid_smoothing_cases(),
)
async def test_live_async_graphic_valid_smoothing(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    smoothing_value: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        client_method = getattr(client, spec.method_name)
        expected_mime, expected_suffix = _expected_file_format(_endpoint_label)
        response = await client_method(
            uploaded,
            smoothing=smoothing_value,
        )
        _assert_output_files(
            response.output_files,
            expected_mime=expected_mime,
            expected_suffix=expected_suffix,
        )


@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "invalid_smoothing"),
    _invalid_smoothing_cases(),
)
def test_live_graphic_invalid_smoothing(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    invalid_smoothing: Any,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        client_method = getattr(client, spec.method_name)
        with pytest.raises(PdfRestApiError, match=r"(?i)smooth"):
            client_method(
                uploaded,
                smoothing="none",
                extra_body={"smoothing": invalid_smoothing},
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("_endpoint_label", "spec", "invalid_smoothing"),
    _invalid_smoothing_cases(),
)
async def test_live_async_graphic_invalid_smoothing(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    _endpoint_label: str,
    spec: _GraphicEndpointSpec,
    invalid_smoothing: Any,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key, base_url=pdfrest_live_base_url
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        client_method = getattr(client, spec.method_name)
        with pytest.raises(PdfRestApiError, match=r"(?i)smooth"):
            await client_method(
                uploaded,
                smoothing="none",
                extra_body={"smoothing": invalid_smoothing},
            )


@pytest.mark.parametrize(
    ("page_range", "expect_success"),
    [
        pytest.param("5", True, id="single"),
        pytest.param("3-7", True, id="ascending-range"),
        pytest.param("last", True, id="last"),
        pytest.param("1-last", True, id="entire-document"),
        pytest.param(["1", "3", "5-7"], True, id="list-mixed"),
    ],
)
def test_live_png_page_range_variants(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_20_page_pdf: PdfRestFile,
    page_range: Any,
    expect_success: bool,
    request: pytest.FixtureRequest,
) -> None:
    case_id = request.node.callspec.id
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        info = client.query_pdf_info(uploaded_20_page_pdf)

        assert info.page_count == 20
        assert str(info.input_id) == str(uploaded_20_page_pdf.id)
        assert info.filename is None or info.filename.endswith(".pdf")

        if expect_success:
            response = client.convert_to_png(
                uploaded_20_page_pdf,
                output_prefix=f"live-range-{case_id}",
                page_range=page_range,
            )

            expected_pages = _expand_page_selection(page_range, total_pages=20)
            assert len(response.output_files) == len(expected_pages)
            _assert_output_files(
                response.output_files,
                expected_mime="image/png",
                expected_suffix=".png",
            )
            assert str(response.input_id) == str(uploaded_20_page_pdf.id)
        else:
            with pytest.raises(PdfRestApiError, match=r"(?i)page"):
                client.convert_to_png(
                    uploaded_20_page_pdf,
                    output_prefix=f"live-range-{case_id}",
                    extra_body={"page_range": page_range},
                )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("page_range", "expect_success"),
    [
        pytest.param("5", True, id="single"),
        pytest.param("3-7", True, id="ascending-range"),
        pytest.param("last", True, id="last"),
        pytest.param("1-last", True, id="entire-document"),
        pytest.param(["1", "3", "5-7"], True, id="list-mixed"),
    ],
)
async def test_live_async_png_page_range_variants(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_20_page_pdf: PdfRestFile,
    page_range: Any,
    expect_success: bool,
    request: pytest.FixtureRequest,
) -> None:
    case_id = request.node.callspec.id
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        info = await client.query_pdf_info(uploaded_20_page_pdf)

        assert info.page_count == 20
        assert str(info.input_id) == str(uploaded_20_page_pdf.id)
        assert info.filename is None or info.filename.endswith(".pdf")

        if expect_success:
            response = await client.convert_to_png(
                uploaded_20_page_pdf,
                output_prefix=f"live-async-range-{case_id}",
                page_range=page_range,
            )

            expected_pages = _expand_page_selection(page_range, total_pages=20)
            assert len(response.output_files) == len(expected_pages)
            _assert_output_files(
                response.output_files,
                expected_mime="image/png",
                expected_suffix=".png",
            )
            assert str(response.input_id) == str(uploaded_20_page_pdf.id)
        else:
            with pytest.raises(PdfRestApiError, match=r"(?i)page"):
                await client.convert_to_png(
                    uploaded_20_page_pdf,
                    output_prefix=f"live-async-range-{case_id}",
                    extra_body={"page_range": page_range},
                )


@pytest.mark.parametrize(
    "page_override",
    [
        pytest.param("0", id="zero"),
        pytest.param("last-0", id="range-with-zero"),
        pytest.param("7-3", id="descending-range"),
        pytest.param("even", id="even"),
        pytest.param("odd", id="odd"),
        pytest.param("odd,even", id="odd-even"),
    ],
)
def test_live_png_page_range_invalid_overrides(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_20_page_pdf: PdfRestFile,
    page_override: str,
    request: pytest.FixtureRequest,
) -> None:
    case_id = request.node.callspec.id
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(
            PdfRestApiError,
            match=r"There was an issue processing your file\. Validate all fields and try again\.",
        ),
    ):
        client.convert_to_png(
            uploaded_20_page_pdf,
            output_prefix=f"live-range-invalid-{case_id}",
            page_range="1",
            extra_body={"pages": page_override},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "page_override",
    [
        pytest.param("0", id="zero"),
        pytest.param("last-0", id="range-with-zero"),
        pytest.param("7-3", id="descending-range"),
        pytest.param("even", id="even"),
        pytest.param("odd", id="odd"),
        pytest.param("odd,even", id="odd-even"),
    ],
)
async def test_live_async_png_page_range_invalid_overrides(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_20_page_pdf: PdfRestFile,
    page_override: str,
    request: pytest.FixtureRequest,
) -> None:
    case_id = request.node.callspec.id
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError,
            match=r"There was an issue processing your file\. Validate all fields and try again\.",
        ):
            await client.convert_to_png(
                uploaded_20_page_pdf,
                output_prefix=f"live-async-range-invalid-{case_id}",
                page_range="1",
                extra_body={"pages": page_override},
            )


def _expand_page_selection(
    selection: Any,
    *,
    total_pages: int,
) -> list[int]:
    def expand_entry(entry: Any) -> list[int]:
        if isinstance(entry, int):
            return [entry]
        text = str(entry).strip()
        lowered = text.lower()
        if lowered == "even":
            return list(range(2, total_pages + 1, 2))
        if lowered == "odd":
            return list(range(1, total_pages + 1, 2))
        if lowered == "last":
            return [total_pages]
        if "-" in lowered:
            start_raw, end_raw = (part.strip() for part in lowered.split("-", 1))

            def resolve(range_token: str) -> int:
                return total_pages if range_token == "last" else int(range_token)  # noqa: S105

            start = resolve(start_raw)
            end = resolve(end_raw)
            step = 1 if end >= start else -1
            return list(range(start, end + step, step))
        return [int(text)]

    if isinstance(selection, Sequence) and not isinstance(
        selection, (str, bytes, bytearray)
    ):
        expanded: list[int] = []
        for segment in selection:
            expanded.extend(expand_entry(segment))
        return expanded
    return expand_entry(selection)
