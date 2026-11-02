from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, cast, get_args

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfZugferdPayload
from pdfrest.types import (
    PdfZugferdCurrencyDisplay,
    PdfZugferdKnownFont,
    PdfZugferdLocale,
    PdfZugferdLogoCorner,
    PdfZugferdRenderOptions,
)

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
)

KNOWN_FONTS = cast(tuple[PdfZugferdKnownFont, ...], get_args(PdfZugferdKnownFont))
LOGO_CORNERS = cast(tuple[PdfZugferdLogoCorner, ...], get_args(PdfZugferdLogoCorner))
LOCALES = cast(tuple[PdfZugferdLocale, ...], get_args(PdfZugferdLocale))
CURRENCY_DISPLAYS = cast(
    tuple[PdfZugferdCurrencyDisplay, ...], get_args(PdfZugferdCurrencyDisplay)
)


def _make_file(name: str, mime_type: str, *, prefix: int | None = None) -> PdfRestFile:
    file_id = PdfRestFileID.generate(prefix)
    return PdfRestFile.model_validate(
        {
            "id": file_id,
            "name": name,
            "url": f"https://api.pdfrest.com/resource/{file_id}",
            "type": mime_type,
            "size": 1024,
            "modified": datetime(2024, 1, 1, tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "scheduledDeletionTimeUtc": None,
        }
    )


def _dump(payload: dict[str, Any]) -> dict[str, Any]:
    return PdfZugferdPayload.model_validate(payload).model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )


def _assert_timeout(value: float | dict[str, float] | None, expected: float) -> None:
    assert value is not None
    if isinstance(value, dict):
        assert value
        assert all(component == pytest.approx(expected) for component in value.values())
    else:
        assert value == pytest.approx(expected)


def test_zugferd_payload_serializes_resources_and_render_options() -> None:
    invoice = _make_file("invoice.xml", "application/xml", prefix=1)
    pdf = _make_file("invoice.pdf", "application/pdf")
    logo = _make_file("logo.png", "image/png", prefix=2)

    payload = _dump(
        {
            "invoice": invoice,
            "pdf": pdf,
            "logo": logo,
            "regenerate_pdf": True,
            "output": "customer-invoice",
            "render_options": {
                "logo_corner": "top-right",
                "font": " arial ",
                "bold_font": "arialbold",
                "text_color": (26, 31, 41),
                "muted_text_color": (10, 5, 0, 55),
                "accent_color": (20, 64, 115),
                "border_color": (12, 7, 0, 20),
                "table_header_color": (20, 64, 115),
                "table_alternate_color": (4, 2, 0, 2),
                "footer_message": "Thank you for your business.",
                "locale": "de-DE",
                "label_language": "en-US",
                "currency_display": "symbol",
                "date_format": "dd.MM.yyyy",
                "decimal_precision": 3,
            },
        }
    )

    assert payload == {
        "id": str(invoice.id),
        "pdf_id": str(pdf.id),
        "logo_id": str(logo.id),
        "render_options": {
            "logo_corner": "top-right",
            "font": "arial",
            "bold_font": "arialbold",
            "text_color_rgb": [26, 31, 41],
            "muted_text_color_cmyk": [10, 5, 0, 55],
            "accent_color_rgb": [20, 64, 115],
            "border_color_cmyk": [12, 7, 0, 20],
            "table_header_color_rgb": [20, 64, 115],
            "table_alternate_color_cmyk": [4, 2, 0, 2],
            "footer_message": "Thank you for your business.",
            "locale": "de-DE",
            "label_language": "en-US",
            "currency_display": "symbol",
            "date_format": "dd.MM.yyyy",
            "decimal_precision": 3,
        },
        "regenerate_pdf": True,
        "output": "customer-invoice",
    }


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("text_color", id="text"),
        pytest.param("muted_text_color", id="muted-text"),
        pytest.param("accent_color", id="accent"),
        pytest.param("border_color", id="border"),
        pytest.param("table_header_color", id="table-header"),
        pytest.param("table_alternate_color", id="table-alternate"),
    ],
)
@pytest.mark.parametrize(
    ("color", "wire_suffix"),
    [
        pytest.param((0, 127, 255), "rgb", id="rgb"),
        pytest.param((0, 25, 50, 100), "cmyk", id="cmyk"),
    ],
)
def test_zugferd_payload_routes_unified_colors(
    field: str,
    color: tuple[int, ...],
    wire_suffix: str,
) -> None:
    invoice = _make_file("invoice.xml", "text/xml")

    payload = _dump({"invoice": invoice, "render_options": {field: color}})

    assert payload["render_options"] == {f"{field}_{wire_suffix}": list(color)}


@pytest.mark.parametrize("font", KNOWN_FONTS, ids=str)
def test_zugferd_payload_accepts_every_published_font(
    font: PdfZugferdKnownFont,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    payload = _dump({"invoice": invoice, "render_options": {"font": font}})

    assert payload["render_options"] == {"font": font}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        *(
            pytest.param("logo_corner", value, id=f"logo-{value}")
            for value in LOGO_CORNERS
        ),
        *(pytest.param("locale", value, id=f"locale-{value}") for value in LOCALES),
        *(
            pytest.param("currency_display", value, id=f"currency-{value}")
            for value in CURRENCY_DISPLAYS
        ),
        pytest.param("label_language", "en", id="language-en"),
        pytest.param("label_language", "de", id="language-de"),
        pytest.param("label_language", "fr", id="language-fr"),
        pytest.param("label_language", "fr-FR", id="language-region"),
    ],
)
def test_zugferd_payload_accepts_render_option_literals(field: str, value: str) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    payload = _dump({"invoice": invoice, "render_options": {field: value}})

    assert payload["render_options"] == {field: value}


@pytest.mark.parametrize(
    "decimal_precision",
    [pytest.param(0, id="minimum"), pytest.param(4, id="maximum")],
)
def test_zugferd_payload_accepts_decimal_precision_boundaries(
    decimal_precision: int,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    payload = _dump(
        {
            "invoice": invoice,
            "render_options": {"decimal_precision": decimal_precision},
        }
    )

    assert payload["render_options"]["decimal_precision"] == decimal_precision


@pytest.mark.parametrize(
    ("options", "error_match"),
    [
        pytest.param(
            {"decimal_precision": -1}, "greater than or equal to 0", id="precision-low"
        ),
        pytest.param(
            {"decimal_precision": 5}, "less than or equal to 4", id="precision-high"
        ),
        pytest.param(
            {"text_color": (0, 256, 0)}, "less than or equal to 255", id="rgb-high"
        ),
        pytest.param(
            {"text_color": (0, 101, 0, 0)}, "less than or equal to 100", id="cmyk-high"
        ),
        pytest.param({"text_color": (0, 0)}, "exactly 3.*or 4", id="channel-count"),
        pytest.param({"font": "   "}, "at least 1 item", id="font-empty"),
        pytest.param({"font": "x" * 201}, "at most 200 items", id="font-long"),
        pytest.param({"font": "Webdings"}, "Webdings is unsupported", id="font-symbol"),
        pytest.param(
            {"footer_message": "x" * 501}, "at most 500 characters", id="footer-long"
        ),
        pytest.param(
            {"label_language": "nl"},
            "English, German, or French",
            id="language-primary",
        ),
        pytest.param(
            {"label_language": "not_a_tag"}, "valid BCP 47", id="language-shape"
        ),
        pytest.param(
            {"unsupported": True}, "Extra inputs are not permitted", id="unknown-field"
        ),
    ],
)
def test_zugferd_payload_rejects_invalid_render_options(
    options: dict[str, Any],
    error_match: str,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    with pytest.raises(ValidationError, match=error_match):
        PdfZugferdPayload.model_validate(
            {"invoice": invoice, "render_options": options}
        )


def test_zugferd_payload_accepts_custom_installed_font() -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    payload = _dump({"invoice": invoice, "render_options": {"font": "Corporate Sans"}})

    assert payload["render_options"] == {"font": "Corporate Sans"}


@pytest.mark.parametrize(
    ("payload", "error_match"),
    [
        pytest.param(
            {"invoice": _make_file("invoice.pdf", "application/pdf")},
            "Invoice must be an XML file",
            id="invoice-mime",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "pdf": _make_file("source.png", "image/png"),
            },
            "Must be a PDF file",
            id="pdf-mime",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "logo": _make_file("logo.gif", "image/gif"),
            },
            "Logo must be a PNG or JPEG file",
            id="logo-mime",
        ),
        pytest.param(
            {
                "invoice": [
                    _make_file("one.xml", "application/xml"),
                    _make_file("two.xml", "text/xml"),
                ]
            },
            "at most 1 item",
            id="invoice-cardinality",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "regenerate_pdf": True,
            },
            "requires a PDF resource",
            id="regeneration-dependency",
        ),
    ],
)
def test_zugferd_payload_rejects_invalid_resources(
    payload: dict[str, Any], error_match: str
) -> None:
    with pytest.raises(ValidationError, match=error_match):
        PdfZugferdPayload.model_validate(payload)


def test_create_zugferd_pdf_success_and_response_mapping() -> None:
    invoice = _make_file("invoice.xml", "application/xml", prefix=1)
    pdf = _make_file("invoice.pdf", "application/pdf")
    logo = _make_file("logo.jpg", "image/jpeg", prefix=2)
    output_id = PdfRestFileID.generate()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/zugferd-pdf"
            assert request.headers["Api-Key"] == VALID_API_KEY
            assert json.loads(request.content) == {
                "id": str(invoice.id),
                "pdf_id": str(pdf.id),
                "logo_id": str(logo.id),
                "render_options": {
                    "logo_corner": "bottom-right",
                    "text_color_rgb": [1, 2, 3],
                    "accent_color_cmyk": [4, 3, 2, 1],
                },
                "regenerate_pdf": True,
                "output": "zugferd-result",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [str(invoice.id), str(pdf.id), str(logo.id)],
                    "outputId": str(output_id),
                    "outputUrl": f"https://api.pdfrest.com/resource/{output_id}",
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        return httpx.Response(
            200,
            json=build_file_info_payload(
                str(output_id), "zugferd-result.pdf", "application/pdf"
            ),
        )

    options: PdfZugferdRenderOptions = {
        "logo_corner": "bottom-right",
        "text_color": (1, 2, 3),
        "accent_color": (4, 3, 2, 1),
    }
    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.create_zugferd_pdf(
            invoice,
            pdf=pdf,
            logo=logo,
            render_options=options,
            regenerate_pdf=True,
            output="zugferd-result",
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.input_ids == [invoice.id, pdf.id, logo.id]
    assert response.output_file.id == output_id
    assert response.output_file.name == "zugferd-result.pdf"
    assert response.output_file.type == "application/pdf"


@pytest.mark.asyncio
async def test_async_create_zugferd_pdf_success_and_response_mapping() -> None:
    invoice = _make_file("invoice.xml", "text/xml", prefix=1)
    pdf = _make_file("invoice.pdf", "application/pdf")
    logo = _make_file("logo.png", "image/png", prefix=2)
    output_id = PdfRestFileID.generate()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/zugferd-pdf"
            assert request.headers["Api-Key"] == ASYNC_API_KEY
            assert json.loads(request.content) == {
                "id": str(invoice.id),
                "pdf_id": str(pdf.id),
                "logo_id": str(logo.id),
                "render_options": {
                    "font": "Corporate Sans",
                    "bold_font": "arialbold",
                    "muted_text_color_cmyk": [0, 0, 0, 50],
                    "locale": "fr-FR",
                    "label_language": "fr-FR",
                    "currency_display": "name",
                    "decimal_precision": 4,
                },
                "regenerate_pdf": True,
                "output": "zugferd-async",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [str(invoice.id), str(pdf.id), str(logo.id)],
                    "outputId": str(output_id),
                    "outputUrl": f"https://api.pdfrest.com/resource/{output_id}",
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        return httpx.Response(
            200,
            json=build_file_info_payload(
                str(output_id), "zugferd-async.pdf", "application/pdf"
            ),
        )

    options: PdfZugferdRenderOptions = {
        "font": "Corporate Sans",
        "bold_font": "arialbold",
        "muted_text_color": (0, 0, 0, 50),
        "locale": "fr-FR",
        "label_language": "fr-FR",
        "currency_display": "name",
        "decimal_precision": 4,
    }
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.create_zugferd_pdf(
            invoice,
            pdf=pdf,
            logo=logo,
            render_options=options,
            regenerate_pdf=True,
            output="zugferd-async",
        )

    assert response.input_ids == [invoice.id, pdf.id, logo.id]
    assert response.output_file.id == output_id
    assert response.output_file.name == "zugferd-async.pdf"


def test_create_zugferd_pdf_request_customization() -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["trace"] == "sync"
        assert request.headers["X-Trace"] == "zugferd"
        _assert_timeout(request.extensions.get("timeout"), 14.0)
        assert json.loads(request.content) == {
            "id": str(invoice.id),
            "regenerate_pdf": False,
            "server_debug": True,
        }
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.create_zugferd_pdf(
            invoice,
            extra_query={"trace": "sync"},
            extra_headers={"X-Trace": "zugferd"},
            extra_body={"server_debug": True},
            timeout=14.0,
        )

    assert response.input_id == invoice.id
    assert response.output_files == []


@pytest.mark.asyncio
async def test_async_create_zugferd_pdf_request_customization() -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["trace"] == "async"
        assert request.headers["X-Trace"] == "zugferd-async"
        _assert_timeout(request.extensions.get("timeout"), 21.0)
        assert json.loads(request.content) == {
            "id": str(invoice.id),
            "regenerate_pdf": False,
            "server_debug": True,
        }
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.create_zugferd_pdf(
            invoice,
            extra_query={"trace": "async"},
            extra_headers={"X-Trace": "zugferd-async"},
            extra_body={"server_debug": True},
            timeout=21.0,
        )

    assert response.input_id == invoice.id
    assert response.output_files == []


@pytest.mark.parametrize("font", KNOWN_FONTS, ids=str)
def test_create_zugferd_pdf_accepts_every_published_font(
    font: PdfZugferdKnownFont,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["render_options"] == {"font": font}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.create_zugferd_pdf(invoice, render_options={"font": font})


@pytest.mark.parametrize("font", KNOWN_FONTS, ids=str)
@pytest.mark.asyncio
async def test_async_create_zugferd_pdf_accepts_every_published_font(
    font: PdfZugferdKnownFont,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["render_options"] == {"font": font}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.create_zugferd_pdf(invoice, render_options={"font": font})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        *(
            pytest.param("logo_corner", value, id=f"logo-{value}")
            for value in LOGO_CORNERS
        ),
        *(pytest.param("locale", value, id=f"locale-{value}") for value in LOCALES),
        *(
            pytest.param("currency_display", value, id=f"currency-{value}")
            for value in CURRENCY_DISPLAYS
        ),
        pytest.param("label_language", "en", id="language-en"),
        pytest.param("label_language", "de", id="language-de"),
        pytest.param("label_language", "fr", id="language-fr"),
    ],
)
def test_create_zugferd_pdf_accepts_every_render_literal(
    field: str, value: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["render_options"] == {field: value}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.create_zugferd_pdf(
            invoice,
            render_options=cast(PdfZugferdRenderOptions, cast(object, {field: value})),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        *(
            pytest.param("logo_corner", value, id=f"logo-{value}")
            for value in LOGO_CORNERS
        ),
        *(pytest.param("locale", value, id=f"locale-{value}") for value in LOCALES),
        *(
            pytest.param("currency_display", value, id=f"currency-{value}")
            for value in CURRENCY_DISPLAYS
        ),
        pytest.param("label_language", "en", id="language-en"),
        pytest.param("label_language", "de", id="language-de"),
        pytest.param("label_language", "fr", id="language-fr"),
    ],
)
@pytest.mark.asyncio
async def test_async_create_zugferd_pdf_accepts_every_render_literal(
    field: str, value: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["render_options"] == {field: value}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.create_zugferd_pdf(
            invoice,
            render_options=cast(PdfZugferdRenderOptions, cast(object, {field: value})),
        )


def test_create_zugferd_pdf_rejects_invalid_resource_before_transport() -> None:
    invoice = _make_file("invoice.pdf", "application/pdf")

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match="Invoice must be an XML file"),
    ):
        client.create_zugferd_pdf(invoice)


@pytest.mark.asyncio
async def test_async_create_zugferd_pdf_rejects_invalid_resource_before_transport() -> (
    None
):
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match="requires a PDF resource"):
            await client.create_zugferd_pdf(invoice, regenerate_pdf=True)
