from __future__ import annotations

import json
import math
from typing import Literal, cast, get_args

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import ConvertPdfToPostscriptPayload
from pdfrest.types import PostScriptLevel

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)

POSTSCRIPT_LEVELS = cast(
    tuple[PostScriptLevel, ...],
    get_args(ConvertPdfToPostscriptPayload.model_fields["ps_level"].annotation),
)


def _postscript_level_id(ps_level: PostScriptLevel) -> str:
    return f"level-{ps_level}"


def _make_non_pdf_file() -> PdfRestFile:
    return PdfRestFile.model_validate(
        build_file_info_payload(
            PdfRestFileID.generate(),
            "example.png",
            "image/png",
        )
    )


def _assert_timeout(
    value: float | dict[str, float] | None,
    expected: float,
) -> None:
    assert value is not None
    if isinstance(value, dict):
        assert value
        assert all(component == pytest.approx(expected) for component in value.values())
    else:
        assert value == pytest.approx(expected)


@pytest.mark.parametrize(
    "ps_level",
    POSTSCRIPT_LEVELS,
    ids=_postscript_level_id,
)
def test_convert_pdf_to_postscript_payload_serialization(
    ps_level: PostScriptLevel,
) -> None:
    source = make_pdf_file(PdfRestFileID.generate(1))

    payload = ConvertPdfToPostscriptPayload.model_validate(
        {
            "file": source,
            "ps_level": ps_level,
            "page_range": "1, 3-5, 12, 14-last",
            "binary_output": False,
            "scale": 1.25,
            "rotate": True,
            "shrink_to_fit": True,
            "print_annotations": False,
            "output": "print-ready",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    assert payload == {
        "id": str(source.id),
        "ps_level": ps_level,
        "page_range": "1,3-5,12,14-last",
        "binary_output": False,
        "scale": 1.25,
        "rotate": True,
        "shrink_to_fit": True,
        "print_annotations": False,
        "output": "print-ready",
    }


@pytest.mark.parametrize(
    ("page_range", "expected_page_range"),
    [
        pytest.param("all", "all", id="all"),
        pytest.param("ALL", "all", id="all-case-insensitive"),
        pytest.param("1", "1", id="single-page"),
        pytest.param("last", "last", id="last-page"),
        pytest.param("1-3", "1-3", id="ascending-range"),
        pytest.param("6-last", "6-last", id="range-to-last"),
        pytest.param(
            "1, 3-5, 12, 14-LAST",
            "1,3-5,12,14-last",
            id="mixed-selection",
        ),
    ],
)
def test_convert_pdf_to_postscript_page_range_accepts_supported_syntax(
    page_range: str,
    expected_page_range: str,
) -> None:
    source = make_pdf_file(PdfRestFileID.generate(2))

    payload = ConvertPdfToPostscriptPayload.model_validate(
        {"file": source, "page_range": page_range}
    )

    assert payload.model_dump(mode="json", by_alias=True)["page_range"] == (
        expected_page_range
    )


@pytest.mark.parametrize(
    "page_range",
    [
        pytest.param("", id="empty"),
        pytest.param("0", id="zero"),
        pytest.param("1-", id="missing-end"),
        pytest.param("1,,3", id="empty-selection"),
        pytest.param("last-2", id="last-as-start"),
        pytest.param("3-1", id="descending"),
        pytest.param("even", id="unsupported-selector"),
        pytest.param("1--3", id="double-hyphen"),
        pytest.param("all,1", id="all-with-selection"),
    ],
)
def test_convert_pdf_to_postscript_page_range_rejects_unsupported_syntax(
    page_range: str,
) -> None:
    source = make_pdf_file(PdfRestFileID.generate())

    with pytest.raises(
        ValidationError,
        match="An invalid page range was specified",
    ):
        ConvertPdfToPostscriptPayload.model_validate(
            {"file": source, "page_range": page_range}
        )


@pytest.mark.parametrize(
    "scale",
    [
        pytest.param(0.0001, id="positive-near-zero"),
        pytest.param(1, id="identity"),
        pytest.param(1.25, id="enlarge"),
    ],
)
def test_convert_pdf_to_postscript_scale_accepts_positive_values(scale: float) -> None:
    source = make_pdf_file(PdfRestFileID.generate())

    payload = ConvertPdfToPostscriptPayload.model_validate(
        {"file": source, "scale": scale}
    )

    assert payload.scale == pytest.approx(scale)


@pytest.mark.parametrize(
    ("scale", "error_match"),
    [
        pytest.param(0, "greater than 0", id="zero"),
        pytest.param(-0.0001, "greater than 0", id="negative"),
        pytest.param(math.inf, "finite number", id="positive-infinity"),
        pytest.param(-math.inf, "finite number", id="negative-infinity"),
        pytest.param(math.nan, "finite number", id="not-a-number"),
    ],
)
def test_convert_pdf_to_postscript_scale_rejects_non_positive_or_non_finite_values(
    scale: float,
    error_match: str,
) -> None:
    source = make_pdf_file(PdfRestFileID.generate())

    with pytest.raises(ValidationError, match=error_match):
        ConvertPdfToPostscriptPayload.model_validate({"file": source, "scale": scale})


def test_convert_pdf_to_postscript_default_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/postscript":
            seen["post"] += 1
            assert json.loads(request.content) == {
                "id": str(source.id),
                "ps_level": 3,
                "page_range": "all",
                "binary_output": True,
                "scale": 1,
                "rotate": False,
                "shrink_to_fit": False,
                "print_annotations": True,
            }
            return httpx.Response(
                200,
                json={"inputId": [source.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "example_pdfrest_postscript.ps",
                    "application/postscript",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.convert_pdf_to_postscript(source)

    assert seen == {"post": 1, "get": 1}
    assert response.output_file.name == "example_pdfrest_postscript.ps"


@pytest.mark.asyncio
async def test_async_convert_pdf_to_postscript_default_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/postscript":
            seen["post"] += 1
            assert json.loads(request.content) == {
                "id": str(source.id),
                "ps_level": 3,
                "page_range": "all",
                "binary_output": True,
                "scale": 1,
                "rotate": False,
                "shrink_to_fit": False,
                "print_annotations": True,
            }
            return httpx.Response(
                200,
                json={"inputId": [source.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "example_pdfrest_postscript.ps",
                    "application/postscript",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.convert_pdf_to_postscript(source)

    assert seen == {"post": 1, "get": 1}
    assert response.output_file.name == "example_pdfrest_postscript.ps"


@pytest.mark.parametrize(
    "ps_level",
    POSTSCRIPT_LEVELS,
    ids=_postscript_level_id,
)
def test_convert_pdf_to_postscript_success(
    monkeypatch: pytest.MonkeyPatch,
    ps_level: PostScriptLevel,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    expected_payload = ConvertPdfToPostscriptPayload.model_validate(
        {
            "file": source,
            "ps_level": ps_level,
            "page_range": "1,3-5",
            "binary_output": False,
            "scale": 1.25,
            "rotate": True,
            "shrink_to_fit": True,
            "print_annotations": False,
            "output": f"level-{ps_level}",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/postscript":
            seen["post"] += 1
            assert json.loads(request.content) == expected_payload
            return httpx.Response(
                200,
                json={"inputId": [source.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    f"level-{ps_level}.ps",
                    "application/postscript",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.convert_pdf_to_postscript(
            source,
            ps_level=ps_level,
            page_range="1,3-5",
            binary_output=False,
            scale=1.25,
            rotate=True,
            shrink_to_fit=True,
            print_annotations=False,
            output=f"level-{ps_level}",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == f"level-{ps_level}.ps"
    assert response.output_file.type == "application/postscript"
    assert response.output_file.size == 256
    assert str(response.output_file.url).endswith(output_id)
    assert str(response.input_id) == str(source.id)
    assert response.warning is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ps_level",
    POSTSCRIPT_LEVELS,
    ids=_postscript_level_id,
)
async def test_async_convert_pdf_to_postscript_success(
    monkeypatch: pytest.MonkeyPatch,
    ps_level: PostScriptLevel,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    expected_payload = ConvertPdfToPostscriptPayload.model_validate(
        {
            "file": source,
            "ps_level": ps_level,
            "page_range": "2-last",
            "binary_output": False,
            "scale": 0.75,
            "rotate": True,
            "shrink_to_fit": True,
            "print_annotations": False,
            "output": f"async-level-{ps_level}",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    seen = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/postscript":
            seen["post"] += 1
            assert json.loads(request.content) == expected_payload
            return httpx.Response(
                200,
                json={"inputId": [source.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    f"async-level-{ps_level}.ps",
                    "application/postscript",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.convert_pdf_to_postscript(
            source,
            ps_level=ps_level,
            page_range="2-last",
            binary_output=False,
            scale=0.75,
            rotate=True,
            shrink_to_fit=True,
            print_annotations=False,
            output=f"async-level-{ps_level}",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == f"async-level-{ps_level}.ps"
    assert response.output_file.type == "application/postscript"
    assert response.output_file.size == 256
    assert str(response.output_file.url).endswith(output_id)
    assert str(response.input_id) == str(source.id)
    assert response.warning is None


def test_convert_pdf_to_postscript_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_timeout[request.method.lower()] = request.extensions.get("timeout")
        assert request.url.params["trace"] == "sync"
        assert request.headers["X-Debug"] == "sync"
        if request.method == "POST" and request.url.path == "/postscript":
            payload = json.loads(request.content)
            assert payload == {
                "id": str(source.id),
                "ps_level": 3,
                "page_range": "all",
                "binary_output": True,
                "scale": 1,
                "rotate": False,
                "shrink_to_fit": False,
                "print_annotations": True,
                "output": "custom",
                "debug": True,
            }
            return httpx.Response(
                200,
                json={"inputId": [source.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "custom.ps",
                    "application/postscript",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    with PdfRestClient(
        api_key=VALID_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.convert_pdf_to_postscript(
            source,
            output="custom",
            extra_query={"trace": "sync"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"debug": True},
            timeout=0.35,
        )

    assert response.output_file.name == "custom.ps"
    _assert_timeout(captured_timeout["post"], 0.35)
    _assert_timeout(captured_timeout["get"], 0.35)


@pytest.mark.asyncio
async def test_async_convert_pdf_to_postscript_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    source = make_pdf_file(PdfRestFileID.generate())
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_timeout[request.method.lower()] = request.extensions.get("timeout")
        assert request.url.params["trace"] == "async"
        assert request.headers["X-Debug"] == "async"
        if request.method == "POST" and request.url.path == "/postscript":
            payload = json.loads(request.content)
            assert payload == {
                "id": str(source.id),
                "ps_level": 3,
                "page_range": "all",
                "binary_output": True,
                "scale": 1,
                "rotate": False,
                "shrink_to_fit": False,
                "print_annotations": True,
                "output": "async-custom",
                "metadata": {"source": "async"},
            }
            return httpx.Response(
                200,
                json={"inputId": [source.id], "outputId": [output_id]},
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-custom.ps",
                    "application/postscript",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.convert_pdf_to_postscript(
            source,
            output="async-custom",
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async"},
            extra_body={"metadata": {"source": "async"}},
            timeout=0.65,
        )

    assert response.output_file.name == "async-custom.ps"
    _assert_timeout(captured_timeout["post"], 0.65)
    _assert_timeout(captured_timeout["get"], 0.65)


ValidationCase = Literal[
    "mime",
    "cardinality",
    "ps-level",
    "page-range",
    "scale",
    "output",
]


def _invoke_sync_validation_case(
    client: PdfRestClient,
    case: ValidationCase,
) -> None:
    source = make_pdf_file(PdfRestFileID.generate())
    if case == "mime":
        client.convert_pdf_to_postscript(_make_non_pdf_file())
    elif case == "cardinality":
        client.convert_pdf_to_postscript(
            [source, make_pdf_file(PdfRestFileID.generate())]
        )
    elif case == "ps-level":
        client.convert_pdf_to_postscript(source, ps_level=4)  # type: ignore[arg-type]
    elif case == "page-range":
        client.convert_pdf_to_postscript(source, page_range="all,1")
    elif case == "scale":
        client.convert_pdf_to_postscript(source, scale=0)
    else:
        client.convert_pdf_to_postscript(source, output="metadata.json")


async def _invoke_async_validation_case(
    client: AsyncPdfRestClient,
    case: ValidationCase,
) -> None:
    source = make_pdf_file(PdfRestFileID.generate())
    if case == "mime":
        await client.convert_pdf_to_postscript(_make_non_pdf_file())
    elif case == "cardinality":
        await client.convert_pdf_to_postscript(
            [source, make_pdf_file(PdfRestFileID.generate())]
        )
    elif case == "ps-level":
        await client.convert_pdf_to_postscript(
            source,
            ps_level=4,  # type: ignore[arg-type]
        )
    elif case == "page-range":
        await client.convert_pdf_to_postscript(source, page_range="all,1")
    elif case == "scale":
        await client.convert_pdf_to_postscript(source, scale=0)
    else:
        await client.convert_pdf_to_postscript(source, output="metadata.json")


VALIDATION_CASES = [
    pytest.param("mime", "Must be a PDF file", id="mime"),
    pytest.param("cardinality", "at most 1 item", id="cardinality"),
    pytest.param("ps-level", "Input should be 2 or 3", id="ps-level"),
    pytest.param(
        "page-range",
        "An invalid page range was specified",
        id="page-range",
    ),
    pytest.param("scale", "greater than 0", id="scale"),
    pytest.param("output", "reserved name", id="output"),
]


@pytest.mark.parametrize(("case", "error_match"), VALIDATION_CASES)
def test_convert_pdf_to_postscript_rejects_invalid_input_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    case: ValidationCase,
    error_match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(ValidationError, match=error_match),
    ):
        _invoke_sync_validation_case(client, case)


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "error_match"), VALIDATION_CASES)
async def test_async_convert_pdf_to_postscript_rejects_invalid_input_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    case: ValidationCase,
    error_match: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValidationError, match=error_match):
            await _invoke_async_validation_case(client, case)
