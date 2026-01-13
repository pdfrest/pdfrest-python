from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from pdfrest import AsyncPdfRestClient, PdfRestClient
from pdfrest.models import PdfRestFile, PdfRestFileBasedResponse, PdfRestFileID
from pdfrest.models._internal import PdfAddAttachmentPayload

from .graphics_test_helpers import (
    ASYNC_API_KEY,
    VALID_API_KEY,
    build_file_info_payload,
    make_pdf_file,
)


def make_attachment_file(
    file_id: str,
    name: str = "attachment.txt",
    mime_type: str = "text/plain",
) -> PdfRestFile:
    return PdfRestFile.model_validate(build_file_info_payload(file_id, name, mime_type))


def test_add_attachment_to_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    attachment = make_attachment_file(str(PdfRestFileID.generate()), "notes.txt")
    output_id = str(PdfRestFileID.generate())

    payload_dump = PdfAddAttachmentPayload.model_validate(
        {"files": [input_file], "attachments": [attachment], "output": "attached"}
    ).model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)

    seen: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-added-attachment"
        ):
            seen["post"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == payload_dump
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id, attachment.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            seen["get"] += 1
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id, "attached.pdf", "application/pdf"
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_attachment_to_pdf(
            input_file,
            attachment=attachment,
            output="attached",
        )

    assert seen == {"post": 1, "get": 1}
    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "attached.pdf"
    assert response.output_file.type == "application/pdf"
    assert [str(file_id) for file_id in response.input_ids] == [
        str(input_file.id),
        str(attachment.id),
    ]
    assert response.warning is None


@pytest.mark.asyncio
async def test_async_add_attachment_to_pdf_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(2))
    attachment = make_attachment_file(
        str(PdfRestFileID.generate()),
        "doc.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    output_id = str(PdfRestFileID.generate())

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-added-attachment"
        ):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["id"] == str(input_file.id)
            assert payload["id_to_attach"] == str(attachment.id)
            assert payload["output"] == "async-attachment"
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id, attachment.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-attachment.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_attachment_to_pdf(
            input_file,
            attachment=attachment,
            output="async-attachment",
        )

    assert isinstance(response, PdfRestFileBasedResponse)
    assert response.output_file.name == "async-attachment.pdf"
    assert [str(file_id) for file_id in response.input_ids] == [
        str(input_file.id),
        str(attachment.id),
    ]


def test_add_attachment_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate())
    attachment = make_attachment_file(
        str(PdfRestFileID.generate()),
        "image.png",
        "image/png",
    )
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-added-attachment"
        ):
            assert request.url.params["trace"] == "sync"
            assert request.headers["X-Debug"] == "sync"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["id"] == str(input_file.id)
            assert payload["id_to_attach"] == str(attachment.id)
            assert payload["output"] == "custom-output"
            assert payload["diagnostics"] == "on"
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id, attachment.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "sync"
            assert request.headers["X-Debug"] == "sync"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "custom-output.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    with PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client:
        response = client.add_attachment_to_pdf(
            input_file,
            attachment=attachment,
            output="custom-output",
            extra_query={"trace": "sync"},
            extra_headers={"X-Debug": "sync"},
            extra_body={"diagnostics": "on"},
            timeout=0.5,
        )

    assert response.output_file.name == "custom-output.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(pytest.approx(0.5) == value for value in timeout_value.values())
    else:
        assert timeout_value == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_async_add_attachment_to_pdf_request_customization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    input_file = make_pdf_file(PdfRestFileID.generate(1))
    attachment = make_attachment_file(
        str(PdfRestFileID.generate()),
        "data.json",
        "application/json",
    )
    output_id = str(PdfRestFileID.generate())
    captured_timeout: dict[str, float | dict[str, float] | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.method == "POST"
            and request.url.path == "/pdf-with-added-attachment"
        ):
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            captured_timeout["value"] = request.extensions.get("timeout")
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["id"] == str(input_file.id)
            assert payload["id_to_attach"] == str(attachment.id)
            assert payload["output"] == "async-output"
            assert payload["notify"] == "yes"
            return httpx.Response(
                200,
                json={
                    "inputId": [input_file.id, attachment.id],
                    "outputId": [output_id],
                },
            )
        if request.method == "GET" and request.url.path == f"/resource/{output_id}":
            assert request.url.params["format"] == "info"
            assert request.url.params["trace"] == "async"
            assert request.headers["X-Debug"] == "async"
            return httpx.Response(
                200,
                json=build_file_info_payload(
                    output_id,
                    "async-output.pdf",
                    "application/pdf",
                ),
            )
        msg = f"Unexpected request {request.method} {request.url}"
        raise AssertionError(msg)

    transport = httpx.MockTransport(handler)
    async with AsyncPdfRestClient(api_key=ASYNC_API_KEY, transport=transport) as client:
        response = await client.add_attachment_to_pdf(
            input_file,
            attachment=attachment,
            output="async-output",
            extra_query={"trace": "async"},
            extra_headers={"X-Debug": "async"},
            extra_body={"notify": "yes"},
            timeout=1.25,
        )

    assert response.output_file.name == "async-output.pdf"
    timeout_value = captured_timeout["value"]
    assert timeout_value is not None
    if isinstance(timeout_value, dict):
        assert all(pytest.approx(1.25) == value for value in timeout_value.values())
    else:
        assert timeout_value == pytest.approx(1.25)


def test_add_attachment_to_pdf_requires_pdf_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDFREST_API_KEY", raising=False)
    not_pdf = make_attachment_file(
        str(PdfRestFileID.generate()),
        "image.png",
        "image/png",
    )
    attachment = make_attachment_file(str(PdfRestFileID.generate()), "note.txt")
    transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(RuntimeError("should not send"))
    )

    with (
        PdfRestClient(api_key=VALID_API_KEY, transport=transport) as client,
        pytest.raises(ValidationError, match="Must be a PDF file"),
    ):
        client.add_attachment_to_pdf(not_pdf, attachment=attachment)


@pytest.mark.parametrize(
    "payload_data",
    [
        pytest.param(
            lambda pdf, attachment: {
                "files": [pdf, make_pdf_file(PdfRestFileID.generate())],
                "attachments": [attachment],
            },
            id="multiple-input-files",
        ),
        pytest.param(
            lambda pdf, attachment: {
                "files": [pdf],
                "attachments": [
                    attachment,
                    make_attachment_file(str(PdfRestFileID.generate())),
                ],
            },
            id="multiple-attachments",
        ),
    ],
)
def test_add_attachment_to_pdf_rejects_multiple_files(
    payload_data: Callable[[PdfRestFile, PdfRestFile], dict[str, object]],
) -> None:
    input_file = make_pdf_file(PdfRestFileID.generate())
    attachment = make_attachment_file(str(PdfRestFileID.generate()))

    with pytest.raises(ValidationError):
        PdfAddAttachmentPayload.model_validate(payload_data(input_file, attachment))
