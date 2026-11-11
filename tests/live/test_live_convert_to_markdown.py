from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import ConvertToMarkdownResponse, PdfRestFileBasedResponse

from ..resources import get_test_resource_path


def test_live_convert_to_markdown_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        response = client.convert_to_markdown(uploaded)

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files
    output_file = response.output_file
    assert output_file.name.endswith(".md")
    assert output_file.type == "text/markdown"
    assert output_file.size > 0
    assert response.warning is None
    assert response.input_id == uploaded.id


@pytest.mark.asyncio
async def test_live_async_convert_to_markdown_success(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        response = await client.convert_to_markdown(uploaded, output="async-md")

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_files
    output_file = response.output_file
    assert output_file.name.startswith("async-md")
    assert output_file.type == "text/markdown"
    assert output_file.size > 0
    assert response.warning is None
    assert response.input_id == uploaded.id


def test_live_convert_to_markdown_inline(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("20-pages.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        response = client.convert_to_markdown_inline(
            uploaded,
            pages=[1, 2],
            page_break_comments=True,
        )

    assert isinstance(response, ConvertToMarkdownResponse)
    assert [
        line.strip() for line in response.markdown.splitlines() if line.strip()
    ] == [
        "<!-- Page 1 -->",
        "1",
        "<!-- Page 2 -->",
        "2",
    ]
    assert response.input_id == uploaded.id


@pytest.mark.asyncio
async def test_live_async_convert_to_markdown_inline(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("20-pages.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        response = await client.convert_to_markdown_inline(
            uploaded,
            pages=[1, 2],
            page_break_comments=True,
        )

    assert isinstance(response, ConvertToMarkdownResponse)
    assert [
        line.strip() for line in response.markdown.splitlines() if line.strip()
    ] == [
        "<!-- Page 1 -->",
        "1",
        "<!-- Page 2 -->",
        "2",
    ]
    assert response.input_id == uploaded.id


def test_live_convert_to_markdown_inline_invalid_page_break_comments(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)page break comments"):
            client.convert_to_markdown_inline(
                uploaded,
                extra_body={"page_break_comments": "maybe"},
            )


@pytest.mark.asyncio
async def test_live_async_convert_to_markdown_inline_invalid_page_break_comments(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)page break comments"):
            await client.convert_to_markdown_inline(
                uploaded,
                extra_body={"page_break_comments": "maybe"},
            )


def test_live_convert_to_markdown_invalid_pages(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = client.files.create_from_paths([resource])[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            client.convert_to_markdown(
                uploaded,
                extra_body={"pages": "last-1"},
            )


@pytest.mark.asyncio
async def test_live_async_convert_to_markdown_invalid_pages(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> None:
    resource = get_test_resource_path("report.pdf")
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        uploaded = (await client.files.create_from_paths([resource]))[0]
        with pytest.raises(PdfRestApiError, match=r"(?i)page"):
            await client.convert_to_markdown(
                uploaded,
                extra_body={"pages": "last-1"},
            )
