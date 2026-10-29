from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import (
    PdfRestFile,
    PdfRestFileID,
    PdfZugferdFinding,
    PdfZugferdValidationResponse,
)
from pdfrest.models._internal import PdfValidateZugferdPayload

from .graphics_test_helpers import ASYNC_API_KEY, VALID_API_KEY


def _make_file(name: str, mime_type: str) -> PdfRestFile:
    file_id = PdfRestFileID.generate()
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


def _response_payload(
    file_id: PdfRestFileID,
    *,
    status: str = "VALID",
    content_match_status: str = "CONFIRMED",
    severity: str = "WARNING",
) -> dict[str, Any]:
    return {
        "status": status,
        "pdfa": True,
        "contentMatchStatus": content_match_status,
        "inputId": str(file_id),
        "inputUrl": f"https://api.pdfrest.com/resource/{file_id}?format=file",
        "findings": [
            {
                "code": "PDF_XML_FIELD_RESULT",
                "severity": severity,
                "message": "Complete reverse validation is not available.",
                "field": "visualConsistency",
                "status": "UNVERIFIED",
                "comparisonReason": "PARTIAL_REVERSE_VALIDATION",
            }
        ],
    }


def _assert_timeout(value: float | dict[str, float] | None, expected: float) -> None:
    assert value is not None
    if isinstance(value, dict):
        assert value
        assert all(component == pytest.approx(expected) for component in value.values())
    else:
        assert value == pytest.approx(expected)


def test_validate_zugferd_payload_serializes_uploaded_pdf_id() -> None:
    pdf = _make_file("invoice.pdf", "application/pdf")

    payload = PdfValidateZugferdPayload.model_validate({"file": pdf}).model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )

    assert payload == {"id": str(pdf.id)}


@pytest.mark.parametrize(
    ("file", "error_match"),
    [
        pytest.param(
            _make_file("invoice.xml", "application/xml"),
            "Must be a PDF file",
            id="mime",
        ),
        pytest.param(
            [
                _make_file("invoice-one.pdf", "application/pdf"),
                _make_file("invoice-two.pdf", "application/pdf"),
            ],
            "at most 1 item",
            id="cardinality",
        ),
    ],
)
def test_validate_zugferd_payload_rejects_invalid_resources(
    file: PdfRestFile | list[PdfRestFile], error_match: str
) -> None:
    with pytest.raises(ValidationError, match=error_match):
        PdfValidateZugferdPayload.model_validate({"file": file})


@pytest.mark.parametrize("status", ["VALID", "INVALID"])
def test_zugferd_validation_response_accepts_status_values(status: str) -> None:
    file_id = PdfRestFileID.generate()

    response = PdfZugferdValidationResponse.model_validate(
        _response_payload(file_id, status=status)
    )

    assert response.status == status


@pytest.mark.parametrize(
    "content_match_status",
    [
        "NOT_APPLICABLE",
        "CONFIRMED",
        "UNVERIFIED",
        "FAILED",
        "ERROR",
        "DEMO_REDACTED",
    ],
)
def test_zugferd_validation_response_accepts_content_match_values(
    content_match_status: str,
) -> None:
    file_id = PdfRestFileID.generate()

    response = PdfZugferdValidationResponse.model_validate(
        _response_payload(file_id, content_match_status=content_match_status)
    )

    assert response.content_match_status == content_match_status


@pytest.mark.parametrize("severity", ["INFO", "WARNING", "BLOCKING", "ERROR"])
def test_zugferd_validation_response_accepts_finding_severities(
    severity: str,
) -> None:
    file_id = PdfRestFileID.generate()

    response = PdfZugferdValidationResponse.model_validate(
        _response_payload(file_id, severity=severity)
    )

    assert response.findings is not None
    assert response.findings[0].severity == severity


def test_zugferd_validation_response_maps_camel_case_fields() -> None:
    file_id = PdfRestFileID.generate()

    response = PdfZugferdValidationResponse.model_validate(_response_payload(file_id))

    assert response.input_id == file_id
    assert response.content_match_status == "CONFIRMED"
    assert response.input_url.endswith("?format=file")
    assert response.findings == [
        PdfZugferdFinding(
            code="PDF_XML_FIELD_RESULT",
            severity="WARNING",
            message="Complete reverse validation is not available.",
            field="visualConsistency",
            status="UNVERIFIED",
            comparison_reason="PARTIAL_REVERSE_VALIDATION",
        )
    ]


def test_zugferd_validation_response_accepts_demo_redactions() -> None:
    file_id = PdfRestFileID.generate(prefix=2)

    response = PdfZugferdValidationResponse.model_validate(
        {
            "status": "INVALID",
            "pdfa": True,
            "contentMatchStatus": "DEMO_REDACTED",
            "inputId": str(file_id),
            "inputUrl": f"https://api.pdfrest.com/resource/{file_id}?format=file",
            "findings": [
                {
                    "code": "PD******************",
                    "severity": "BLOCKING",
                    "message": "PD* ***** ***** **** *** ***** ****",
                    "field": "BT****",
                    "status": "MISMATCH",
                    "comparisonReason": "DEMO_REDACTED",
                }
            ],
            "message": "Validation details are restricted.",
        }
    )

    assert response.findings is not None
    assert response.findings[0].code == "PD******************"
    assert response.findings[0].comparison_reason == "DEMO_REDACTED"


def test_zugferd_validation_response_rejects_invalid_comparison_reason() -> None:
    file_id = PdfRestFileID.generate()
    payload = _response_payload(file_id)
    payload["findings"][0]["comparisonReason"] = "not-safe"

    with pytest.raises(ValidationError, match="comparisonReason"):
        PdfZugferdValidationResponse.model_validate(payload)


def test_validate_zugferd_pdf_success_and_response_mapping() -> None:
    pdf = _make_file("invoice.pdf", "application/pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/validated-zugferd"
        assert request.headers["Api-Key"] == VALID_API_KEY
        assert json.loads(request.content) == {"id": str(pdf.id)}
        return httpx.Response(200, json=_response_payload(pdf.id))

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.validate_zugferd_pdf(pdf)

    assert isinstance(response, PdfZugferdValidationResponse)
    assert response.status == "VALID"
    assert response.pdfa is True
    assert response.content_match_status == "CONFIRMED"
    assert response.input_id == pdf.id
    assert response.findings is not None
    assert response.findings[0].comparison_reason == "PARTIAL_REVERSE_VALIDATION"


@pytest.mark.asyncio
async def test_async_validate_zugferd_pdf_success_and_response_mapping() -> None:
    pdf = _make_file("invoice.pdf", "application/pdf")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/validated-zugferd"
        assert request.headers["Api-Key"] == ASYNC_API_KEY
        assert json.loads(request.content) == {"id": str(pdf.id)}
        payload = _response_payload(
            pdf.id, status="INVALID", content_match_status="DEMO_REDACTED"
        )
        payload["message"] = "Validation details are restricted."
        return httpx.Response(200, json=payload)

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.validate_zugferd_pdf(pdf)

    assert response.status == "INVALID"
    assert response.content_match_status == "DEMO_REDACTED"
    assert response.input_id == pdf.id
    assert response.message == "Validation details are restricted."


def test_validate_zugferd_pdf_request_customization() -> None:
    pdf = _make_file("invoice.pdf", "application/pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["trace"] == "sync"
        assert request.headers["X-Trace"] == "zugferd-validation"
        _assert_timeout(request.extensions.get("timeout"), 13.0)
        assert json.loads(request.content) == {
            "id": str(pdf.id),
            "server_debug": True,
        }
        return httpx.Response(200, json=_response_payload(pdf.id))

    with PdfRestClient(
        api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = client.validate_zugferd_pdf(
            pdf,
            extra_query={"trace": "sync"},
            extra_headers={"X-Trace": "zugferd-validation"},
            extra_body={"server_debug": True},
            timeout=13.0,
        )

    assert response.input_id == pdf.id


@pytest.mark.asyncio
async def test_async_validate_zugferd_pdf_request_customization() -> None:
    pdf = _make_file("invoice.pdf", "application/pdf")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["trace"] == "async"
        assert request.headers["X-Trace"] == "zugferd-validation-async"
        _assert_timeout(request.extensions.get("timeout"), 17.0)
        assert json.loads(request.content) == {
            "id": str(pdf.id),
            "server_debug": True,
        }
        return httpx.Response(200, json=_response_payload(pdf.id))

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.validate_zugferd_pdf(
            pdf,
            extra_query={"trace": "async"},
            extra_headers={"X-Trace": "zugferd-validation-async"},
            extra_body={"server_debug": True},
            timeout=17.0,
        )

    assert response.input_id == pdf.id


@pytest.mark.parametrize(
    ("file", "error_match"),
    [
        pytest.param(
            _make_file("invoice.xml", "application/xml"),
            "Must be a PDF file",
            id="mime",
        ),
        pytest.param(
            [
                _make_file("invoice-one.pdf", "application/pdf"),
                _make_file("invoice-two.pdf", "application/pdf"),
            ],
            "at most 1 item",
            id="cardinality",
        ),
    ],
)
def test_validate_zugferd_pdf_rejects_invalid_resource_before_transport(
    file: PdfRestFile | list[PdfRestFile], error_match: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    with (
        PdfRestClient(
            api_key=VALID_API_KEY, transport=httpx.MockTransport(handler)
        ) as client,
        pytest.raises(ValidationError, match=error_match),
    ):
        client.validate_zugferd_pdf(file)


@pytest.mark.parametrize(
    ("file", "error_match"),
    [
        pytest.param(
            _make_file("invoice.xml", "application/xml"),
            "Must be a PDF file",
            id="mime",
        ),
        pytest.param(
            [
                _make_file("invoice-one.pdf", "application/pdf"),
                _make_file("invoice-two.pdf", "application/pdf"),
            ],
            "at most 1 item",
            id="cardinality",
        ),
    ],
)
@pytest.mark.asyncio
async def test_async_validate_zugferd_pdf_rejects_invalid_resource_before_transport(
    file: PdfRestFile | list[PdfRestFile], error_match: str
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("transport must not run for invalid local input")

    async with AsyncPdfRestClient(
        api_key=ASYNC_API_KEY, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValidationError, match=error_match):
            await client.validate_zugferd_pdf(file)
