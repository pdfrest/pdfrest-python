from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient


@pytest.mark.parametrize(
    "output_name",
    [
        pytest.param(None, id="default-output"),
        pytest.param("blank-doc", id="custom-output"),
    ],
)
def test_live_blank_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    output_name: str | None,
) -> None:
    kwargs: dict[str, str | int] = {
        "page_size": "letter",
        "page_count": 1,
        "page_orientation": "portrait",
    }
    if output_name is not None:
        kwargs["output"] = output_name

    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.blank_pdf(**kwargs)

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None
    if output_name is not None:
        assert output_file.name.startswith(output_name)
    else:
        assert output_file.name.endswith(".pdf")


@pytest.mark.asyncio
async def test_live_async_blank_pdf_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.blank_pdf(
            page_size="A4",
            page_count=2,
            page_orientation="landscape",
            output="async-blank",
        )

    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async-blank")
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert response.warning is None


def test_live_blank_pdf_invalid_request(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)(page|size)"),
    ):
        client.blank_pdf(
            page_size="letter",
            page_count=1,
            page_orientation="portrait",
            extra_body={"page_size": "not-a-size"},
        )


@pytest.mark.asyncio
async def test_live_async_blank_pdf_invalid_request(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(PdfRestApiError, match=r"(?i)(page|size)"):
            await client.blank_pdf(
                page_size="letter",
                page_count=1,
                page_orientation="portrait",
                extra_body={"page_size": "bad-size"},
            )
