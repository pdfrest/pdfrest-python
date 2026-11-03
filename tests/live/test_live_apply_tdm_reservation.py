from __future__ import annotations

import pytest

from pdfrest import AsyncPdfRestClient, PdfRestApiError, PdfRestClient
from pdfrest.models import PdfRestFile

from ..resources import get_test_resource_path

POLICY_URL = "https://example.com/terms/tdm-policy"


@pytest.fixture(scope="module")
def uploaded_pdf_for_tdm_reservation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
) -> PdfRestFile:
    resource = get_test_resource_path("report.pdf")
    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        return client.files.create_from_paths([resource])[0]


@pytest.mark.parametrize(
    "output_name",
    [
        pytest.param(None, id="default-output"),
        pytest.param("tdm-reserved-live", id="custom-output"),
    ],
)
def test_live_apply_tdm_reservation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_tdm_reservation: PdfRestFile,
    output_name: str | None,
) -> None:
    kwargs: dict[str, str] = {}
    if output_name is not None:
        kwargs["output"] = output_name

    with PdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = client.apply_tdm_reservation(
            uploaded_pdf_for_tdm_reservation,
            policy=POLICY_URL,
            **kwargs,
        )
        output_bytes = client.files.read_bytes(response.output_file)

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert output_file.url is not None
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_tdm_reservation.id)
    assert POLICY_URL.encode() in output_bytes
    assert b"tdm:policy" in output_bytes
    if output_name is not None:
        assert output_file.name.startswith(output_name)
    else:
        assert output_file.name.endswith(".pdf")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_name",
    [
        pytest.param(None, id="default-output"),
        pytest.param("tdm-reserved-live-async", id="custom-output"),
    ],
)
async def test_live_async_apply_tdm_reservation(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_tdm_reservation: PdfRestFile,
    output_name: str | None,
) -> None:
    kwargs: dict[str, str] = {}
    if output_name is not None:
        kwargs["output"] = output_name

    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        response = await client.apply_tdm_reservation(
            uploaded_pdf_for_tdm_reservation,
            policy=POLICY_URL,
            **kwargs,
        )
        output_bytes = await client.files.read_bytes(response.output_file)

    assert response.output_files
    output_file = response.output_file
    assert output_file.type == "application/pdf"
    assert output_file.size > 0
    assert output_file.url is not None
    assert response.warning is None
    assert str(response.input_id) == str(uploaded_pdf_for_tdm_reservation.id)
    assert POLICY_URL.encode() in output_bytes
    assert b"tdm:policy" in output_bytes
    if output_name is not None:
        assert output_file.name.startswith(output_name)
    else:
        assert output_file.name.endswith(".pdf")


def test_live_apply_tdm_reservation_rejects_missing_policy(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_tdm_reservation: PdfRestFile,
) -> None:
    with (
        PdfRestClient(
            api_key=pdfrest_api_key,
            base_url=pdfrest_live_base_url,
        ) as client,
        pytest.raises(PdfRestApiError, match=r"(?i)TDM policy setting is required"),
    ):
        client.apply_tdm_reservation(
            uploaded_pdf_for_tdm_reservation,
            policy=POLICY_URL,
            extra_body={"policy": ""},
        )


@pytest.mark.asyncio
async def test_live_async_apply_tdm_reservation_rejects_missing_policy(
    pdfrest_api_key: str,
    pdfrest_live_base_url: str,
    uploaded_pdf_for_tdm_reservation: PdfRestFile,
) -> None:
    async with AsyncPdfRestClient(
        api_key=pdfrest_api_key,
        base_url=pdfrest_live_base_url,
    ) as client:
        with pytest.raises(
            PdfRestApiError,
            match=r"(?i)TDM policy setting is required",
        ):
            await client.apply_tdm_reservation(
                uploaded_pdf_for_tdm_reservation,
                policy=POLICY_URL,
                extra_body={"policy": ""},
            )
