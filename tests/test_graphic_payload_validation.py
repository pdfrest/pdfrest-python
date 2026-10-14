from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models._internal import (
    BasePdfRestGraphicPayload,
    BmpPdfRestPayload,
    GifPdfRestPayload,
    JpegPdfRestPayload,
    PngPdfRestPayload,
    TiffPdfRestPayload,
)

from .graphics_test_helpers import ASYNC_API_KEY, VALID_API_KEY, make_pdf_file

PAYLOAD_MODELS: tuple[type[BasePdfRestGraphicPayload[Any]], ...] = (
    PngPdfRestPayload,
    BmpPdfRestPayload,
    GifPdfRestPayload,
    JpegPdfRestPayload,
    TiffPdfRestPayload,
)
GRAPHIC_METHOD_NAMES = (
    "convert_to_png",
    "convert_to_bmp",
    "convert_to_gif",
    "convert_to_jpeg",
    "convert_to_tiff",
)
_TEST_PASSWORD = "open-sesame"  # noqa: S105 - Test-only password.


@pytest.mark.parametrize("payload_model", PAYLOAD_MODELS)
def test_graphic_payload_serializes_password(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
) -> None:
    payload = payload_model.model_validate(
        {
            "files": [make_pdf_file("12345678-1234-4abc-8def-1234567890ab")],
            "password": _TEST_PASSWORD,
        }
    )

    data = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert data["password"] == _TEST_PASSWORD


@pytest.mark.parametrize("payload_model", PAYLOAD_MODELS)
def test_graphic_payload_rejects_empty_password(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
) -> None:
    with pytest.raises(
        ValidationError,
        match=r"password\s+String should have at least 1 character",
    ):
        payload_model.model_validate(
            {
                "files": [make_pdf_file("12345678-1234-4abc-8def-1234567890ab")],
                "password": "",
            }
        )


@pytest.mark.parametrize("method_name", GRAPHIC_METHOD_NAMES)
def test_graphic_client_rejects_empty_password(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when password validation fails.")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY,
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(
            ValidationError,
            match=r"password\s+String should have at least 1 character",
        ),
    ):
        getattr(client, method_name)(
            make_pdf_file("12345678-1234-4abc-8def-1234567890ab"),
            password="",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", GRAPHIC_METHOD_NAMES)
async def test_async_graphic_client_rejects_empty_password(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Request should not be sent when password validation fails.")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(
            ValidationError,
            match=r"password\s+String should have at least 1 character",
        ):
            await getattr(client, method_name)(
                make_pdf_file("12345678-1234-4abc-8def-1234567890ab"),
                password="",
            )


@pytest.mark.parametrize("payload_model", PAYLOAD_MODELS)
def test_graphic_payload_accepts_page_range_variants(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
) -> None:
    payload = payload_model.model_validate(
        {
            "files": [make_pdf_file("12345678-1234-4abc-8def-1234567890ab")],
            "page_range": [1, "last", "6-last"],
        }
    )

    data = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert data["pages"] == "1,last,6-last"


@pytest.mark.parametrize("payload_model", PAYLOAD_MODELS)
@pytest.mark.parametrize(
    ("bad_prefix", "expected"),
    [
        pytest.param(
            ".hidden",
            "The output prefix must not start with a `.`.",
            id="leading-dot",
        ),
        pytest.param(
            "profile.json",
            "The output prefix is a reserved name.",
            id="reserved-profile",
        ),
        pytest.param(
            "metadata.json",
            "The output prefix is a reserved name.",
            id="reserved-metadata",
        ),
        pytest.param(
            "invalid!name",
            "The output prefix must not contain special characters: '!'.",
            id="special-char",
        ),
        pytest.param(
            "nested/path",
            "The output prefix must not contain a directory separator.",
            id="directory-separator",
        ),
    ],
)
def test_graphic_payload_invalid_output_prefix(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
    bad_prefix: str,
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=re.escape(expected)):
        payload_model.model_validate(
            {
                "files": [make_pdf_file("12345678-1234-4abc-8def-1234567890ab")],
                "output_prefix": bad_prefix,
            }
        )


@pytest.mark.parametrize("payload_model", PAYLOAD_MODELS)
@pytest.mark.parametrize(
    ("bad_page_range", "expected"),
    [
        pytest.param(
            "0",
            "greater than or equal to 1",
            id="scalar-zero",
        ),
        pytest.param(
            ["0"],
            "greater than or equal to 1",
            id="list-zero-string",
        ),
        pytest.param(
            [0],
            "greater than or equal to 1",
            id="list-zero-int",
        ),
        pytest.param(
            "last-5",
            "unable to parse string as an integer",
            id="range-last-to-number",
        ),
        pytest.param(
            "3-2",
            "less than or equal to the end page",
            id="range-descending",
        ),
        pytest.param(
            "foo",
            "unable to parse string as an integer",
            id="scalar-word",
        ),
        pytest.param(
            ["1", "foo"],
            "unable to parse string as an integer",
            id="list-mixed",
        ),
        pytest.param(
            "even",
            "unable to parse string as an integer",
            id="even",
        ),
        pytest.param(
            "odd",
            "unable to parse string as an integer",
            id="odd",
        ),
    ],
)
def test_graphic_payload_invalid_page_range_value(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
    bad_page_range: object,
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=re.escape(expected)):
        payload_model.model_validate(
            {
                "files": [make_pdf_file("12345678-1234-4abc-8def-1234567890ab")],
                "page_range": bad_page_range,
            }
        )


@pytest.mark.parametrize("payload_model", PAYLOAD_MODELS)
@pytest.mark.parametrize(
    ("page_range", "expected_message"),
    [
        pytest.param(
            "even",
            "unable to parse string as an integer",
            id="even",
        ),
        pytest.param(
            "odd",
            "unable to parse string as an integer",
            id="odd",
        ),
        pytest.param(
            "5-3",
            "less than or equal to the end page",
            id="descending",
        ),
    ],
)
def test_graphic_payload_rejects_special_ranges(
    payload_model: type[BasePdfRestGraphicPayload[Any]],
    page_range: str,
    expected_message: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match=expected_message,
    ):
        payload_model.model_validate(
            {
                "files": [make_pdf_file("12345678-1234-4abc-8def-1234567890ab")],
                "page_range": page_range,
            }
        )
