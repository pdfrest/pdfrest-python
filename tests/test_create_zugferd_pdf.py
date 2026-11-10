from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, cast, get_args

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import (
    PdfInvoiceXmlToZugferdPayload,
    PdfToZugferdPayload,
)
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


def _dump(model: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
    return model.model_validate(payload).model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )


def _assert_timeout(value: float | dict[str, float] | None, expected: float) -> None:
    assert value is not None
    if isinstance(value, dict):
        assert value
        assert all(component == pytest.approx(expected) for component in value.values())
    else:
        assert value == pytest.approx(expected)


def _assert_response(
    response: PdfRestFileBasedResponse,
    *,
    input_ids: list[PdfRestFileID],
    output_id: PdfRestFileID,
    output_name: str,
) -> None:
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.input_ids == input_ids
    assert response.warning is None
    assert len(response.output_files) == 1
    assert response.output_file.id == output_id
    assert response.output_file.name == output_name
    assert response.output_file.type == "application/pdf"
    assert response.output_file.size == 256
    assert str(response.output_file.url).endswith(f"/resource/{output_id}")


def test_invoice_xml_payload_serializes_all_render_options() -> None:
    invoice = _make_file("invoice.xml", "application/xml", prefix=1)
    logo = _make_file("logo.png", "image/png", prefix=2)

    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {
            "invoice": invoice,
            "logo": logo,
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
                "label_language": "eng-US",
                "currency_display": "symbol",
                "date_format": "dd.MM.yyyy",
                "decimal_precision": 3,
            },
        },
    )

    assert payload == {
        "id": str(invoice.id),
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
            "label_language": "en",
            "currency_display": "symbol",
            "date_format": "dd.MM.yyyy",
            "decimal_precision": 3,
        },
        "output": "customer-invoice",
    }


def test_pdf_payload_maps_regeneration_permission_to_wire_field() -> None:
    invoice = _make_file("invoice.xml", "text/xml", prefix=1)
    pdf = _make_file("invoice.pdf", "application/pdf", prefix=2)

    payload = _dump(
        PdfToZugferdPayload,
        {
            "invoice": invoice,
            "pdf": pdf,
            "regenerate_pdf": True,
            "render_options": {"label_language": "fra-FR"},
        },
    )

    assert payload == {
        "id": str(invoice.id),
        "pdf_id": str(pdf.id),
        "render_options": {"label_language": "fr"},
        "regenerate_pdf": True,
    }


COLOR_FIELDS = (
    "text_color",
    "muted_text_color",
    "accent_color",
    "border_color",
    "table_header_color",
    "table_alternate_color",
)


@pytest.mark.parametrize("field", COLOR_FIELDS)
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
    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {"invoice": invoice, "render_options": {field: color}},
    )
    assert payload["render_options"] == {f"{field}_{wire_suffix}": list(color)}


@pytest.mark.parametrize("font", KNOWN_FONTS, ids=str)
def test_zugferd_payload_accepts_every_published_font(
    font: PdfZugferdKnownFont,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {"invoice": invoice, "render_options": {"font": font}},
    )
    assert payload["render_options"] == {"font": font}


def test_zugferd_payload_accepts_unlisted_installed_font_name() -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {"invoice": invoice, "render_options": {"font": "Noto Sans"}},
    )
    assert payload["render_options"] == {"font": "Noto Sans"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("en", "en", id="english"),
        pytest.param("eng", "en", id="english-alias"),
        pytest.param("eng-US", "en", id="english-region"),
        pytest.param("de", "de", id="german"),
        pytest.param("deu", "de", id="german-alias"),
        pytest.param("fr", "fr", id="french"),
        pytest.param("fra-FR", "fr", id="french-region"),
    ],
)
def test_zugferd_payload_canonicalizes_supported_label_languages(
    value: str, expected: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {"invoice": invoice, "render_options": {"label_language": value}},
    )
    assert payload["render_options"] == {"label_language": expected}


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
    ],
)
def test_zugferd_payload_accepts_every_closed_literal(field: str, value: str) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {"invoice": invoice, "render_options": {field: value}},
    )
    assert payload["render_options"] == {field: value}


VALID_RENDER_BOUNDARIES = [
    pytest.param(
        {"decimal_precision": 0},
        {"decimal_precision": 0},
        id="precision-minimum",
    ),
    pytest.param(
        {"decimal_precision": 4},
        {"decimal_precision": 4},
        id="precision-maximum",
    ),
    pytest.param(
        {"text_color": (0, 0, 0)},
        {"text_color_rgb": [0, 0, 0]},
        id="rgb-minimum",
    ),
    pytest.param(
        {"text_color": (255, 255, 255)},
        {"text_color_rgb": [255, 255, 255]},
        id="rgb-maximum",
    ),
    pytest.param(
        {"text_color": (0, 0, 0, 0)},
        {"text_color_cmyk": [0, 0, 0, 0]},
        id="cmyk-minimum",
    ),
    pytest.param(
        {"text_color": (100, 100, 100, 100)},
        {"text_color_cmyk": [100, 100, 100, 100]},
        id="cmyk-maximum",
    ),
    pytest.param({"font": "x"}, {"font": "x"}, id="font-minimum"),
    pytest.param({"font": "x" * 200}, {"font": "x" * 200}, id="font-maximum"),
    pytest.param({"bold_font": "x"}, {"bold_font": "x"}, id="bold-font-minimum"),
    pytest.param(
        {"bold_font": "x" * 200},
        {"bold_font": "x" * 200},
        id="bold-font-maximum",
    ),
    pytest.param({"footer_message": ""}, {"footer_message": ""}, id="footer-empty"),
    pytest.param(
        {"footer_message": "x" * 500},
        {"footer_message": "x" * 500},
        id="footer-maximum",
    ),
]


@pytest.mark.parametrize(("options", "expected"), VALID_RENDER_BOUNDARIES)
def test_zugferd_payload_accepts_constraint_boundaries(
    options: dict[str, Any], expected: dict[str, Any]
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    payload = _dump(
        PdfInvoiceXmlToZugferdPayload,
        {"invoice": invoice, "render_options": options},
    )
    assert payload["render_options"] == expected


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
            {"text_color": (-1, 0, 0)}, "greater than or equal to 0", id="rgb-low"
        ),
        pytest.param(
            {"text_color": (0, 256, 0)}, "less than or equal to 255", id="rgb-high"
        ),
        pytest.param(
            {"text_color": (-1, 0, 0, 0)}, "greater than or equal to 0", id="cmyk-low"
        ),
        pytest.param(
            {"text_color": (0, 101, 0, 0)}, "less than or equal to 100", id="cmyk-high"
        ),
        pytest.param({"text_color": (0, 0)}, "exactly 3.*or 4", id="channel-count"),
        pytest.param({"font": "   "}, "at least 1 character", id="font-empty"),
        pytest.param({"font": "x" * 201}, "at most 200 characters", id="font-long"),
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
            {"label_language": "en_"},
            "String should match pattern",
            id="language-shape",
        ),
        pytest.param({"label_language": None}, "valid string", id="language-null"),
        pytest.param({"logo_corner": "center"}, "logo_corner", id="logo-corner"),
        pytest.param({"locale": "en-US"}, "locale", id="locale"),
        pytest.param({"currency_display": "iso"}, "currency_display", id="currency"),
    ],
)
def test_zugferd_payload_rejects_invalid_render_options(
    options: dict[str, Any], error_match: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    with pytest.raises(ValidationError, match=error_match):
        PdfInvoiceXmlToZugferdPayload.model_validate(
            {"invoice": invoice, "render_options": options}
        )


@pytest.mark.parametrize(
    ("payload", "error_match"),
    [
        pytest.param(
            {"invoice": _make_file("invoice.pdf", "application/pdf")},
            "Invoice must be an XML file",
            id="invoice-mime",
        ),
        pytest.param({"invoice": []}, "at least 1 item", id="invoice-empty"),
        pytest.param(
            {
                "invoice": [
                    _make_file("one.xml", "application/xml"),
                    _make_file("two.xml", "text/xml"),
                ]
            },
            "at most 1 item",
            id="invoice-extra",
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
            {"invoice": _make_file("invoice.xml", "application/xml"), "logo": []},
            "at least 1 item",
            id="logo-empty",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "logo": [
                    _make_file("one.png", "image/png"),
                    _make_file("two.jpg", "image/jpeg"),
                ],
            },
            "at most 1 item",
            id="logo-extra",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "output": "../unsafe",
            },
            "directory separator",
            id="unsafe-output",
        ),
    ],
)
def test_invoice_xml_payload_rejects_invalid_resources(
    payload: dict[str, Any], error_match: str
) -> None:
    with pytest.raises(ValidationError, match=error_match):
        PdfInvoiceXmlToZugferdPayload.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "error_match"),
    [
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "pdf": _make_file("source.png", "image/png"),
            },
            "Must be a PDF file",
            id="pdf-mime",
        ),
        pytest.param(
            {"invoice": _make_file("invoice.xml", "application/xml"), "pdf": []},
            "at least 1 item",
            id="pdf-empty",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "pdf": [
                    _make_file("one.pdf", "application/pdf"),
                    _make_file("two.pdf", "application/pdf"),
                ],
            },
            "at most 1 item",
            id="pdf-extra",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "pdf": _make_file("source.pdf", "application/pdf"),
                "logo": _make_file("logo.png", "image/png"),
            },
            "allow_regeneration=True",
            id="logo-without-permission",
        ),
        pytest.param(
            {
                "invoice": _make_file("invoice.xml", "application/xml"),
                "pdf": _make_file("source.pdf", "application/pdf"),
                "render_options": {"font": "arial"},
            },
            "allow_regeneration=True",
            id="render-without-permission",
        ),
    ],
)
def test_pdf_payload_rejects_invalid_resources(
    payload: dict[str, Any], error_match: str
) -> None:
    with pytest.raises(ValidationError, match=error_match):
        PdfToZugferdPayload.model_validate(payload)


@pytest.mark.parametrize("invoice_mime", ["application/xml", "text/xml"])
@pytest.mark.parametrize("logo_mime", ["image/png", "image/jpeg"])
def test_convert_invoice_xml_to_zugferd_pdf_supported_mime_matrix(
    invoice_mime: str, logo_mime: str
) -> None:
    invoice = _make_file("invoice.xml", invoice_mime, prefix=1)
    logo = _make_file("logo", logo_mime, prefix=2)
    output_id = PdfRestFileID.generate()
    counts = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            counts["post"] += 1
            assert request.url.path == "/zugferd-pdf"
            assert json.loads(request.content) == {
                "id": str(invoice.id),
                "logo_id": str(logo.id),
                "render_options": {"font": "arial", "label_language": "en"},
                "output": "zugferd-result",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [str(invoice.id), str(logo.id)],
                    "outputId": str(output_id),
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        counts["get"] += 1
        return httpx.Response(
            200,
            json=build_file_info_payload(
                str(output_id), "zugferd-result.pdf", "application/pdf"
            ),
        )

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            logo=logo,
            render_options={"font": "arial", "label_language": "eng-US"},
            output="zugferd-result",
        )

    assert counts == {"post": 1, "get": 1}
    _assert_response(
        response,
        input_ids=[invoice.id, logo.id],
        output_id=output_id,
        output_name="zugferd-result.pdf",
    )


@pytest.mark.parametrize("invoice_mime", ["application/xml", "text/xml"])
@pytest.mark.parametrize("logo_mime", ["image/png", "image/jpeg"])
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_supported_mime_matrix(
    invoice_mime: str, logo_mime: str
) -> None:
    invoice = _make_file("invoice.xml", invoice_mime, prefix=1)
    logo = _make_file("logo", logo_mime, prefix=2)
    output_id = PdfRestFileID.generate()
    counts = {"post": 0, "get": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            counts["post"] += 1
            assert request.url.path == "/zugferd-pdf"
            assert json.loads(request.content) == {
                "id": str(invoice.id),
                "logo_id": str(logo.id),
                "output": "zugferd-async",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [str(invoice.id), str(logo.id)],
                    "outputId": str(output_id),
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        counts["get"] += 1
        return httpx.Response(
            200,
            json=build_file_info_payload(
                str(output_id), "zugferd-async.pdf", "application/pdf"
            ),
        )

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.convert_invoice_xml_to_zugferd_pdf(
            invoice, logo=logo, output="zugferd-async"
        )

    assert counts == {"post": 1, "get": 1}
    _assert_response(
        response,
        input_ids=[invoice.id, logo.id],
        output_id=output_id,
        output_name="zugferd-async.pdf",
    )


def test_convert_pdf_to_zugferd_pdf_preserves_pdf_by_default() -> None:
    invoice = _make_file("invoice.xml", "application/xml", prefix=1)
    pdf = _make_file("invoice.pdf", "application/pdf", prefix=2)
    output_id = PdfRestFileID.generate()
    counts = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            counts["post"] += 1
            assert request.url.path == "/zugferd-pdf"
            assert json.loads(request.content) == {
                "id": str(invoice.id),
                "pdf_id": str(pdf.id),
                "regenerate_pdf": False,
                "output": "preserved",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [str(invoice.id), str(pdf.id)],
                    "outputId": str(output_id),
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        counts["get"] += 1
        return httpx.Response(
            200,
            json=build_file_info_payload(
                str(output_id), "preserved.pdf", "application/pdf"
            ),
        )

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.convert_pdf_to_zugferd_pdf(
            pdf, invoice=invoice, output="preserved"
        )

    assert counts == {"post": 1, "get": 1}
    _assert_response(
        response,
        input_ids=[invoice.id, pdf.id],
        output_id=output_id,
        output_name="preserved.pdf",
    )


@pytest.mark.asyncio
async def test_async_convert_pdf_to_zugferd_pdf_allows_regeneration_options() -> None:
    invoice = _make_file("invoice.xml", "text/xml", prefix=1)
    pdf = _make_file("invoice.pdf", "application/pdf", prefix=2)
    logo = _make_file("logo.jpg", "image/jpeg")
    output_id = PdfRestFileID.generate()
    counts = {"post": 0, "get": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            counts["post"] += 1
            assert request.url.path == "/zugferd-pdf"
            assert json.loads(request.content) == {
                "id": str(invoice.id),
                "pdf_id": str(pdf.id),
                "logo_id": str(logo.id),
                "render_options": {
                    "bold_font": "arialbold",
                    "border_color_cmyk": [0, 0, 0, 50],
                },
                "regenerate_pdf": True,
                "output": "replacement-allowed",
            }
            return httpx.Response(
                200,
                json={
                    "inputId": [str(invoice.id), str(pdf.id), str(logo.id)],
                    "outputId": str(output_id),
                },
            )
        assert request.method == "GET"
        assert request.url.path == f"/resource/{output_id}"
        counts["get"] += 1
        return httpx.Response(
            200,
            json=build_file_info_payload(
                str(output_id), "replacement-allowed.pdf", "application/pdf"
            ),
        )

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.convert_pdf_to_zugferd_pdf(
            pdf,
            invoice=invoice,
            allow_regeneration=True,
            logo=logo,
            render_options={"bold_font": "arialbold", "border_color": (0, 0, 0, 50)},
            output="replacement-allowed",
        )

    assert counts == {"post": 1, "get": 1}
    _assert_response(
        response,
        input_ids=[invoice.id, pdf.id, logo.id],
        output_id=output_id,
        output_name="replacement-allowed.pdf",
    )


@pytest.mark.parametrize("font", KNOWN_FONTS, ids=str)
def test_convert_invoice_xml_to_zugferd_pdf_accepts_every_published_font(
    font: PdfZugferdKnownFont,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {"font": font}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.convert_invoice_xml_to_zugferd_pdf(
            invoice, render_options={"font": font}
        )


@pytest.mark.parametrize("font", KNOWN_FONTS, ids=str)
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_accepts_every_published_font(
    font: PdfZugferdKnownFont,
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {"font": font}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.convert_invoice_xml_to_zugferd_pdf(
            invoice, render_options={"font": font}
        )


def test_convert_invoice_xml_to_zugferd_pdf_accepts_unlisted_font_name() -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {"font": "Noto Sans"}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.convert_invoice_xml_to_zugferd_pdf(
            invoice, render_options={"font": "Noto Sans"}
        )


@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_accepts_unlisted_font_name() -> (
    None
):
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {"font": "Noto Sans"}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.convert_invoice_xml_to_zugferd_pdf(
            invoice, render_options={"font": "Noto Sans"}
        )


CLIENT_COLOR_CASES = [
    pytest.param(field, color, suffix, id=f"{field}-{suffix}")
    for field in COLOR_FIELDS
    for color, suffix in (
        ((0, 127, 255), "rgb"),
        ((0, 25, 50, 100), "cmyk"),
    )
]

INVALID_CLIENT_COLOR_CASES = [
    pytest.param(field, color, error_match, id=f"{field}-{case_id}")
    for field in COLOR_FIELDS
    for color, error_match, case_id in (
        ((-1, 0, 0), "greater than or equal to 0", "rgb-low"),
        ((0, 256, 0), "less than or equal to 255", "rgb-high"),
        ((-1, 0, 0, 0), "greater than or equal to 0", "cmyk-low"),
        ((0, 101, 0, 0), "less than or equal to 100", "cmyk-high"),
    )
]


@pytest.mark.parametrize(("field", "color", "suffix"), CLIENT_COLOR_CASES)
def test_convert_invoice_xml_to_zugferd_pdf_serializes_every_color_option(
    field: str, color: tuple[int, ...], suffix: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {
            f"{field}_{suffix}": list(color)
        }
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    options = cast(PdfZugferdRenderOptions, cast(object, {field: color}))
    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.convert_invoice_xml_to_zugferd_pdf(invoice, render_options=options)


@pytest.mark.parametrize(("field", "color", "suffix"), CLIENT_COLOR_CASES)
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_serializes_every_color_option(
    field: str, color: tuple[int, ...], suffix: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {
            f"{field}_{suffix}": list(color)
        }
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    options = cast(PdfZugferdRenderOptions, cast(object, {field: color}))
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.convert_invoice_xml_to_zugferd_pdf(invoice, render_options=options)


@pytest.mark.parametrize(("field", "color", "error_match"), INVALID_CLIENT_COLOR_CASES)
def test_convert_invoice_xml_to_zugferd_pdf_rejects_every_invalid_color_before_transport(
    field: str, color: tuple[int, ...], error_match: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    options = cast(PdfZugferdRenderOptions, cast(object, {field: color}))
    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=error_match),
    ):
        client.convert_invoice_xml_to_zugferd_pdf(invoice, render_options=options)


@pytest.mark.parametrize(("field", "color", "error_match"), INVALID_CLIENT_COLOR_CASES)
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_rejects_every_invalid_color_before_transport(
    field: str, color: tuple[int, ...], error_match: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    options = cast(PdfZugferdRenderOptions, cast(object, {field: color}))
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match=error_match):
            await client.convert_invoice_xml_to_zugferd_pdf(
                invoice, render_options=options
            )


@pytest.mark.parametrize(("options", "expected"), VALID_RENDER_BOUNDARIES)
def test_convert_invoice_xml_to_zugferd_pdf_accepts_constraint_boundaries(
    options: dict[str, Any], expected: dict[str, Any]
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == expected
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    render_options = cast(PdfZugferdRenderOptions, cast(object, options))
    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.convert_invoice_xml_to_zugferd_pdf(
            invoice, render_options=render_options
        )


@pytest.mark.parametrize(("options", "expected"), VALID_RENDER_BOUNDARIES)
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_accepts_constraint_boundaries(
    options: dict[str, Any], expected: dict[str, Any]
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == expected
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    render_options = cast(PdfZugferdRenderOptions, cast(object, options))
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.convert_invoice_xml_to_zugferd_pdf(
            invoice, render_options=render_options
        )


CLIENT_RENDER_CASES = [
    *(
        pytest.param("logo_corner", value, value, id=f"logo-{value}")
        for value in LOGO_CORNERS
    ),
    *(pytest.param("locale", value, value, id=f"locale-{value}") for value in LOCALES),
    *(
        pytest.param("currency_display", value, value, id=f"currency-{value}")
        for value in CURRENCY_DISPLAYS
    ),
    pytest.param("label_language", "en", "en", id="language-english"),
    pytest.param("label_language", "eng", "en", id="language-english-alias"),
    pytest.param("label_language", "de", "de", id="language-german"),
    pytest.param("label_language", "deu-DE", "de", id="language-german-alias"),
    pytest.param("label_language", "fr", "fr", id="language-french"),
    pytest.param("label_language", "fra", "fr", id="language-french-alias"),
    pytest.param("date_format", "dd.MM.yyyy", "dd.MM.yyyy", id="date-format"),
]


@pytest.mark.parametrize(("field", "value", "expected"), CLIENT_RENDER_CASES)
def test_convert_invoice_xml_to_zugferd_pdf_accepts_render_contract(
    field: str, value: str, expected: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {field: expected}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    options = cast(PdfZugferdRenderOptions, cast(object, {field: value}))
    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        client.convert_invoice_xml_to_zugferd_pdf(invoice, render_options=options)


@pytest.mark.parametrize(("field", "value", "expected"), CLIENT_RENDER_CASES)
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_accepts_render_contract(
    field: str, value: str, expected: str
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert json.loads(request.content)["render_options"] == {field: expected}
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    options = cast(PdfZugferdRenderOptions, cast(object, {field: value}))
    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        await client.convert_invoice_xml_to_zugferd_pdf(invoice, render_options=options)


INVALID_GENERATION_CASES = [
    pytest.param("invoice-mime", "Invoice must be an XML file", id="invoice-mime"),
    pytest.param("invoice-empty", "at least 1 item", id="invoice-empty"),
    pytest.param("invoice-extra", "at most 1 item", id="invoice-extra"),
    pytest.param("logo-mime", "Logo must be a PNG or JPEG file", id="logo-mime"),
    pytest.param("logo-empty", "at least 1 item", id="logo-empty"),
    pytest.param("logo-extra", "at most 1 item", id="logo-extra"),
    pytest.param("invalid-corner", "logo_corner", id="invalid-corner"),
    pytest.param("invalid-locale", "locale", id="invalid-locale"),
    pytest.param("invalid-currency", "currency_display", id="invalid-currency"),
    pytest.param("malformed-color", "greater than or equal to 0", id="malformed-color"),
    pytest.param("unsafe-output", "directory separator", id="unsafe-output"),
    pytest.param("language-null", "valid string", id="language-null"),
    pytest.param("font-empty", "at least 1 character", id="font-empty"),
    pytest.param("font-long", "at most 200 characters", id="font-long"),
    pytest.param("bold-font-empty", "at least 1 character", id="bold-font-empty"),
    pytest.param("bold-font-long", "at most 200 characters", id="bold-font-long"),
    pytest.param("footer-long", "at most 500 characters", id="footer-long"),
    pytest.param("precision-low", "greater than or equal to 0", id="precision-low"),
    pytest.param("precision-high", "less than or equal to 4", id="precision-high"),
]


def _invoke_invalid_generation(client: Any, case: str) -> Any:
    invoice = _make_file("invoice.xml", "application/xml")
    cases: dict[str, tuple[Any, dict[str, Any]]] = {
        "invoice-mime": (_make_file("invoice.pdf", "application/pdf"), {}),
        "invoice-empty": ([], {}),
        "invoice-extra": (
            [invoice, _make_file("second.xml", "text/xml")],
            {},
        ),
        "logo-mime": (invoice, {"logo": _make_file("logo.gif", "image/gif")}),
        "logo-empty": (invoice, {"logo": []}),
        "logo-extra": (
            invoice,
            {
                "logo": [
                    _make_file("one.png", "image/png"),
                    _make_file("two.jpg", "image/jpeg"),
                ]
            },
        ),
        "invalid-corner": (invoice, {"render_options": {"logo_corner": "center"}}),
        "invalid-locale": (invoice, {"render_options": {"locale": "en-US"}}),
        "invalid-currency": (
            invoice,
            {"render_options": {"currency_display": "iso"}},
        ),
        "malformed-color": (
            invoice,
            {"render_options": {"text_color": (-1, 0, 0)}},
        ),
        "unsafe-output": (invoice, {"output": "../unsafe"}),
        "language-null": (
            invoice,
            {"render_options": {"label_language": None}},
        ),
        "font-empty": (invoice, {"render_options": {"font": "   "}}),
        "font-long": (invoice, {"render_options": {"font": "x" * 201}}),
        "bold-font-empty": (invoice, {"render_options": {"bold_font": "   "}}),
        "bold-font-long": (
            invoice,
            {"render_options": {"bold_font": "x" * 201}},
        ),
        "footer-long": (
            invoice,
            {"render_options": {"footer_message": "x" * 501}},
        ),
        "precision-low": (
            invoice,
            {"render_options": {"decimal_precision": -1}},
        ),
        "precision-high": (
            invoice,
            {"render_options": {"decimal_precision": 5}},
        ),
    }
    invoice, kwargs = cases[case]
    return client.convert_invoice_xml_to_zugferd_pdf(invoice, **kwargs)


@pytest.mark.parametrize(("case", "error_match"), INVALID_GENERATION_CASES)
def test_convert_invoice_xml_to_zugferd_pdf_rejects_invalid_input_before_transport(
    case: str, error_match: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=error_match),
    ):
        _invoke_invalid_generation(client, case)


@pytest.mark.parametrize(("case", "error_match"), INVALID_GENERATION_CASES)
@pytest.mark.asyncio
async def test_async_convert_invoice_xml_to_zugferd_pdf_rejects_invalid_input_before_transport(
    case: str, error_match: str
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match=error_match):
            await _invoke_invalid_generation(client, case)


INVALID_PDF_CASES = [
    pytest.param("pdf-mime", "Must be a PDF file", id="pdf-mime"),
    pytest.param("pdf-empty", "at least 1 item", id="pdf-empty"),
    pytest.param("pdf-extra", "at most 1 item", id="pdf-extra"),
    pytest.param("invoice-mime", "Invoice must be an XML file", id="invoice-mime"),
    pytest.param("invoice-empty", "at least 1 item", id="invoice-empty"),
    pytest.param("invoice-extra", "at most 1 item", id="invoice-extra"),
    pytest.param("logo-mime", "Logo must be a PNG or JPEG file", id="logo-mime"),
    pytest.param("logo-empty", "at least 1 item", id="logo-empty"),
    pytest.param("logo-extra", "at most 1 item", id="logo-extra"),
    pytest.param(
        "logo-without-permission",
        "allow_regeneration=True",
        id="logo-without-permission",
    ),
    pytest.param(
        "render-without-permission",
        "allow_regeneration=True",
        id="render-without-permission",
    ),
]


def _invoke_invalid_pdf_conversion(client: Any, case: str) -> Any:
    pdf: Any = _make_file("source.pdf", "application/pdf")
    invoice: Any = _make_file("invoice.xml", "application/xml")
    kwargs: dict[str, Any] = {}
    if case == "pdf-mime":
        pdf = _make_file("source.png", "image/png")
    elif case == "pdf-empty":
        pdf = []
    elif case == "pdf-extra":
        pdf = [pdf, _make_file("second.pdf", "application/pdf")]
    elif case == "invoice-mime":
        invoice = _make_file("invoice.pdf", "application/pdf")
    elif case == "invoice-empty":
        invoice = []
    elif case == "invoice-extra":
        invoice = [invoice, _make_file("second.xml", "text/xml")]
    elif case == "logo-mime":
        kwargs.update(allow_regeneration=True, logo=_make_file("logo.gif", "image/gif"))
    elif case in {"logo-empty", "logo-extra"}:
        logos = {
            "logo-empty": [],
            "logo-extra": [
                _make_file("one.png", "image/png"),
                _make_file("two.jpg", "image/jpeg"),
            ],
        }
        kwargs.update(
            allow_regeneration=True,
            logo=logos[case],
        )
    elif case == "logo-without-permission":
        kwargs["logo"] = _make_file("logo.png", "image/png")
    else:
        kwargs["render_options"] = {"font": "arial"}
    return client.convert_pdf_to_zugferd_pdf(pdf, invoice=invoice, **kwargs)


@pytest.mark.parametrize(("case", "error_match"), INVALID_PDF_CASES)
def test_convert_pdf_to_zugferd_pdf_rejects_invalid_input_before_transport(
    case: str, error_match: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=error_match),
    ):
        _invoke_invalid_pdf_conversion(client, case)


@pytest.mark.parametrize(("case", "error_match"), INVALID_PDF_CASES)
@pytest.mark.asyncio
async def test_async_convert_pdf_to_zugferd_pdf_rejects_invalid_input_before_transport(
    case: str, error_match: str
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match=error_match):
            await _invoke_invalid_pdf_conversion(client, case)


@pytest.mark.parametrize(
    ("method_name", "expected_body"),
    [
        pytest.param(
            "convert_invoice_xml_to_zugferd_pdf",
            {"regenerate_pdf": False},
            id="invoice-xml",
        ),
        pytest.param(
            "convert_pdf_to_zugferd_pdf",
            {"regenerate_pdf": False},
            id="supplied-pdf",
        ),
    ],
)
def test_zugferd_sync_request_customization(
    method_name: str, expected_body: dict[str, Any]
) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    pdf = _make_file("source.pdf", "application/pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert request.url.params["trace"] == "sync"
        assert request.headers["X-Trace"] == "zugferd"
        _assert_timeout(request.extensions.get("timeout"), 14.0)
        body = json.loads(request.content)
        assert body["server_debug"] is True
        if method_name == "convert_pdf_to_zugferd_pdf":
            assert body["regenerate_pdf"] is expected_body["regenerate_pdf"]
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        method = getattr(client, method_name)
        kwargs = {
            "extra_query": {"trace": "sync"},
            "extra_headers": {"X-Trace": "zugferd"},
            "extra_body": {"server_debug": True},
            "timeout": 14.0,
        }
        if method_name == "convert_pdf_to_zugferd_pdf":
            response = method(pdf, invoice=invoice, **kwargs)
        else:
            response = method(invoice, **kwargs)
    assert response.input_id == invoice.id
    assert response.output_files == []


@pytest.mark.parametrize(
    "method_name",
    [
        pytest.param("convert_invoice_xml_to_zugferd_pdf", id="invoice-xml"),
        pytest.param("convert_pdf_to_zugferd_pdf", id="supplied-pdf"),
    ],
)
@pytest.mark.asyncio
async def test_zugferd_async_request_customization(method_name: str) -> None:
    invoice = _make_file("invoice.xml", "application/xml")
    pdf = _make_file("source.pdf", "application/pdf")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/zugferd-pdf"
        assert request.url.params["trace"] == "async"
        assert request.headers["X-Trace"] == "zugferd-async"
        _assert_timeout(request.extensions.get("timeout"), 21.0)
        assert json.loads(request.content)["server_debug"] is True
        return httpx.Response(200, json={"inputId": str(invoice.id)})

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        method = getattr(client, method_name)
        kwargs = {
            "extra_query": {"trace": "async"},
            "extra_headers": {"X-Trace": "zugferd-async"},
            "extra_body": {"server_debug": True},
            "timeout": 21.0,
        }
        if method_name == "convert_pdf_to_zugferd_pdf":
            response = await method(pdf, invoice=invoice, **kwargs)
        else:
            response = await method(invoice, **kwargs)
    assert response.input_id == invoice.id
    assert response.output_files == []
