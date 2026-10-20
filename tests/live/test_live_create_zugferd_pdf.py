from __future__ import annotations

from typing import TypedDict

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile
from pdfrest.types import PdfZugferdRenderOptions

from ..resources import get_test_resource_path


class ZugferdResources(TypedDict):
    invoice: PdfRestFile
    logo: PdfRestFile
    pdf: PdfRestFile


RENDER_OPTION_CASES = [
    pytest.param(
        PdfZugferdRenderOptions(
            logo_corner="top-left",
            font="courier",
            text_color=(0, 0, 0),
            locale="de-DE",
            label_language="en",
            currency_display="code",
            decimal_precision=0,
        ),
        "top-left-de",
        id="top-left-german-code",
    ),
    pytest.param(
        PdfZugferdRenderOptions(
            logo_corner="top-right",
            font="DejaVu Sans",
            muted_text_color=(10, 5, 0, 55),
            locale="fr-FR",
            label_language="de",
            currency_display="symbol",
            decimal_precision=1,
        ),
        "top-right-fr",
        id="top-right-french-symbol",
    ),
    pytest.param(
        PdfZugferdRenderOptions(
            logo_corner="bottom-left",
            accent_color=(20, 64, 115),
            locale="nl-NL",
            label_language="fr",
            currency_display="name",
            decimal_precision=4,
        ),
        "bottom-left-nl",
        id="bottom-left-dutch-name",
    ),
    pytest.param(
        PdfZugferdRenderOptions(
            logo_corner="bottom-right",
            table_header_color=(83, 44, 0, 55),
            locale="en-GB",
            label_language="en-US",
            currency_display="code",
            date_format="dd/MM/yyyy",
            decimal_precision=2,
        ),
        "bottom-right-en",
        id="bottom-right-english-region",
    ),
]


@pytest.fixture(scope="module")
def uploaded_zugferd_resources(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> ZugferdResources:
    paths = [
        get_test_resource_path("zugferd-minimum-invoice.xml"),
        get_test_resource_path("signing_logo.png"),
        get_test_resource_path("report.pdf"),
    ]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        invoice, logo, pdf = client.files.create_from_paths(paths)
    return ZugferdResources(invoice=invoice, logo=logo, pdf=pdf)


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


@pytest.mark.parametrize(("render_options", "output"), RENDER_OPTION_CASES)
def test_live_create_zugferd_pdf_render_options(
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
        response = client.create_zugferd_pdf(
            invoice,
            logo=logo,
            render_options=render_options,
            output=output,
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert response.input_ids == [invoice.id, logo.id]
    assert response.warning is None
    _assert_zugferd_output(response.output_file, output_bytes, output)


@pytest.mark.parametrize(("render_options", "output"), RENDER_OPTION_CASES)
@pytest.mark.asyncio
async def test_live_async_create_zugferd_pdf_render_options(
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
        response = await client.create_zugferd_pdf(
            invoice,
            logo=logo,
            render_options=render_options,
            output=f"async-{output}",
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert response.input_ids == [invoice.id, logo.id]
    assert response.warning is None
    _assert_zugferd_output(response.output_file, output_bytes, f"async-{output}")


def test_live_create_zugferd_pdf_regenerates_mismatched_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    pdf = uploaded_zugferd_resources["pdf"]
    logo = uploaded_zugferd_resources["logo"]
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.create_zugferd_pdf(
            invoice,
            pdf=pdf,
            logo=logo,
            regenerate_pdf=True,
            output="regenerated-zugferd",
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert response.input_ids == [invoice.id, pdf.id, logo.id]
    _assert_zugferd_output(response.output_file, output_bytes, "regenerated-zugferd")


@pytest.mark.asyncio
async def test_live_async_create_zugferd_pdf_regenerates_mismatched_pdf(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    invoice = uploaded_zugferd_resources["invoice"]
    pdf = uploaded_zugferd_resources["pdf"]
    logo = uploaded_zugferd_resources["logo"]
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.create_zugferd_pdf(
            invoice,
            pdf=pdf,
            logo=logo,
            regenerate_pdf=True,
            output="async-regenerated-zugferd",
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert response.input_ids == [invoice.id, pdf.id, logo.id]
    _assert_zugferd_output(
        response.output_file, output_bytes, "async-regenerated-zugferd"
    )


def test_live_create_zugferd_pdf_rejects_invalid_render_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)locale|invalid"),
    ):
        client.create_zugferd_pdf(
            uploaded_zugferd_resources["invoice"],
            extra_body={"render_options": {"locale": "xx-XX"}},
        )


@pytest.mark.asyncio
async def test_live_async_create_zugferd_pdf_rejects_invalid_render_option(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_zugferd_resources: ZugferdResources,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)locale|invalid"):
            await client.create_zugferd_pdf(
                uploaded_zugferd_resources["invoice"],
                extra_body={"render_options": {"locale": "xx-XX"}},
            )
