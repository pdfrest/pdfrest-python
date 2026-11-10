from __future__ import annotations

from typing import Literal, TypedDict, cast, get_args

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import ExtractedTextDocument, PdfRestFile
from pdfrest.types import (
    PdfZugferdCurrencyDisplay,
    PdfZugferdKnownFont,
    PdfZugferdLabelLanguage,
    PdfZugferdLocale,
    PdfZugferdLogoCorner,
    PdfZugferdRenderOptions,
)

from ..resources import get_test_resource_path


class ZugferdResources(TypedDict):
    invoice: PdfRestFile
    multi_item_invoice: PdfRestFile
    logo: PdfRestFile
    mismatched_pdf: PdfRestFile
    matching_pdf: PdfRestFile


LOGO_CORNERS = cast(tuple[PdfZugferdLogoCorner, ...], get_args(PdfZugferdLogoCorner))
LOCALES = cast(tuple[PdfZugferdLocale, ...], get_args(PdfZugferdLocale))
CURRENCY_DISPLAYS = cast(
    tuple[PdfZugferdCurrencyDisplay, ...], get_args(PdfZugferdCurrencyDisplay)
)
LABEL_LANGUAGES = cast(tuple[str, ...], get_args(get_args(PdfZugferdLabelLanguage)[0]))
KNOWN_FONTS = cast(tuple[PdfZugferdKnownFont, ...], get_args(PdfZugferdKnownFont))


ISOLATED_RENDER_OPTION_CASES = [
    *(
        pytest.param(
            PdfZugferdRenderOptions(logo_corner=value),
            f"logo-{value}",
            id=f"logo-{value}",
        )
        for value in LOGO_CORNERS
    ),
    *(
        pytest.param(
            PdfZugferdRenderOptions(locale=value),
            f"locale-{value}",
            id=f"locale-{value}",
        )
        for value in LOCALES
    ),
    *(
        pytest.param(
            PdfZugferdRenderOptions(label_language=value),
            f"language-{value}",
            id=f"language-{value}",
        )
        for value in LABEL_LANGUAGES
    ),
    *(
        pytest.param(
            PdfZugferdRenderOptions(currency_display=value),
            f"currency-{value}",
            id=f"currency-{value}",
        )
        for value in CURRENCY_DISPLAYS
    ),
    pytest.param(
        PdfZugferdRenderOptions(decimal_precision=0),
        "precision-minimum",
        id="precision-minimum",
    ),
    pytest.param(
        PdfZugferdRenderOptions(decimal_precision=4),
        "precision-maximum",
        id="precision-maximum",
    ),
]

INVALID_RENDER_OPTION_CASES = [
    pytest.param(
        {"logo_corner": "center"}, r"(?i)logo.corner|invalid", id="logo-corner"
    ),
    pytest.param({"currency_display": "iso"}, r"(?i)currency|invalid", id="currency"),
    pytest.param({"locale": "en-US"}, r"(?i)locale|invalid", id="locale"),
    pytest.param(
        {"decimal_precision": -1},
        r"(?i)decimal|precision|range|invalid",
        id="precision-low",
    ),
    pytest.param(
        {"decimal_precision": 5},
        r"(?i)decimal|precision|range|invalid",
        id="precision-high",
    ),
    pytest.param(
        {"text_color_rgb": [-1, 0, 0]}, r"(?i)color|range|invalid", id="rgb-low"
    ),
    pytest.param(
        {"text_color_rgb": [0, 256, 0]}, r"(?i)color|range|invalid", id="rgb-high"
    ),
    pytest.param(
        {"text_color_cmyk": [-1, 0, 0, 0]}, r"(?i)color|range|invalid", id="cmyk-low"
    ),
    pytest.param(
        {"text_color_cmyk": [0, 101, 0, 0]}, r"(?i)color|range|invalid", id="cmyk-high"
    ),
]


@pytest.fixture(scope="module")
def uploaded_zugferd_resources(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> ZugferdResources:
    paths = [
        get_test_resource_path("zugferd-minimum-invoice.xml"),
        get_test_resource_path("zugferd-basic-two-items.xml"),
        get_test_resource_path("signing_logo.png"),
        get_test_resource_path("report.pdf"),
    ]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        invoice, multi_item_invoice, logo, mismatched_pdf = (
            client.files.create_from_paths(paths)
        )
        matching_pdf = client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            output="matching-zugferd-source",
        ).output_file
    return ZugferdResources(
        invoice=invoice,
        multi_item_invoice=multi_item_invoice,
        logo=logo,
        mismatched_pdf=mismatched_pdf,
        matching_pdf=matching_pdf,
    )


def _assert_zugferd_output(
    output: PdfRestFile,
    output_bytes: bytes,
    output_prefix: str,
) -> None:
    assert output.name.startswith(output_prefix)
    assert output.name.endswith(".pdf")
    assert output.type == "application/pdf"
    assert output.size == len(output_bytes)
    assert output.size > 0
    assert f"/resource/{output.id}" in str(output.url)
    assert output_bytes.startswith(b"%PDF-")


def _render_first_page(
    client: PdfRestClient, source: PdfRestFile, output: str
) -> bytes:
    response = client.convert_to_png(
        source,
        page_range="1",
        output_prefix=output,
    )
    assert len(response.output_files) == 1
    return client.files.read_bytes(response.output_files[0])


async def _render_first_page_async(
    client: AsyncPdfRestClient,
    source: PdfRestFile,
    output: str,
) -> bytes:
    response = await client.convert_to_png(
        source,
        page_range="1",
        output_prefix=output,
    )
    assert len(response.output_files) == 1
    return await client.files.read_bytes(response.output_files[0])


def _font_names(document: ExtractedTextDocument) -> set[str]:
    assert document.words is not None
    names = {word.style.font.name for word in document.words if word.style is not None}
    assert names
    return names


FONT_RENDER_OPTION_CASES = [
    pytest.param(
        PdfZugferdRenderOptions(font="courier"),
        ("courier",),
        "known-body-font",
        id="known-body-font",
    ),
    pytest.param(
        PdfZugferdRenderOptions(font="Noto Sans"),
        ("noto", "sans"),
        "installed-body-font",
        id="installed-body-font",
    ),
    pytest.param(
        PdfZugferdRenderOptions(bold_font="courierbold"),
        ("courier", "bold"),
        "bold-font",
        id="bold-font",
    ),
]

OBSERVABLE_VISUAL_CASES = [
    pytest.param(
        PdfZugferdRenderOptions(border_color=(255, 0, 0)),
        "border-color",
        None,
        "invoice",
        id="border-color",
    ),
    pytest.param(
        PdfZugferdRenderOptions(table_alternate_color=(255, 255, 0)),
        "alternate-row-color",
        None,
        "multi_item_invoice",
        id="alternate-row-color",
    ),
    pytest.param(
        PdfZugferdRenderOptions(footer_message="Observable review footer"),
        "footer-message",
        "Observable review footer",
        "invoice",
        id="footer-message",
    ),
]


@pytest.mark.parametrize(("render_options", "output"), ISOLATED_RENDER_OPTION_CASES)
def test_live_convert_invoice_xml_to_zugferd_pdf_isolated_render_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    render_options: PdfZugferdRenderOptions,
    output: str,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    logo = uploaded_zugferd_resources["logo"]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            logo=logo,
            render_options=render_options,
            output=output,
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert response.input_ids == [invoice.id, logo.id]
    assert response.warning is None
    _assert_zugferd_output(response.output_file, output_bytes, output)


@pytest.mark.parametrize(("render_options", "output"), ISOLATED_RENDER_OPTION_CASES)
@pytest.mark.asyncio
async def test_live_async_convert_invoice_xml_to_zugferd_pdf_isolated_render_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    render_options: PdfZugferdRenderOptions,
    output: str,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    logo = uploaded_zugferd_resources["logo"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            logo=logo,
            render_options=render_options,
            output=f"async-{output}",
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert response.input_ids == [invoice.id, logo.id]
    assert response.warning is None
    _assert_zugferd_output(response.output_file, output_bytes, f"async-{output}")


@pytest.mark.parametrize(
    ("render_options", "expected_font_fragments", "output"),
    FONT_RENDER_OPTION_CASES,
)
def test_live_convert_invoice_xml_to_zugferd_pdf_uses_requested_font_resource(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    render_options: PdfZugferdRenderOptions,
    expected_font_fragments: tuple[str, ...],
    output: str,
) -> None:
    assert "courier" in KNOWN_FONTS
    assert "Noto Sans" not in KNOWN_FONTS
    invoice = uploaded_zugferd_resources["invoice"]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            render_options=render_options,
            output=output,
        )
        output_bytes = client.files.read_bytes(response.output_file)
        extracted = client.extract_pdf_text(
            response.output_file,
            word_style=True,
        )

    names = {name.lower() for name in _font_names(extracted)}
    assert any(
        all(fragment in name for fragment in expected_font_fragments) for name in names
    )
    assert response.warning is None
    _assert_zugferd_output(response.output_file, output_bytes, output)


@pytest.mark.parametrize(
    ("render_options", "expected_font_fragments", "output"),
    FONT_RENDER_OPTION_CASES,
)
@pytest.mark.asyncio
async def test_live_async_convert_invoice_xml_to_zugferd_pdf_uses_requested_font_resource(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    render_options: PdfZugferdRenderOptions,
    expected_font_fragments: tuple[str, ...],
    output: str,
) -> None:
    assert "courier" in KNOWN_FONTS
    assert "Noto Sans" not in KNOWN_FONTS
    invoice = uploaded_zugferd_resources["invoice"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            render_options=render_options,
            output=f"async-{output}",
        )
        output_bytes = await client.files.read_bytes(response.output_file)
        extracted = await client.extract_pdf_text(
            response.output_file,
            word_style=True,
        )

    names = {name.lower() for name in _font_names(extracted)}
    assert any(
        all(fragment in name for fragment in expected_font_fragments) for name in names
    )
    assert response.warning is None
    _assert_zugferd_output(
        response.output_file,
        output_bytes,
        f"async-{output}",
    )


@pytest.mark.parametrize(
    ("render_options", "output", "expected_text", "invoice_key"),
    OBSERVABLE_VISUAL_CASES,
)
def test_live_convert_invoice_xml_to_zugferd_pdf_observes_each_visual_control(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    render_options: PdfZugferdRenderOptions,
    output: str,
    expected_text: str | None,
    invoice_key: Literal["invoice", "multi_item_invoice"],
) -> None:
    invoice = uploaded_zugferd_resources[invoice_key]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        baseline = client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            output=f"baseline-{output}",
        )
        response = client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            render_options=render_options,
            output=output,
        )
        output_bytes = client.files.read_bytes(response.output_file)
        baseline_png = _render_first_page(
            client, baseline.output_file, f"base-{output}"
        )
        customized_png = _render_first_page(client, response.output_file, output)
        extracted = (
            client.extract_pdf_text(response.output_file)
            if expected_text is not None
            else None
        )

    assert customized_png != baseline_png
    if expected_text is not None:
        assert extracted is not None
        assert extracted.full_text is not None
        assert expected_text in (extracted.full_text.document_text or "")
    assert response.warning is None
    _assert_zugferd_output(response.output_file, output_bytes, output)


@pytest.mark.parametrize(
    ("render_options", "output", "expected_text", "invoice_key"),
    OBSERVABLE_VISUAL_CASES,
)
@pytest.mark.asyncio
async def test_live_async_convert_invoice_xml_to_zugferd_pdf_observes_each_visual_control(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    render_options: PdfZugferdRenderOptions,
    output: str,
    expected_text: str | None,
    invoice_key: Literal["invoice", "multi_item_invoice"],
) -> None:
    invoice = uploaded_zugferd_resources[invoice_key]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        baseline = await client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            output=f"async-baseline-{output}",
        )
        response = await client.convert_invoice_xml_to_zugferd_pdf(
            invoice,
            render_options=render_options,
            output=f"async-{output}",
        )
        output_bytes = await client.files.read_bytes(response.output_file)
        baseline_png = await _render_first_page_async(
            client,
            baseline.output_file,
            f"async-base-{output}",
        )
        customized_png = await _render_first_page_async(
            client,
            response.output_file,
            f"async-{output}",
        )
        extracted = (
            await client.extract_pdf_text(response.output_file)
            if expected_text is not None
            else None
        )

    assert customized_png != baseline_png
    if expected_text is not None:
        assert extracted is not None
        assert extracted.full_text is not None
        assert expected_text in (extracted.full_text.document_text or "")
    assert response.warning is None
    _assert_zugferd_output(
        response.output_file,
        output_bytes,
        f"async-{output}",
    )


def test_live_convert_pdf_to_zugferd_pdf_preserves_matching_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    matching_pdf = uploaded_zugferd_resources["matching_pdf"]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        source_png = _render_first_page(client, matching_pdf, "source-zugferd")
        response = client.convert_pdf_to_zugferd_pdf(
            matching_pdf,
            invoice=invoice,
            output="preserved-zugferd",
        )
        output_bytes = client.files.read_bytes(response.output_file)
        output_png = _render_first_page(
            client,
            response.output_file,
            "preserved-zugferd",
        )

    assert response.input_ids == [invoice.id, matching_pdf.id]
    assert response.warning is None
    assert output_png == source_png
    _assert_zugferd_output(response.output_file, output_bytes, "preserved-zugferd")


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_zugferd_pdf_preserves_matching_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    matching_pdf = uploaded_zugferd_resources["matching_pdf"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        source_png = await _render_first_page_async(
            client,
            matching_pdf,
            "async-source-zugferd",
        )
        response = await client.convert_pdf_to_zugferd_pdf(
            matching_pdf,
            invoice=invoice,
            output="async-preserved-zugferd",
        )
        output_bytes = await client.files.read_bytes(response.output_file)
        output_png = await _render_first_page_async(
            client,
            response.output_file,
            "async-preserved-zugferd",
        )

    assert response.input_ids == [invoice.id, matching_pdf.id]
    assert response.warning is None
    assert output_png == source_png
    _assert_zugferd_output(
        response.output_file,
        output_bytes,
        "async-preserved-zugferd",
    )


def test_live_convert_pdf_to_zugferd_pdf_rejects_mismatch_without_permission(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(
            PdfRestApiError,
            match=r"(?i)visual.consistency|comparison",
        ),
    ):
        client.convert_pdf_to_zugferd_pdf(
            uploaded_zugferd_resources["mismatched_pdf"],
            invoice=uploaded_zugferd_resources["invoice"],
        )


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_zugferd_pdf_rejects_mismatch_without_permission(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError,
            match=r"(?i)visual.consistency|comparison",
        ):
            await client.convert_pdf_to_zugferd_pdf(
                uploaded_zugferd_resources["mismatched_pdf"],
                invoice=uploaded_zugferd_resources["invoice"],
            )


def test_live_convert_pdf_to_zugferd_pdf_allows_replacement(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    mismatched_pdf = uploaded_zugferd_resources["mismatched_pdf"]
    logo = uploaded_zugferd_resources["logo"]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        source_bytes = client.files.read_bytes(mismatched_pdf)
        source_png = _render_first_page(
            client,
            mismatched_pdf,
            "source-before-replacement",
        )
        response = client.convert_pdf_to_zugferd_pdf(
            mismatched_pdf,
            invoice=invoice,
            allow_regeneration=True,
            logo=logo,
            render_options={"footer_message": "Replacement permitted"},
            output="replacement-permitted",
        )
        output_bytes = client.files.read_bytes(response.output_file)
        output_png = _render_first_page(
            client,
            response.output_file,
            "replacement-permitted",
        )
        extracted = client.extract_pdf_text(response.output_file)

    assert response.input_ids == [invoice.id, mismatched_pdf.id, logo.id]
    assert response.warning is None
    assert output_bytes != source_bytes
    assert output_png != source_png
    assert extracted.full_text is not None
    assert "Replacement permitted" in (extracted.full_text.document_text or "")
    _assert_zugferd_output(response.output_file, output_bytes, "replacement-permitted")


@pytest.mark.asyncio
async def test_live_async_convert_pdf_to_zugferd_pdf_allows_replacement(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    mismatched_pdf = uploaded_zugferd_resources["mismatched_pdf"]
    logo = uploaded_zugferd_resources["logo"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        source_bytes = await client.files.read_bytes(mismatched_pdf)
        source_png = await _render_first_page_async(
            client,
            mismatched_pdf,
            "async-source-before-replacement",
        )
        response = await client.convert_pdf_to_zugferd_pdf(
            mismatched_pdf,
            invoice=invoice,
            allow_regeneration=True,
            logo=logo,
            render_options={"footer_message": "Async replacement permitted"},
            output="async-replacement-permitted",
        )
        output_bytes = await client.files.read_bytes(response.output_file)
        output_png = await _render_first_page_async(
            client,
            response.output_file,
            "async-replacement-permitted",
        )
        extracted = await client.extract_pdf_text(response.output_file)

    assert response.input_ids == [invoice.id, mismatched_pdf.id, logo.id]
    assert response.warning is None
    assert output_bytes != source_bytes
    assert output_png != source_png
    assert extracted.full_text is not None
    assert "Async replacement permitted" in (extracted.full_text.document_text or "")
    _assert_zugferd_output(
        response.output_file,
        output_bytes,
        "async-replacement-permitted",
    )


@pytest.mark.parametrize(
    ("invalid_options", "error_match"), INVALID_RENDER_OPTION_CASES
)
def test_live_convert_invoice_xml_to_zugferd_pdf_rejects_invalid_render_options(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    invalid_options: dict[str, object],
    error_match: str,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=error_match),
    ):
        client.convert_invoice_xml_to_zugferd_pdf(
            uploaded_zugferd_resources["invoice"],
            extra_body={"render_options": invalid_options},
        )


@pytest.mark.parametrize(
    ("invalid_options", "error_match"), INVALID_RENDER_OPTION_CASES
)
@pytest.mark.asyncio
async def test_live_async_convert_invoice_xml_to_zugferd_pdf_rejects_invalid_render_options(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
    invalid_options: dict[str, object],
    error_match: str,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=error_match):
            await client.convert_invoice_xml_to_zugferd_pdf(
                uploaded_zugferd_resources["invoice"],
                extra_body={"render_options": invalid_options},
            )
