"""Sync and async client interfaces for the pdfrest API."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
import random
import time
import uuid
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterator,
    Mapping,
    Sequence,
)
from contextlib import ExitStack
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from os import PathLike
from pathlib import Path
from typing import (
    IO,
    Any,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
)

import httpx
from httpx import URL
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
)
from typing_extensions import override

from .exceptions import (
    PdfRestApiError,
    PdfRestAuthenticationError,
    PdfRestConfigurationError,
    PdfRestConnectTimeoutError,
    PdfRestDeleteError,
    PdfRestError,
    PdfRestErrorGroup,
    PdfRestPoolTimeoutError,
    PdfRestRequestError,
    PdfRestTimeoutError,
    PdfRestTransportError,
    translate_httpx_error,
)
from .models import (
    ExtractedTextDocument,
    PdfRestDeletionResponse,
    PdfRestErrorResponse,
    PdfRestFile,
    PdfRestFileBasedResponse,
    PdfRestFileID,
    PdfRestInfoResponse,
    SummarizePdfTextResponse,
    TranslatePdfTextFileResponse,
    TranslatePdfTextResponse,
    UpResponse,
)
from .models._internal import (
    BasePdfRestGraphicPayload,
    BmpPdfRestPayload,
    ConvertEmailToPdfPayload,
    ConvertHtmlToPdfPayload,
    ConvertImageToPdfPayload,
    ConvertOfficeToPdfPayload,
    ConvertPostscriptToPdfPayload,
    ConvertToMarkdownPayload,
    ConvertUrlToPdfPayload,
    DeletePayload,
    ExtractImagesPayload,
    ExtractTextPayload,
    GifPdfRestPayload,
    JpegPdfRestPayload,
    OcrPdfPayload,
    PdfAddAttachmentPayload,
    PdfAddImagePayload,
    PdfAddTextPayload,
    PdfBlankPayload,
    PdfCompressPayload,
    PdfConvertColorsPayload,
    PdfDecryptPayload,
    PdfEncryptPayload,
    PdfExportFormDataPayload,
    PdfFlattenAnnotationsPayload,
    PdfFlattenFormsPayload,
    PdfFlattenLayersPayload,
    PdfFlattenTransparenciesPayload,
    PdfImageWatermarkPayload,
    PdfImportFormDataPayload,
    PdfInfoPayload,
    PdfLinearizePayload,
    PdfMergePayload,
    PdfRasterizePayload,
    PdfRedactionApplyPayload,
    PdfRedactionPreviewPayload,
    PdfRestRawFileResponse,
    PdfRestrictPayload,
    PdfSignPayload,
    PdfSplitPayload,
    PdfTextWatermarkPayload,
    PdfToExcelPayload,
    PdfToPdfaPayload,
    PdfToPdfxPayload,
    PdfToPowerpointPayload,
    PdfToWordPayload,
    PdfUnrestrictPayload,
    PdfXfaToAcroformsPayload,
    PngPdfRestPayload,
    SummarizePdfTextPayload,
    TiffPdfRestPayload,
    TranslatePdfTextPayload,
    UnzipPayload,
    UploadURLs,
    ZipPayload,
)
from .types import (
    ALL_PDF_INFO_QUERIES,
    BmpColorModel,
    CompressionLevel,
    ExportDataFormat,
    ExtractTextGranularity,
    FlattenQuality,
    GifColorModel,
    GraphicSmoothing,
    HtmlPageOrientation,
    HtmlPageSize,
    HtmlWebLayout,
    JpegColorModel,
    OcrLanguage,
    PdfAddTextObject,
    PdfAOutputType,
    PdfConversionCompression,
    PdfConversionDownsample,
    PdfConversionLocale,
    PdfInfoQuery,
    PdfMergeInput,
    PdfPageOrientation,
    PdfPageSelection,
    PdfPageSize,
    PdfPresetColorProfile,
    PdfRedactionInstruction,
    PdfRestriction,
    PdfRGBColor,
    PdfSignatureConfiguration,
    PdfSignatureCredentials,
    PdfTextColor,
    PdfXType,
    PngColorModel,
    SummaryFormat,
    SummaryOutputFormat,
    TiffColorModel,
    TranslateOutputFormat,
    WatermarkHorizontalAlignment,
    WatermarkVerticalAlignment,
)

__all__ = (
    "AsyncPdfRestClient",
    "AsyncPdfRestFilesClient",
    "PdfRestClient",
    "PdfRestFilesClient",
)
FileResponseModel = TypeVar("FileResponseModel", bound=PdfRestFileBasedResponse)

DEFAULT_BASE_URL = "https://api.pdfrest.com"
API_KEY_ENV_VAR = "PDFREST_API_KEY"
API_KEY_HEADER_NAME = "Api-Key"
DEFAULT_GENERAL_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 120.0
FILE_UPLOAD_FIELD_NAME = "file"
DEFAULT_FILE_INFO_CONCURRENCY = 8
DEFAULT_MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 8.0
BACKOFF_JITTER_SECONDS = 0.1
RETRYABLE_STATUS_CODES = {408, 425, 429, 499}
_SUCCESSFUL_DELETION_MESSAGE = "successfully deleted"
_DEMO_RESTRICTION_MESSAGE_FIELDS = ("message", "warning", "keyMessage")
_DEMO_FALLBACK_FILE_ID = "00000000-0000-4000-8000-000000000000"
_DEMO_FALLBACK_FILE_URL = "https://pdfrest.com/demo-redacted"
_DEMO_FALLBACK_MIME_TYPE = "application/octet-stream"
_DEMO_FALLBACK_FILE_NAME = "demo-redacted.bin"
_DEMO_FALLBACK_FILE_SIZE = 1


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
QueryParamValue = str | int | float | bool | None
TimeoutTypes = float | httpx.Timeout | None
AnyMapping = Mapping[str, Any]
Query = Mapping[str, QueryParamValue]
Body = Mapping[str, Any]

PDFREST_LOGGER = logging.getLogger("pdfrest")
PDFREST_LOGGER.addHandler(logging.NullHandler())
LOGGER = logging.getLogger("pdfrest.client")
_PDFREST_HANDLER_IDS: set[int] = set()


def _ensure_stream_handler(
    logger: logging.Logger, formatter: logging.Formatter
) -> None:
    for handler in logger.handlers:
        if id(handler) in _PDFREST_HANDLER_IDS:
            return
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    _PDFREST_HANDLER_IDS.add(id(handler))


def _configure_logging() -> None:
    level_name = os.getenv("PDFREST_LOG")
    if not level_name:
        return
    normalized = level_name.strip().lower()
    level_map = {"debug": logging.DEBUG, "info": logging.INFO}
    level = level_map.get(normalized)
    if level is None:
        return
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    pdfrest_logger = PDFREST_LOGGER
    pdfrest_logger.setLevel(level)
    _ensure_stream_handler(pdfrest_logger, formatter)
    pdfrest_logger.propagate = False

    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(level)
    _ensure_stream_handler(httpx_logger, formatter)
    httpx_logger.propagate = False


_configure_logging()


def _parse_retry_after_header(header_value: str | None) -> float | None:
    if not header_value:
        return None
    trimmed = header_value.strip()
    if not trimmed:
        return None
    try:
        seconds = float(trimmed)
    except ValueError:
        try:
            retry_datetime = parsedate_to_datetime(trimmed)
        except (TypeError, ValueError):
            return None
        if retry_datetime.tzinfo is None:
            retry_datetime = retry_datetime.replace(tzinfo=timezone.utc)
        delay = (retry_datetime - datetime.now(timezone.utc)).total_seconds()
        return delay if delay > 0 else 0.0
    return seconds if seconds > 0 else 0.0


def _is_demo_restriction_message(value: str) -> bool:
    normalized = value.strip().casefold()
    if not normalized:
        return False
    return (
        "watermarked or redacted" in normalized
        and "free account" in normalized
        and "upgrade your plan" in normalized
    )


FileContent = IO[bytes] | bytes | str
FileTuple2 = tuple[str | None, FileContent]
FileTuple3 = tuple[str | None, FileContent, str | None]
FileTuple4 = tuple[str | None, FileContent, str | None, Mapping[str, str]]
FileTypes = FileContent | FileTuple2 | FileTuple3 | FileTuple4
UploadFiles = Sequence[FileTypes] | FileTypes

FilePath = str | PathLike[str]
FilePathTuple2 = tuple[FilePath, str | None]
FilePathTuple3 = tuple[FilePath, str | None, Mapping[str, str]]
FilePathTypes = FilePath | FilePathTuple2 | FilePathTuple3
FilePathInput = FilePathTypes | Sequence[FilePathTypes]
UrlValue = str | URL
UrlInput = UrlValue | Sequence[UrlValue]
NormalizedFileTypes: TypeAlias = FileContent | FileTuple2 | FileTuple3 | FileTuple4
DestinationPath = str | PathLike[str]


def _default_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        timeout=DEFAULT_GENERAL_TIMEOUT_SECONDS,
        read=DEFAULT_READ_TIMEOUT_SECONDS,
    )


def _extract_uploaded_file_ids(payload: Any) -> list[str]:
    try:
        files_payload = payload["files"]
    except (TypeError, KeyError) as exc:  # pragma: no cover - defensive
        raise PdfRestApiError(
            500, message="Upload response missing 'files' collection."
        ) from exc
    if not isinstance(files_payload, Sequence):  # pragma: no cover - defensive
        raise PdfRestApiError(500, message="Upload response 'files' is not a sequence.")
    entries = cast(Sequence[Mapping[str, Any]], files_payload)
    file_ids: list[str] = []
    for entry in entries:
        if "id" not in entry:
            raise PdfRestApiError(
                500, message="Upload response contains invalid file references."
            )
        file_ids.append(str(entry["id"]))
    return file_ids


def _is_demo_fallback_file_id(file_id: str) -> bool:
    return file_id.strip().lower() == _DEMO_FALLBACK_FILE_ID


def _build_demo_fallback_file(file_id: str) -> PdfRestFile:
    return PdfRestFile.model_validate(
        {
            "id": file_id,
            "name": _DEMO_FALLBACK_FILE_NAME,
            "url": _DEMO_FALLBACK_FILE_URL,
            "type": _DEMO_FALLBACK_MIME_TYPE,
            "size": _DEMO_FALLBACK_FILE_SIZE,
            "modified": datetime.now(timezone.utc),
        }
    )


def _handle_deletion_failures(response: PdfRestDeletionResponse) -> None:
    failures: list[PdfRestDeleteError] = []
    for file_id, result in response.deletion_responses.items():
        normalized_result = result.strip().lower()
        if normalized_result != _SUCCESSFUL_DELETION_MESSAGE:
            failures.append(PdfRestDeleteError(file_id, result))
    if failures:
        msg = "Failed to delete one or more files."
        raise PdfRestErrorGroup(
            msg,
            failures,
        )


def _normalize_headers(headers: Mapping[str, str]) -> Mapping[str, str]:
    return {str(key): str(value) for key, value in headers.items()}


def _ensure_file_content(value: FileContent) -> FileContent:
    if isinstance(value, (bytes, str)):
        return value
    if hasattr(value, "read"):
        return value
    msg = "File content must be a readable binary stream, bytes, or str."
    raise TypeError(msg)


def _normalize_file_type(file_value: FileTypes) -> NormalizedFileTypes:
    if isinstance(file_value, tuple):
        length = len(file_value)
        if length not in {2, 3, 4}:
            msg = "File tuple inputs must contain 2, 3, or 4 items."
            raise TypeError(msg)
        if length == 2:
            filename, content = cast(FileTuple2, file_value)
            normalized_filename = str(filename) if filename is not None else None
            normalized_content = _ensure_file_content(content)
            return (normalized_filename, normalized_content)
        if length == 3:
            filename, content, content_type = cast(FileTuple3, file_value)
            normalized_filename = str(filename) if filename is not None else None
            normalized_content = _ensure_file_content(content)
            normalized_content_type = (
                str(content_type) if content_type is not None else None
            )
            return (normalized_filename, normalized_content, normalized_content_type)

        filename, content, content_type, headers = cast(FileTuple4, file_value)
        normalized_filename = str(filename) if filename is not None else None
        normalized_content = _ensure_file_content(content)
        normalized_content_type = (
            str(content_type) if content_type is not None else None
        )
        normalized_headers = _normalize_headers(headers)
        return (
            normalized_filename,
            normalized_content,
            normalized_content_type,
            normalized_headers,
        )
    return _ensure_file_content(file_value)


def _normalize_upload_files(
    files: UploadFiles,
) -> list[tuple[str, NormalizedFileTypes]]:
    if isinstance(files, Mapping):
        msg = "Upload files must be provided as a sequence or a single file specification."
        raise TypeError(msg)

    if isinstance(files, Sequence) and not isinstance(files, (str, bytes, bytearray)):
        items = list(files)
    else:
        # Treat single file specification as a one-element sequence.
        items = [cast(FileTypes, files)]

    if not items:
        msg = "At least one file must be provided."
        raise ValueError(msg)
    normalized_items: list[tuple[str, NormalizedFileTypes]] = []
    for file_value in items:
        normalized_items.append(
            (FILE_UPLOAD_FIELD_NAME, _normalize_file_type(cast(FileTypes, file_value)))
        )
    return normalized_items


def _parse_path_spec(spec: FilePathTypes) -> tuple[Path, str | None, Mapping[str, str]]:
    if isinstance(spec, tuple):
        length = len(spec)
        if length == 2:
            raw_path, content_type = cast(FilePathTuple2, spec)
            headers: Mapping[str, str] = {}
        elif length == 3:
            raw_path, content_type, headers = cast(FilePathTuple3, spec)
        else:
            msg = "File path tuples must contain a path plus optional content type and headers."
            raise TypeError(msg)
        normalized_headers = _normalize_headers(headers)
        normalized_content_type = (
            str(content_type) if content_type is not None else None
        )
        path = Path(raw_path)
        return path, normalized_content_type, normalized_headers
    path = Path(spec)
    return path, None, {}


def _normalize_path_inputs(
    file_paths: FilePathInput,
) -> list[FilePathTypes]:
    if isinstance(file_paths, Sequence) and not isinstance(
        file_paths, (str, bytes, bytearray)
    ):
        sequence_paths = cast(Sequence[FilePathTypes], file_paths)
        items: list[FilePathTypes] = list(sequence_paths)
    else:
        items = [cast(FilePathTypes, file_paths)]
    if not items:
        msg = "At least one file path must be provided."
        raise ValueError(msg)
    return items


def _resolve_file_id(file_ref: PdfRestFile | str) -> str:
    return file_ref.id if isinstance(file_ref, PdfRestFile) else str(file_ref)


def _normalize_file_id(file_ref: PdfRestFileID | str) -> PdfRestFileID:
    if isinstance(file_ref, PdfRestFileID):
        return file_ref
    return PdfRestFileID(str(file_ref))


ClientType = TypeVar("ClientType", httpx.Client, httpx.AsyncClient)
ReturnType = TypeVar("ReturnType")


class _ClientConfig(BaseModel):
    """Internal representation of client configuration validated by Pydantic."""

    base_url: URL
    api_key: str | None = None
    timeout: TimeoutTypes = Field(default_factory=_default_timeout)
    headers: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("base_url", mode="before")
    @classmethod
    def _parse_base_url(cls, value: Any) -> URL:
        url_value = value or DEFAULT_BASE_URL
        url = URL(str(url_value))
        if url.scheme not in {"http", "https"}:
            msg = "base_url must use http or https scheme."
            raise PdfRestConfigurationError(msg)
        return (
            url
            if not url.path or url.path == "/"
            else url.copy_with(path=url.path.rstrip("/"))
        )

    @field_validator("api_key")
    @classmethod
    def _validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        return trimmed

    @field_validator("headers", mode="before")
    @classmethod
    def _validate_headers(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        converted: dict[str, str] = {}
        for key, item in dict(value).items():
            converted[str(key)] = str(item)
        return converted

    @field_validator("timeout", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> TimeoutTypes:
        if value is None:
            return _default_timeout()
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, httpx.Timeout):
            return value
        msg = "timeout must be a float (seconds) or httpx.Timeout instance."
        raise PdfRestConfigurationError(msg)


class _RequestModel(BaseModel):
    """Internal request data validated prior to dispatch."""

    method: HttpMethod
    endpoint: str
    params: dict[str, QueryParamValue] | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: TimeoutTypes
    json_body: dict[str, Any] | None = None
    files: Any | None = None
    data: Any | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _has_stream_uploads: bool = PrivateAttr(default=False)

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        if not value.startswith("/"):
            msg = "endpoint must start with '/'."
            raise PdfRestConfigurationError(msg)
        return value

    def mark_has_stream_uploads(self) -> None:
        self._has_stream_uploads = True

    def has_stream_uploads(self) -> bool:
        return self._has_stream_uploads


class _BaseApiClient(Generic[ClientType]):
    """Shared logic between sync and async client variants."""

    _config: _ClientConfig

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | URL | None = None,
        timeout: TimeoutTypes | None = None,
        headers: AnyMapping | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._logger = LOGGER
        if max_retries < 0:
            msg = "max_retries must be a non-negative integer."
            raise PdfRestConfigurationError(msg)
        self._max_retries = max_retries
        raw_api_key = api_key if api_key is not None else os.getenv(API_KEY_ENV_VAR)
        resolved_api_key = (
            raw_api_key.strip() if raw_api_key and raw_api_key.strip() else None
        )

        resolved_base_url = (
            URL(str(base_url)) if base_url is not None else URL(DEFAULT_BASE_URL)
        )

        if resolved_api_key is None and self._base_url_requires_api_key(
            resolved_base_url
        ):
            msg = (
                "API key is required when communicating with pdfRest-hosted "
                "endpoints. Provide `api_key` or set the PDFREST_API_KEY environment variable."
            )
            raise PdfRestConfigurationError(msg)

        if resolved_api_key is not None:
            self._validate_pdfrest_api_key(resolved_api_key, resolved_base_url)

        version = importlib.metadata.version("pdfrest")
        default_headers: dict[str, str] = {
            "Accept": "application/json",
            "wsn": "pdfrest-python",
            "User-Agent": f"pdfrest-python-sdk/{version}",
        }
        if resolved_api_key is not None:
            default_headers[API_KEY_HEADER_NAME] = resolved_api_key
        if headers:
            for key, value in headers.items():
                default_headers[str(key)] = str(value)

        try:
            self._config = _ClientConfig(
                base_url=resolved_base_url,
                api_key=resolved_api_key,
                timeout=timeout if timeout is not None else _default_timeout(),
                headers=default_headers,
            )
        except PdfRestConfigurationError:
            raise
        except ValidationError as exc:  # pragma: no cover - defensive
            raise PdfRestConfigurationError(str(exc)) from exc

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        if status_code in RETRYABLE_STATUS_CODES:
            return True
        return 500 <= status_code < 600

    def _should_retry_exception(self, exc: PdfRestError) -> bool:
        allow_retry = getattr(exc, "allow_retry", True)
        if not allow_retry:
            return False
        if isinstance(exc, PdfRestApiError):
            return self._is_retryable_status(exc.status_code)
        return isinstance(
            exc, (PdfRestTimeoutError, PdfRestTransportError, PdfRestRequestError)
        )

    def _compute_backoff_delay(self, retry_number: int) -> float:
        base_delay = min(
            INITIAL_BACKOFF_SECONDS * (2**retry_number),
            MAX_BACKOFF_SECONDS,
        )
        # ignoring S311 because this isn't being used for cryptography
        jitter = random.uniform(-BACKOFF_JITTER_SECONDS, BACKOFF_JITTER_SECONDS)  # noqa: S311
        delay = base_delay + jitter
        return delay if delay > 0 else 0.0

    def _determine_retry_delay(self, attempt: int, exc: PdfRestError) -> float:
        delay = self._compute_backoff_delay(attempt)
        retry_after_value = getattr(exc, "retry_after", None)
        if isinstance(retry_after_value, (int, float)):
            delay = max(delay, float(retry_after_value))
        return delay

    @staticmethod
    def _sanitize_headers(headers: Mapping[str, Any] | None) -> dict[str, Any]:
        if not headers:
            return {}
        sanitized: dict[str, Any] = {}
        for key, value in headers.items():
            if key.lower() == API_KEY_HEADER_NAME.lower():
                sanitized[key] = "******"
            else:
                sanitized[key] = value
        return sanitized

    def _log_request(self, request: _RequestModel) -> None:
        if not self._logger.isEnabledFor(logging.DEBUG):
            return
        sanitized_headers = self._sanitize_headers(request.headers)
        self._logger.debug(
            "Request %s %s params=%s timeout=%s headers=%s",
            request.method,
            request.endpoint,
            request.params,
            request.timeout,
            sanitized_headers,
        )
        if request.method in {"POST", "PUT", "PATCH"} and request.json_body is not None:
            self._logger.debug(
                "Request payload %s %s: %s",
                request.method,
                request.endpoint,
                request.json_body,
            )

    @staticmethod
    def _describe_request(request: _RequestModel) -> str:
        return f"{request.method} {request.endpoint}"

    @staticmethod
    def _base_url_requires_api_key(url: URL) -> bool:
        host = url.host or ""
        return host.lower().endswith("pdfrest.com")

    @staticmethod
    def _validate_pdfrest_api_key(api_key: str, url: URL) -> None:
        if not _BaseApiClient._base_url_requires_api_key(url):
            return
        if len(api_key) != 36:
            msg = "pdfRest API keys must be 36 characters (UUID format)."
            raise PdfRestConfigurationError(msg)
        try:
            _ = uuid.UUID(api_key)
        except ValueError:
            msg = "pdfRest API keys must be valid UUID strings."
            raise PdfRestConfigurationError(msg) from None

    @property
    def base_url(self) -> URL:
        """Resolved base URL for the client."""
        return self._config.base_url

    def _prepare_request(
        self,
        method: HttpMethod,
        endpoint: str,
        *,
        query: Query | None = None,
        json_body: Body | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
        files: Any | None = None,
        data: Any | None = None,
    ) -> _RequestModel:
        headers = self._compose_headers(extra_headers)
        params = self._compose_query_params(query, extra_query)
        json_payload = self._compose_json_body(json_body, extra_body)
        if files is not None and json_payload is not None:
            msg = "JSON payloads cannot be combined with multipart file uploads."
            raise PdfRestConfigurationError(msg)
        timeout_value = timeout if timeout is not None else self._config.timeout

        files_payload: Any | None = files
        if isinstance(files_payload, Iterator):
            files_payload = list(files_payload)

        try:
            request = _RequestModel(
                method=method,
                endpoint=endpoint,
                params=params,
                headers=headers,
                timeout=timeout_value,
                json_body=json_payload,
                files=files_payload,
                data=data,
            )
        except PdfRestConfigurationError:
            raise
        except ValidationError as exc:  # pragma: no cover - defensive
            raise PdfRestConfigurationError(str(exc)) from exc
        if self._contains_open_stream(files_payload):
            request.mark_has_stream_uploads()
        return request

    def prepare_request(
        self,
        method: HttpMethod,
        endpoint: str,
        *,
        query: Query | None = None,
        json_body: Body | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
        files: Any | None = None,
        data: Any | None = None,
    ) -> _RequestModel:
        return self._prepare_request(
            method,
            endpoint,
            query=query,
            json_body=json_body,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
            files=files,
            data=data,
        )

    def _compose_headers(self, extra_headers: AnyMapping | None) -> dict[str, str]:
        combined_headers: dict[str, str] = dict(self._config.headers)
        if extra_headers is None:
            return combined_headers
        for key, value in extra_headers.items():
            combined_headers[str(key)] = str(value)
        return combined_headers

    @staticmethod
    def _compose_query_params(
        query: Query | None,
        extra_query: Query | None,
    ) -> dict[str, QueryParamValue] | None:
        params: dict[str, QueryParamValue] = {}
        for mapping in (query, extra_query):
            if mapping is None:
                continue
            for key, value in mapping.items():
                params[str(key)] = value
        return params or None

    @staticmethod
    def _compose_json_body(
        json_body: Body | None,
        extra_body: Body | None,
    ) -> dict[str, Any] | None:
        if json_body is None:
            if extra_body is not None:
                msg = "extra_body can only be used with JSON requests."
                raise PdfRestConfigurationError(msg)
            return None
        payload: dict[str, Any] = dict(json_body)
        if extra_body is not None:
            for key, value in extra_body.items():
                payload[str(key)] = value
        return payload

    @staticmethod
    def _contains_open_stream(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (bytes, bytearray, str)):
            return False
        if hasattr(value, "read"):
            return True
        if isinstance(value, Mapping):
            return any(
                _BaseApiClient._contains_open_stream(item) for item in value.values()
            )
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            return any(_BaseApiClient._contains_open_stream(item) for item in value)
        return False

    def _build_stream_retry_checker(
        self, request: _RequestModel
    ) -> Callable[[PdfRestError], bool] | None:
        if not request.has_stream_uploads():
            return None

        def checker(exc: PdfRestError) -> bool:
            return bool(
                isinstance(exc, (PdfRestConnectTimeoutError, PdfRestPoolTimeoutError))
            )

        return checker

    def _handle_response(self, response: httpx.Response) -> Any:
        request = response.request
        request_label = (
            f"{getattr(request, 'method', 'UNKNOWN')} {getattr(request, 'url', '')}"
        )
        if response.is_success:
            payload = self._decode_json(response)
            self._log_demo_restriction_messages(payload, request_label)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "Response %s status=%s", request_label, response.status_code
                )
            return payload

        message, error_payload = self._extract_error_details(response)
        retry_after = _parse_retry_after_header(response.headers.get("Retry-After"))

        if response.status_code == 401:
            auth_message = message or "Authentication with pdfRest failed."
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "Authentication error response %s status=%s message=%s payload=%s",
                    request_label,
                    response.status_code,
                    auth_message,
                    error_payload,
                )
            raise PdfRestAuthenticationError(
                response.status_code,
                message=auth_message,
                response_content=error_payload,
                retry_after=retry_after,
            )

        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "Error response %s status=%s message=%s payload=%s",
                request_label,
                response.status_code,
                message,
                error_payload,
            )

        raise PdfRestApiError(
            response.status_code,
            message=message,
            response_content=error_payload,
            retry_after=retry_after,
        )

    def _decode_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise PdfRestApiError(
                response.status_code,
                message="Response body is not valid JSON.",
                response_content=response.text,
            ) from exc

    def _log_demo_restriction_messages(self, payload: Any, request_label: str) -> None:
        if not isinstance(payload, Mapping):
            return

        typed_payload = cast(Mapping[str, Any], payload)
        emitted_messages: set[str] = set()
        for field_name in _DEMO_RESTRICTION_MESSAGE_FIELDS:
            value = typed_payload.get(field_name)
            if not isinstance(value, str):
                continue
            message = value.strip()
            if not _is_demo_restriction_message(message):
                continue
            normalized_message = message.casefold()
            if normalized_message in emitted_messages:
                continue
            emitted_messages.add(normalized_message)
            self._logger.warning(
                "Demo mode restriction message in response %s field=%s: %s",
                request_label,
                field_name,
                message,
            )

    @staticmethod
    def _extract_error_details(
        response: httpx.Response,
    ) -> tuple[str | None, Any | None]:
        try:
            pdfrest_error = PdfRestErrorResponse.model_validate_json(response.content)
        except ValidationError:
            return None, response.text
        return pdfrest_error.error, None


class _SyncApiClient(_BaseApiClient[httpx.Client]):
    """Internal synchronous client implementation."""

    _client: httpx.Client
    _owns_http_client: bool

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | URL | None = None,
        timeout: TimeoutTypes | None = None,
        headers: AnyMapping | None = None,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            headers=headers,
            max_retries=max_retries,
        )
        self._owns_http_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self.base_url,
            headers=dict(self._config.headers),
            timeout=self._config.timeout,
            transport=transport,
        )

    def close(self) -> None:
        if self._owns_http_client:
            self._client.close()

    def __enter__(self) -> _SyncApiClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _execute_with_retry(
        self,
        func: Callable[[], ReturnType],
        *,
        operation: str,
        should_continue: Callable[[PdfRestError], bool] | None = None,
    ) -> ReturnType:
        total_attempts = self._max_retries + 1
        for attempt in range(total_attempts):
            try:
                return func()
            except PdfRestError as exc:
                self._logger.debug(
                    "Exception during %s attempt %d/%d: %s",
                    operation,
                    attempt + 1,
                    total_attempts,
                    exc,
                )
                additional_retry_allowed = (
                    should_continue(exc) if should_continue is not None else True
                )
                should_retry = (
                    attempt < self._max_retries
                    and self._should_retry_exception(exc)
                    and additional_retry_allowed
                )
                if not should_retry:
                    self._logger.debug("No retry for %s; raising exception.", operation)
                    raise
                delay = self._determine_retry_delay(attempt, exc)
                self._logger.debug("Retrying %s after %.2f seconds.", operation, delay)
                if delay > 0:
                    time.sleep(delay)
        msg = "Retry loop exited unexpectedly."
        raise RuntimeError(msg)  # pragma: no cover

    def _send_request(self, request: _RequestModel) -> Any:
        http_client = self._client

        stream_retry_checker = self._build_stream_retry_checker(request)

        return self._execute_with_retry(
            lambda: self._perform_request(http_client, request),
            operation=self._describe_request(request),
            should_continue=stream_retry_checker,
        )

    def send_request_once(self, request: _RequestModel) -> Any:
        return self._perform_request(self._client, request)

    def run_with_retry(
        self,
        func: Callable[[], ReturnType],
        *,
        operation: str,
        should_continue: Callable[[PdfRestError], bool] | None = None,
    ) -> ReturnType:
        return self._execute_with_retry(
            func,
            operation=operation,
            should_continue=should_continue,
        )

    def _perform_request(
        self, http_client: httpx.Client, request: _RequestModel
    ) -> Any:
        self._log_request(request)
        try:
            response = http_client.request(
                method=request.method,
                url=request.endpoint,
                params=request.params or None,
                headers=request.headers or None,
                timeout=request.timeout,
                json=request.json_body,
                files=request.files,
                data=request.data,
            )
        except httpx.HTTPError as exc:
            translated = translate_httpx_error(exc)
            self._logger.debug(
                "HTTPX exception for %s: %s",
                self._describe_request(request),
                translated,
            )
            raise translated from exc
        try:
            payload = self._handle_response(response)
        except PdfRestApiError:
            response.close()
            raise
        response.close()
        return payload

    def _post_file_operation(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        payload_model: type[BaseModel],
        response_model: type[FileResponseModel] = PdfRestFileBasedResponse,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> FileResponseModel:
        job_options = payload_model.model_validate(payload)
        json_body = job_options.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude_unset=True
        )
        request = self.prepare_request(
            "POST",
            endpoint,
            json_body=json_body,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = self._send_request(request)
        raw_response = PdfRestRawFileResponse.model_validate(raw_payload)

        output_ids = raw_response.ids or []
        output_files = [
            self.fetch_file_info(
                str(file_id),
                extra_query=extra_query,
                extra_headers=extra_headers,
                timeout=timeout,
            )
            for file_id in output_ids
        ]

        response_payload: dict[str, Any] = {
            "input_id": [str(file_id) for file_id in raw_response.input_id],
            "output_file": [
                file.model_dump(mode="json", by_alias=True) for file in output_files
            ],
            "warning": raw_response.warning,
        }
        if raw_response.model_extra:
            response_payload.update(raw_response.model_extra)

        return response_model.model_validate(response_payload)

    def send_request(self, request: _RequestModel) -> Any:
        return self._send_request(request)

    def download_file(
        self,
        file_id: str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> httpx.Response:
        request_model = self.prepare_request(
            "GET",
            f"/resource/{file_id}",
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return self._execute_with_retry(
            lambda: self._download_with_retry(request_model),
            operation=f"{request_model.method} {request_model.endpoint} (download)",
        )

    def _download_with_retry(self, request: _RequestModel) -> httpx.Response:
        self._log_request(request)
        http_request = self._client.build_request(
            request.method,
            request.endpoint,
            params=request.params or None,
            headers=request.headers or None,
        )
        if request.timeout is not None:
            timeout_value = (
                request.timeout
                if isinstance(request.timeout, httpx.Timeout)
                else httpx.Timeout(request.timeout)
            )
            http_request.extensions["timeout"] = timeout_value.as_dict()
        try:
            response = self._client.send(http_request, stream=True)
        except httpx.HTTPError as exc:
            translated = translate_httpx_error(exc)
            self._logger.debug(
                "HTTPX exception for %s: %s",
                self._describe_request(request),
                translated,
            )
            raise translated from exc
        if response.is_success:
            return response
        try:
            self._handle_response(response)
        finally:
            response.close()
        msg = "Unreachable"
        raise RuntimeError(msg)  # pragma: no cover

    def fetch_file_info(
        self,
        file_id: str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFile:
        request = self.prepare_request(
            "GET",
            f"/resource/{file_id}",
            query={"format": "info"},
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            payload = self._send_request(request)
        except PdfRestApiError as exc:
            if exc.status_code == 404 and _is_demo_fallback_file_id(file_id):
                self._logger.warning(
                    "Demo fallback file id %s was not found during file-info lookup; "
                    "returning placeholder metadata.",
                    file_id,
                )
                return _build_demo_fallback_file(file_id)
            raise
        return PdfRestFile.model_validate(payload)


class _AsyncApiClient(_BaseApiClient[httpx.AsyncClient]):
    """Internal asynchronous client implementation."""

    _client: httpx.AsyncClient
    _owns_http_client: bool

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | URL | None = None,
        timeout: TimeoutTypes | None = None,
        headers: AnyMapping | None = None,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency_limit: int = DEFAULT_FILE_INFO_CONCURRENCY,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            headers=headers,
            max_retries=max_retries,
        )
        self._owns_http_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self.base_url,
            headers=dict(self._config.headers),
            timeout=self._config.timeout,
            transport=transport,
        )
        self._concurrency_limit = concurrency_limit

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._client.aclose()

    async def __aenter__(self) -> _AsyncApiClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()

    async def _execute_with_retry(
        self,
        func: Callable[[], Awaitable[ReturnType]],
        *,
        operation: str,
        should_continue: Callable[[PdfRestError], bool] | None = None,
    ) -> ReturnType:
        total_attempts = self._max_retries + 1
        for attempt in range(total_attempts):
            try:
                return await func()
            except PdfRestError as exc:
                self._logger.debug(
                    "Exception during %s attempt %d/%d: %s",
                    operation,
                    attempt + 1,
                    total_attempts,
                    exc,
                )
                additional_retry_allowed = (
                    should_continue(exc) if should_continue is not None else True
                )
                should_retry = (
                    attempt < self._max_retries
                    and self._should_retry_exception(exc)
                    and additional_retry_allowed
                )
                if not should_retry:
                    self._logger.debug("No retry for %s; raising exception.", operation)
                    raise
                delay = self._determine_retry_delay(attempt, exc)
                self._logger.debug("Retrying %s after %.2f seconds.", operation, delay)
                if delay > 0:
                    await asyncio.sleep(delay)
        msg = "Retry loop exited unexpectedly."
        raise RuntimeError(msg)  # pragma: no cover

    async def _send_request(self, request: _RequestModel) -> Any:
        http_client = self._client

        stream_retry_checker = self._build_stream_retry_checker(request)

        return await self._execute_with_retry(
            lambda: self._perform_request(http_client, request),
            operation=self._describe_request(request),
            should_continue=stream_retry_checker,
        )

    async def send_request_once(self, request: _RequestModel) -> Any:
        return await self._perform_request(self._client, request)

    async def run_with_retry(
        self,
        func: Callable[[], Awaitable[ReturnType]],
        *,
        operation: str,
        should_continue: Callable[[PdfRestError], bool] | None = None,
    ) -> ReturnType:
        return await self._execute_with_retry(
            func,
            operation=operation,
            should_continue=should_continue,
        )

    async def _perform_request(
        self, http_client: httpx.AsyncClient, request: _RequestModel
    ) -> Any:
        self._log_request(request)
        try:
            response = await http_client.request(
                method=request.method,
                url=request.endpoint,
                params=request.params or None,
                headers=request.headers or None,
                timeout=request.timeout,
                json=request.json_body,
                files=request.files,
                data=request.data,
            )
        except httpx.HTTPError as exc:
            translated = translate_httpx_error(exc)
            self._logger.debug(
                "HTTPX exception for %s: %s",
                self._describe_request(request),
                translated,
            )
            raise translated from exc
        try:
            payload = self._handle_response(response)
        except PdfRestApiError:
            await response.aclose()
            raise
        await response.aclose()
        return payload

    async def _post_file_operation(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        payload_model: type[BaseModel],
        response_model: type[FileResponseModel] = PdfRestFileBasedResponse,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> FileResponseModel:
        job_options = payload_model.model_validate(payload)
        request = self.prepare_request(
            "POST",
            endpoint,
            json_body=job_options.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = await self._send_request(request)
        raw_response = PdfRestRawFileResponse.model_validate(raw_payload)

        output_ids = raw_response.ids or []
        output_files: list[PdfRestFile] = []
        semaphore = asyncio.Semaphore(self._concurrency_limit)

        async def throttled_fetch_file_info(file_id: str) -> PdfRestFile:
            async with semaphore:
                return await self.fetch_file_info(
                    str(file_id),
                    extra_query=extra_query,
                    extra_headers=extra_headers,
                    timeout=timeout,
                )

        if output_ids:
            output_files = list(
                await asyncio.gather(
                    *(throttled_fetch_file_info(str(file_id)) for file_id in output_ids)
                )
            )

        response_payload: dict[str, Any] = {
            "input_id": [str(file_id) for file_id in raw_response.input_id],
            "output_file": [
                file.model_dump(mode="json", by_alias=True) for file in output_files
            ],
            "warning": raw_response.warning,
        }
        if raw_response.model_extra:
            response_payload.update(raw_response.model_extra)

        return response_model.model_validate(response_payload)

    async def send_request(self, request: _RequestModel) -> Any:
        return await self._send_request(request)

    async def download_file(
        self,
        file_id: str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> httpx.Response:
        request_model = self.prepare_request(
            "GET",
            f"/resource/{file_id}",
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return await self._execute_with_retry(
            lambda: self._download_with_retry(request_model),
            operation=f"{request_model.method} {request_model.endpoint} (download)",
        )

    async def _download_with_retry(self, request: _RequestModel) -> httpx.Response:
        self._log_request(request)
        http_request = self._client.build_request(
            request.method,
            request.endpoint,
            params=request.params or None,
            headers=request.headers or None,
        )
        if request.timeout is not None:
            timeout_value = (
                request.timeout
                if isinstance(request.timeout, httpx.Timeout)
                else httpx.Timeout(request.timeout)
            )
            http_request.extensions["timeout"] = timeout_value.as_dict()
        try:
            response = await self._client.send(http_request, stream=True)
        except httpx.HTTPError as exc:
            translated = translate_httpx_error(exc)
            self._logger.debug(
                "HTTPX exception for %s: %s",
                self._describe_request(request),
                translated,
            )
            raise translated from exc
        if response.is_success:
            return response
        try:
            self._handle_response(response)
        finally:
            await response.aclose()
        msg = "Unreachable"
        raise RuntimeError(msg)  # pragma: no cover

    async def fetch_file_info(
        self,
        file_id: str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFile:
        request = self.prepare_request(
            "GET",
            f"/resource/{file_id}",
            query={"format": "info"},
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            payload = await self._send_request(request)
        except PdfRestApiError as exc:
            if exc.status_code == 404 and _is_demo_fallback_file_id(file_id):
                self._logger.warning(
                    "Demo fallback file id %s was not found during file-info lookup; "
                    "returning placeholder metadata.",
                    file_id,
                )
                return _build_demo_fallback_file(file_id)
            raise
        return PdfRestFile.model_validate(payload)


class PdfRestFileStream:
    """Streaming wrapper for synchronously downloading files from pdfRest."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]:
        yield from self._response.iter_bytes(chunk_size)

    def iter_text(self, chunk_size: int | None = None) -> Iterator[str]:
        yield from self._response.iter_text(chunk_size)

    def iter_lines(self) -> Iterator[str]:
        yield from self._response.iter_lines()

    def iter_raw(self, chunk_size: int | None = None) -> Iterator[bytes]:
        yield from self._response.iter_raw(chunk_size)

    def close(self) -> None:
        self._response.close()

    def __enter__(self) -> PdfRestFileStream:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


class AsyncPdfRestFileStream:
    """Streaming wrapper for asynchronously downloading files from pdfRest."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def iter_bytes(self, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_bytes(chunk_size):
            yield chunk

    async def iter_text(self, chunk_size: int | None = None) -> AsyncIterator[str]:
        async for chunk in self._response.aiter_text(chunk_size):
            yield chunk

    async def iter_lines(self) -> AsyncIterator[str]:
        async for line in self._response.aiter_lines():
            yield line

    async def iter_raw(self, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_raw(chunk_size):
            yield chunk

    async def close(self) -> None:
        await self._response.aclose()

    async def __aenter__(self) -> AsyncPdfRestFileStream:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.close()


class PdfRestFilesClient(Protocol):
    """Public interface for file operations returned by files helpers.

    This protocol describes the object returned by
    [`PdfRestClient.files`][pdfrest.PdfRestClient.files].
    Retrieve this helper from `client.files`; do not instantiate it directly.
    """

    def get(
        self,
        id: PdfRestFileID | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFile:
        """Retrieve metadata for an uploaded file.

        Args:
            id: Uploaded file identifier.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The resolved file metadata.
        """
        ...

    def create(
        self,
        files: UploadFiles,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more local file objects.

        Args:
            files: Multipart file payload(s) accepted by httpx upload APIs.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Metadata for uploaded files.
        """
        ...

    def create_from_paths(
        self,
        file_paths: FilePathInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by filesystem path.

        Args:
            file_paths: Path input(s), optionally with content type and headers.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Metadata for uploaded files.
        """
        ...

    def create_from_urls(
        self,
        urls: UrlInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by remote URL.

        Args:
            urls: One URL or a sequence of URLs to upload.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            extra_body: Additional JSON body fields merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Metadata for uploaded files.
        """
        ...

    def delete(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> None:
        """Delete one or more previously uploaded files.

        Args:
            files: File reference(s) to delete.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            extra_body: Additional JSON body fields merged into the request.
            timeout: Optional request timeout override.

        Raises:
            PdfRestErrorGroup: Raised when one or more deletions fail. Individual
                failures are reported as `PdfRestDeleteError` items in the group.
        """
        ...

    def read_bytes(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> bytes:
        """Download a file and return its raw bytes.

        Args:
            file_ref: File object or file id to download.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The downloaded bytes.
        """
        ...

    def read_text(
        self,
        file_ref: PdfRestFile | str,
        *,
        encoding: str = "utf-8",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> str:
        """Download a file and decode it into text.

        Args:
            file_ref: File object or file id to download.
            encoding: Text encoding used when decoding the response.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The decoded text content.
        """
        ...

    def read_json(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Any:
        """Download a file and parse its content as JSON.

        Args:
            file_ref: File object or file id to download.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Parsed JSON value.
        """
        ...

    def write_bytes(
        self,
        file_ref: PdfRestFile | str,
        destination: DestinationPath,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Path:
        """Download a file and persist it to disk.

        Args:
            file_ref: File object or file id to download.
            destination: Output path for the downloaded file.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The written destination path.
        """
        ...

    def stream(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileStream:
        """Open a streaming download for a file.

        Args:
            file_ref: File object or file id to download.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            A synchronous streaming wrapper around the HTTP response.
        """
        ...


class AsyncPdfRestFilesClient(Protocol):
    """Public interface for async file operations returned by files helpers.

    This protocol describes the object returned by
    [`AsyncPdfRestClient.files`][pdfrest.AsyncPdfRestClient.files].
    Retrieve this helper from `client.files`; do not instantiate it directly.
    """

    async def get(
        self,
        id: PdfRestFileID | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFile:
        """Retrieve metadata for an uploaded file.

        Args:
            id: Uploaded file identifier.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The resolved file metadata.
        """
        ...

    async def create(
        self,
        files: UploadFiles,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more local file objects.

        Args:
            files: Multipart file payload(s) accepted by httpx upload APIs.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Metadata for uploaded files.
        """
        ...

    async def create_from_paths(
        self,
        file_paths: FilePathInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by filesystem path.

        Args:
            file_paths: Path input(s), optionally with content type and headers.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Metadata for uploaded files.
        """
        ...

    async def create_from_urls(
        self,
        urls: UrlInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by remote URL.

        Args:
            urls: One URL or a sequence of URLs to upload.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            extra_body: Additional JSON body fields merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Metadata for uploaded files.
        """
        ...

    async def delete(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> None:
        """Delete one or more previously uploaded files.

        Args:
            files: File reference(s) to delete.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            extra_body: Additional JSON body fields merged into the request.
            timeout: Optional request timeout override.

        Raises:
            PdfRestErrorGroup: Raised when one or more deletions fail. Individual
                failures are reported as `PdfRestDeleteError` items in the group.
        """
        ...

    async def read_bytes(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> bytes:
        """Download a file and return its raw bytes.

        Args:
            file_ref: File object or file id to download.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The downloaded bytes.
        """
        ...

    async def read_text(
        self,
        file_ref: PdfRestFile | str,
        *,
        encoding: str = "utf-8",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> str:
        """Download a file and decode it into text.

        Args:
            file_ref: File object or file id to download.
            encoding: Text encoding used when decoding the response.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The decoded text content.
        """
        ...

    async def read_json(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Any:
        """Download a file and parse its content as JSON.

        Args:
            file_ref: File object or file id to download.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            Parsed JSON value.
        """
        ...

    async def write_bytes(
        self,
        file_ref: PdfRestFile | str,
        destination: DestinationPath,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Path:
        """Download a file and persist it to disk.

        Args:
            file_ref: File object or file id to download.
            destination: Output path for the downloaded file.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            The written destination path.
        """
        ...

    async def stream(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> AsyncPdfRestFileStream:
        """Open a streaming download for a file.

        Args:
            file_ref: File object or file id to download.
            extra_query: Additional query parameters appended to the request.
            extra_headers: Additional headers merged into the request.
            timeout: Optional request timeout override.

        Returns:
            An asynchronous streaming wrapper around the HTTP response.
        """
        ...


class _FilesClient:
    """Expose file-related operations for the synchronous client."""

    def __init__(self, client: _SyncApiClient) -> None:
        self._client = client

    def get(
        self,
        id: PdfRestFileID | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFile:
        """Retrieve file metadata given a file identifier."""
        file_id = _normalize_file_id(id)
        return self._client.fetch_file_info(
            str(file_id),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )

    def create(
        self,
        files: UploadFiles,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by content.

        Provide either a single file specification or a sequence of file
        specifications (each matching the shapes accepted by httpx). Every
        uploaded part is sent using the field name ``file``.
        """
        normalized_files = _normalize_upload_files(files)
        request = self._client.prepare_request(
            "POST",
            "/upload",
            files=normalized_files,
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        payload = self._client.send_request(request)
        file_ids = _extract_uploaded_file_ids(payload)
        return [
            self._client.fetch_file_info(
                file_id,
                extra_query=extra_query,
                extra_headers=extra_headers,
                timeout=timeout,
            )
            for file_id in file_ids
        ]

    def create_from_paths(
        self,
        file_paths: FilePathInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by their path.

        Each entry may be a bare path-like object or a tuple of
        `(path, content_type)` / `(path, content_type, headers)` where headers
        mirrors the httpx multipart header mapping. All opened file handles are
        closed once the request completes.
        """
        normalized_paths = _normalize_path_inputs(file_paths)
        path_specs = [_parse_path_spec(spec) for spec in normalized_paths]

        def attempt() -> list[PdfRestFile]:
            with ExitStack() as stack:
                upload_specs: list[tuple[str, FileTypes]] = []
                for path, content_type, headers in path_specs:
                    file_obj = stack.enter_context(path.open("rb"))
                    filename = path.name
                    normalized_spec: FileTypes
                    if headers:
                        normalized_spec = (filename, file_obj, content_type, headers)
                    elif content_type is not None:
                        normalized_spec = (filename, file_obj, content_type)
                    else:
                        normalized_spec = (filename, file_obj)
                    upload_specs.append((FILE_UPLOAD_FIELD_NAME, normalized_spec))

                request = self._client.prepare_request(
                    "POST",
                    "/upload",
                    files=upload_specs,
                    extra_query=extra_query,
                    extra_headers=extra_headers,
                    timeout=timeout,
                )
                payload = self._client.send_request_once(request)
                file_ids = _extract_uploaded_file_ids(payload)
                return [
                    self._client.fetch_file_info(
                        file_id,
                        extra_query=extra_query,
                        extra_headers=extra_headers,
                        timeout=timeout,
                    )
                    for file_id in file_ids
                ]

        return self._client.run_with_retry(attempt, operation="POST /upload (paths)")

    def create_from_urls(
        self,
        urls: UrlInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by providing remote URLs."""
        normalized_urls = UploadURLs.model_validate({"url": urls})
        request = self._client.prepare_request(
            "POST",
            "/upload",
            json_body=normalized_urls.model_dump(mode="json"),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        payload = self._client.send_request(request)
        file_ids = _extract_uploaded_file_ids(payload)
        return [
            self._client.fetch_file_info(
                file_id,
                extra_query=extra_query,
                extra_headers=extra_headers,
                timeout=timeout,
            )
            for file_id in file_ids
        ]

    def delete(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> None:
        """Delete one or more uploaded files by reference."""
        payload = DeletePayload.model_validate({"files": files})
        request = self._client.prepare_request(
            "POST",
            "/delete",
            json_body=payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = self._client.send_request(request)
        deletion_response = PdfRestDeletionResponse.model_validate(raw_payload)
        _handle_deletion_failures(deletion_response)
        return

    def read_bytes(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> bytes:
        response = self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            return response.read()
        finally:
            response.close()

    def read_text(
        self,
        file_ref: PdfRestFile | str,
        *,
        encoding: str = "utf-8",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> str:
        response = self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            response.encoding = encoding
            data = response.read()
            codec = response.encoding or encoding or "utf-8"
            return data.decode(codec)
        finally:
            response.close()

    def read_json(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Any:
        response = self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            data = response.read()
            codec = response.encoding or "utf-8"
            return json.loads(data.decode(codec))
        finally:
            response.close()

    def write_bytes(
        self,
        file_ref: PdfRestFile | str,
        destination: DestinationPath,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Path:
        response = self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        path = Path(destination)
        try:
            with path.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    _ = file_handle.write(chunk)
        finally:
            response.close()
        return path

    def stream(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileStream:
        response = self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return PdfRestFileStream(response)


class _AsyncFilesClient:
    """Expose file-related operations for the asynchronous client."""

    def __init__(
        self,
        client: _AsyncApiClient,
        *,
        concurrency_limit: int = DEFAULT_FILE_INFO_CONCURRENCY,
    ) -> None:
        self._client = client
        self._concurrency_limit = concurrency_limit

    async def get(
        self,
        id: PdfRestFileID | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFile:
        """Retrieve file metadata given a file identifier."""
        file_id = _normalize_file_id(id)
        return await self._client.fetch_file_info(
            str(file_id),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )

    async def create(
        self,
        files: UploadFiles,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by content.

        Provide either a single file specification or a sequence of file
        specifications (each matching the shapes accepted by httpx). Every
        uploaded part is sent using the field name ``file``.
        """
        normalized_files = _normalize_upload_files(files)
        request = self._client.prepare_request(
            "POST",
            "/upload",
            files=normalized_files,
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        payload = await self._client.send_request(request)
        file_ids = _extract_uploaded_file_ids(payload)
        semaphore = asyncio.Semaphore(self._concurrency_limit)

        async def fetch(file_id: str) -> PdfRestFile:
            async with semaphore:
                return await self._client.fetch_file_info(
                    file_id,
                    extra_query=extra_query,
                    extra_headers=extra_headers,
                    timeout=timeout,
                )

        return await asyncio.gather(*(fetch(file_id) for file_id in file_ids))

    async def create_from_paths(
        self,
        file_paths: FilePathInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by their path.

        Each entry may be a bare path-like object or a tuple of
        `(path, content_type)` / `(path, content_type, headers)` where headers
        mirrors the httpx multipart header mapping. All opened file handles are
        closed once the request completes.
        """
        normalized_paths = _normalize_path_inputs(file_paths)
        path_specs = [_parse_path_spec(spec) for spec in normalized_paths]

        async def attempt() -> list[PdfRestFile]:
            with ExitStack() as stack:
                upload_specs: list[tuple[str, FileTypes]] = []
                for path, content_type, headers in path_specs:
                    file_obj = stack.enter_context(path.open("rb"))
                    filename = path.name
                    normalized_spec: FileTypes
                    if headers:
                        normalized_spec = (filename, file_obj, content_type, headers)
                    elif content_type is not None:
                        normalized_spec = (filename, file_obj, content_type)
                    else:
                        normalized_spec = (filename, file_obj)
                    upload_specs.append((FILE_UPLOAD_FIELD_NAME, normalized_spec))

                request = self._client.prepare_request(
                    "POST",
                    "/upload",
                    files=upload_specs,
                    extra_query=extra_query,
                    extra_headers=extra_headers,
                    timeout=timeout,
                )
                payload = await self._client.send_request_once(request)
                file_ids = _extract_uploaded_file_ids(payload)
                results: list[PdfRestFile] = []
                semaphore = asyncio.Semaphore(self._concurrency_limit)

                async def throttled_fetch(file_id: str) -> PdfRestFile:
                    async with semaphore:
                        return await self._client.fetch_file_info(
                            file_id,
                            extra_query=extra_query,
                            extra_headers=extra_headers,
                            timeout=timeout,
                        )

                if file_ids:
                    results = list(
                        await asyncio.gather(
                            *(throttled_fetch(fid) for fid in file_ids)
                        )
                    )
                return results

        return await self._client.run_with_retry(
            attempt, operation="POST /upload (paths)"
        )

    async def create_from_urls(
        self,
        urls: UrlInput,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> list[PdfRestFile]:
        """Upload one or more files by providing remote URLs."""
        normalized_urls = UploadURLs.model_validate({"url": urls})
        request = self._client.prepare_request(
            "POST",
            "/upload",
            json_body=normalized_urls.model_dump(mode="json"),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        payload = await self._client.send_request(request)
        file_ids = _extract_uploaded_file_ids(payload)
        semaphore = asyncio.Semaphore(self._concurrency_limit)

        async def fetch(file_id: str) -> PdfRestFile:
            async with semaphore:
                return await self._client.fetch_file_info(
                    file_id,
                    extra_query=extra_query,
                    extra_headers=extra_headers,
                    timeout=timeout,
                )

        return await asyncio.gather(*(fetch(file_id) for file_id in file_ids))

    async def delete(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> None:
        """Delete one or more uploaded files by reference."""
        payload = DeletePayload.model_validate({"files": files})
        request = self._client.prepare_request(
            "POST",
            "/delete",
            json_body=payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = await self._client.send_request(request)
        deletion_response = PdfRestDeletionResponse.model_validate(raw_payload)
        _handle_deletion_failures(deletion_response)
        return

    async def read_bytes(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> bytes:
        response = await self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            return await response.aread()
        finally:
            await response.aclose()

    async def read_text(
        self,
        file_ref: PdfRestFile | str,
        *,
        encoding: str = "utf-8",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> str:
        response = await self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            response.encoding = encoding
            data = await response.aread()
            codec = response.encoding or encoding or "utf-8"
            return data.decode(codec)
        finally:
            await response.aclose()

    async def read_json(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Any:
        response = await self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        try:
            data = await response.aread()
            codec = response.encoding or "utf-8"
            return json.loads(data.decode(codec))
        finally:
            await response.aclose()

    async def write_bytes(
        self,
        file_ref: PdfRestFile | str,
        destination: DestinationPath,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> Path:
        response = await self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        path = Path(destination)
        try:
            with path.open("wb") as file_handle:
                async for chunk in response.aiter_bytes():
                    _ = file_handle.write(chunk)
        finally:
            await response.aclose()
        return path

    async def stream(
        self,
        file_ref: PdfRestFile | str,
        *,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> AsyncPdfRestFileStream:
        response = await self._client.download_file(
            _resolve_file_id(file_ref),
            extra_query=extra_query,
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return AsyncPdfRestFileStream(response)


class PdfRestClient(_SyncApiClient):
    """Synchronous client for interacting with the pdfrest API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | URL | None = None,
        timeout: TimeoutTypes | None = None,
        headers: AnyMapping | None = None,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """Initialize a synchronous pdfRest client.

        Args:
            api_key: API key sent in the `Api-Key` header.
            base_url: Base URL for the pdfRest API service.
            timeout: Request timeout override for this call.
            headers: Default headers merged into every request.
            http_client: Optional preconfigured `httpx.Client` instance to reuse.
            transport: Optional custom `httpx` transport.
            max_retries: Maximum number of retries for retryable failures.
        """
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            headers=headers,
            http_client=http_client,
            transport=transport,
            max_retries=max_retries,
        )
        files_client: PdfRestFilesClient = _FilesClient(self)
        self._files_client = files_client

    @override
    def __enter__(self) -> PdfRestClient:
        """Enter the client context manager and return this client instance.

        Returns:
            The current client instance.
        """
        _ = super().__enter__()
        return self

    @override
    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        """Exit the client context manager and close underlying HTTP resources.

        Args:
            exc_type: Exception type raised in the managed context, if any.
            exc: Exception instance raised in the managed context, if any.
            traceback: Traceback object for exceptions raised in the managed context.
        """
        super().__exit__(exc_type, exc, traceback)

    @property
    def files(self) -> PdfRestFilesClient:
        """Return the [PdfRestFilesClient][pdfrest.PdfRestFilesClient] helper bound to this client.

        Returns:
            The file-management helper bound to this client.
        """
        return self._files_client

    def up(
        self,
        *,
        extra_headers: AnyMapping | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> UpResponse:
        """Call the `/up` health endpoint and return server metadata.

        Calls the health endpoint and returns service metadata such as status, product, version, and release date. Use this as a lightweight connectivity check before running document workflows.

        Args:
            extra_headers: Additional HTTP headers merged into the request.
            extra_query: Additional query parameters merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `UpResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        request = self._prepare_request(
            "GET",
            "/up",
            extra_headers=extra_headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
        )
        payload = self._send_request(request)
        return UpResponse.model_validate(payload)

    def _convert_to_graphic(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        payload_model: type[BasePdfRestGraphicPayload[Any]],
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Shared helper used by image conversion endpoint methods.

        Args:
            endpoint: API endpoint path used for this request helper.
            payload: Raw payload values forwarded to payload validation.
            payload_model: Payload model class used to validate and serialize inputs.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.
        """
        return self._post_file_operation(
            endpoint=endpoint,
            payload=payload,
            payload_model=payload_model,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def query_pdf_info(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        queries: Sequence[PdfInfoQuery] | PdfInfoQuery = ALL_PDF_INFO_QUERIES,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestInfoResponse:
        """Query pdfRest for metadata describing a PDF document.

        Retrieves PDF metadata and structural flags (for example page count, tags, signatures, forms, transparency, and permission state). The `queries` argument controls which info keys pdfRest computes and returns.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            queries: Info fields to query from the `/pdf-info` endpoint.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `PdfRestInfoResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload = PdfInfoPayload.model_validate({"file": file, "queries": queries})
        request = self.prepare_request(
            "POST",
            "/pdf-info",
            json_body=payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_defaults=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = self._send_request(request)
        return PdfRestInfoResponse.model_validate(raw_payload)

    def summarize_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        target_word_count: int = 400,
        summary_format: SummaryFormat = "overview",
        pages: PdfPageSelection | None = None,
        output_format: SummaryOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> SummarizePdfTextResponse:
        """Summarize the textual content of a PDF, Markdown, or text document.

        Generates an inline summary from document text and returns it in a structured response model. You can scope to pages, choose summary style, and control output formatting for downstream display.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            target_word_count: Approximate target length for generated summary text.
            summary_format: Summary layout/style requested from pdfRest.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `SummarizePdfTextResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "target_word_count": target_word_count,
            "summary_format": summary_format,
            "output_format": output_format,
            "output_type": "json",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        validated_payload = SummarizePdfTextPayload.model_validate(payload)
        request = self.prepare_request(
            "POST",
            "/summarized-pdf-text",
            json_body=validated_payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = self._send_request(request)
        return SummarizePdfTextResponse.model_validate(raw_payload)

    def summarize_text_to_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        target_word_count: int = 400,
        summary_format: SummaryFormat = "overview",
        pages: PdfPageSelection | None = None,
        output_format: SummaryOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Summarize a document and return the result as a downloadable file.

        Generates a summary and returns a file-based response containing the produced summary document. Use this when you want downloadable artifacts instead of inline summary text.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            target_word_count: Approximate target length for generated summary text.
            summary_format: Summary layout/style requested from pdfRest.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "target_word_count": target_word_count,
            "summary_format": summary_format,
            "output_format": output_format,
            "output_type": "file",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/summarized-pdf-text",
            payload=payload,
            payload_model=SummarizePdfTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_markdown(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        page_break_comments: bool = False,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to Markdown and return a file-based response.

        Converts document content into Markdown and supports either inline text output or file output. This is useful when preparing PDFs for LLM/RAG indexing and markdown-centric tooling.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            page_break_comments: When true, inserts page-break marker comments in generated Markdown between source pages.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_type": "file",
            "page_break_comments": page_break_comments,
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/markdown",
            payload=payload,
            payload_model=ConvertToMarkdownPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def ocr_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        languages: OcrLanguage | Sequence[OcrLanguage] = "English",
        pages: PdfPageSelection | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Perform OCR on a PDF to make text searchable and extractable.

        Runs OCR on image-based PDFs to produce searchable text layers while preserving PDF layout. Use `language` to guide recognition and `output` to control output naming.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            languages: OCR language(s) to use when recognizing text in scanned or image-based pages.
            pages: Page selection to constrain processing to specific pages.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "languages": languages}
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-ocr-text",
            payload=payload,
            payload_model=OcrPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def translate_pdf_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_language: str,
        pages: PdfPageSelection | None = None,
        output_format: TranslateOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> TranslatePdfTextResponse:
        """Translate the textual content of a PDF, Markdown, or text document (JSON).

        Translates extracted document text and returns translated content inline when `output_type` is JSON. Supports page scoping and output formatting for multilingual text workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_language: Target language for translated output text.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `TranslatePdfTextResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_language": output_language,
            "output_format": output_format,
            "output_type": "json",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        validated_payload = TranslatePdfTextPayload.model_validate(payload)
        request = self.prepare_request(
            "POST",
            "/translated-pdf-text",
            json_body=validated_payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = self._send_request(request)
        return TranslatePdfTextResponse.model_validate(raw_payload)

    def translate_pdf_text_to_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_language: str,
        pages: PdfPageSelection | None = None,
        output_format: TranslateOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> TranslatePdfTextFileResponse:
        """Translate textual content and receive a file-based response.

        Translates document text and returns a file-based response with translated output artifacts. Choose this when you need downloadable translated files instead of inline text.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_language: Target language for translated output text.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `TranslatePdfTextFileResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_language": output_language,
            "output_format": output_format,
            "output_type": "file",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/translated-pdf-text",
            payload=payload,
            payload_model=TranslatePdfTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
            response_model=TranslatePdfTextFileResponse,
        )

    def extract_images(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Extract embedded images from a PDF.

        Extracts embedded images from the source PDF and returns them as output files. This is useful for asset reuse, auditing image quality, or downstream image processing.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/extracted-images",
            payload=payload,
            payload_model=ExtractImagesPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def extract_pdf_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        full_text: Literal["off", "by_page", "document"] = "document",
        preserve_line_breaks: bool = False,
        word_style: bool = False,
        word_coordinates: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> ExtractedTextDocument:
        """Extract text content from a PDF and return parsed JSON results.

        Extracts text from a PDF as inline JSON text content. Use `pages` to limit scope and `granularity`/related options to control how text is aggregated.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            full_text: Controls full-text output mode: disabled, aggregated document text, or per-page text blocks.
            preserve_line_breaks: Preserves detected line breaks in full-text output instead of flattening lines.
            word_style: Includes per-word style metadata such as font, size, and color in structured output.
            word_coordinates: Includes per-word coordinate metadata for positional text extraction.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `ExtractedTextDocument` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "full_text": full_text,
            "preserve_line_breaks": preserve_line_breaks,
            "word_style": word_style,
            "word_coordinates": word_coordinates,
            "output_type": "json",
        }
        if pages is not None:
            payload["pages"] = pages

        validated_payload = ExtractTextPayload.model_validate(payload)
        request = self.prepare_request(
            "POST",
            "/extracted-text",
            json_body=validated_payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = self._send_request(request)
        return ExtractedTextDocument.model_validate(raw_payload)

    def extract_pdf_text_to_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        full_text: ExtractTextGranularity = "document",
        preserve_line_breaks: bool = False,
        word_style: bool = False,
        word_coordinates: bool = False,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Extract text content from a PDF and return a file-based response.

        Extracts text into file outputs (including richer structured formats when requested). Use this for large outputs or when you need durable extracted-text artifacts.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            full_text: Controls full-text output mode: disabled, aggregated document text, or per-page text blocks.
            preserve_line_breaks: Preserves detected line breaks in full-text output instead of flattening lines.
            word_style: Includes per-word style metadata such as font, size, and color in structured output.
            word_coordinates: Includes per-word coordinate metadata for positional text extraction.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "full_text": full_text,
            "preserve_line_breaks": preserve_line_breaks,
            "word_style": word_style,
            "word_coordinates": word_coordinates,
            "output_type": "file",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/extracted-text",
            payload=payload,
            payload_model=ExtractTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def preview_redactions(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        redactions: PdfRedactionInstruction | Sequence[PdfRedactionInstruction],
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Generate a PDF redaction preview with annotated redaction rectangles.

        Builds a redaction preview PDF so you can inspect matches before permanently removing content. Redaction rules support literals, regex patterns, and preset detectors.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            redactions: Redaction rules to preview or apply.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "redactions": redactions,
        }
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-redacted-text-preview",
            payload=payload,
            payload_model=PdfRedactionPreviewPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def apply_redactions(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        rgb_color: PdfRGBColor | Sequence[int] | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Apply previously previewed redactions and return the final redacted PDF.

        Applies irreversible redactions to the PDF based on provided rules and outputs a redacted document. Use this after validating coverage with `preview_redactions`.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            rgb_color: RGB fill color applied to redaction rectangles when previewing/applying redactions.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
        }
        if rgb_color is not None:
            payload["rgb_color"] = rgb_color
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-redacted-text-applied",
            payload=payload,
            payload_model=PdfRedactionApplyPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def add_text_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        text_objects: PdfAddTextObject | Sequence[PdfAddTextObject],
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Insert one or more text blocks into a PDF.

        Places one or more text overlays onto a PDF with font, size, color, opacity, position, and rotation controls. This supports annotations, stamps, and templated labeling workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            text_objects: Text overlay objects to draw onto the document.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "text_objects": text_objects,
        }
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-added-text",
            payload=payload,
            payload_model=PdfAddTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def add_image_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        image: PdfRestFile | Sequence[PdfRestFile],
        x: int,
        y: int,
        page: int,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Insert an image into a single page of a PDF.

        Places an uploaded image onto target pages in a PDF with size/position controls. This is commonly used for logos, seals, and branding overlays.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            image: Image/PDF resource to place into the source document.
            x: Horizontal position in PDF points.
            y: Vertical position in PDF points.
            page: Target page number (or selector) where inserted content should be applied.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "image": image,
            "x": x,
            "y": y,
            "page": page,
        }
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-added-image",
            payload=payload,
            payload_model=PdfAddImagePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def split_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        page_groups: Sequence[PdfPageSelection] | PdfPageSelection | None = None,
        output_prefix: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Split a PDF into one or more PDF files based on the provided page groups.

        Splits a PDF into multiple outputs using page selections and grouping rules. Use this to break long documents into per-range or per-section files.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            page_groups: Page-selection groups that define each split output document.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if page_groups is not None:
            payload["page_groups"] = page_groups
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix

        return self._post_file_operation(
            endpoint="/split-pdf",
            payload=payload,
            payload_model=PdfSplitPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def merge_pdfs(
        self,
        sources: Sequence[PdfMergeInput],
        *,
        output_prefix: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Merge multiple PDFs (or page subsets) into a single PDF file.

        Merges multiple uploaded PDFs into a single output, with optional per-input page selections. This is useful for packet assembly and document bundling.

        Args:
            sources: Merge source list containing files with optional page selections per source.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"sources": sources}
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix

        return self._post_file_operation(
            endpoint="/merged-pdf",
            payload=payload,
            payload_model=PdfMergePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def zip_files(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Compress one or more files into a zip archive.

        Packages uploaded files into a ZIP archive and returns it as a file-based response. Use this to consolidate multiple outputs for a single download.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": files}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/zip",
            payload=payload,
            payload_model=ZipPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def unzip_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        password: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Extract files from a zip archive.

        Expands an uploaded ZIP archive into individual files on pdfRest storage and returns metadata for the extracted resources. This is useful when reusing uploaded bundles in later API calls.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            password: Password value used by encrypt/decrypt endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if password is not None:
            payload["password"] = password

        return self._post_file_operation(
            endpoint="/unzip",
            payload=payload,
            payload_model=UnzipPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_excel(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to an Excel spreadsheet.

        Converts PDF content into Excel workbook output optimized for tabular data extraction. Use this for spreadsheet-centric review or data cleanup workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/excel",
            payload=payload,
            payload_model=PdfToExcelPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_powerpoint(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to a PowerPoint presentation.

        Converts PDF pages into PowerPoint output suitable for slide editing and presentation reuse. This helps repurpose static PDF material into editable decks.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/powerpoint",
            payload=payload,
            payload_model=PdfToPowerpointPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_xfa_to_acroforms(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert an XFA PDF to an AcroForm-enabled PDF.

        Converts XFA form PDFs into AcroForm-compatible PDFs for broader tooling compatibility. Use this before importing/exporting form data with AcroForm-focused flows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-acroforms",
            payload=payload,
            payload_model=PdfXfaToAcroformsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_word(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to a Word document.

        Converts PDF content into Word output for document editing workflows. This is useful when users need editable text and layout reconstruction in DOCX format.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/word",
            payload=payload,
            payload_model=PdfToWordPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def import_form_data(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        data_file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Import form data from a data file into an existing PDF with form fields.

        Imports external form-data files (XFDF/FDF/XML variants) into a source PDF and outputs a filled document. This supports bulk form-filling and integration pipelines.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            data_file: Uploaded form-data file (for example XFDF/FDF/XML/XDP/XFD) to import into the PDF.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "data_file": data_file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-imported-form-data",
            payload=payload,
            payload_model=PdfImportFormDataPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def export_form_data(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        data_format: ExportDataFormat,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Export form data from a PDF into an external data file.

        Exports form field data from a PDF into a structured data format (such as XFDF/FDF/XML). Use this for downstream processing, storage, or migration of form values.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            data_format: Output form-data format to export (for example XFDF, FDF, XML, XDP, or XFD).
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "data_format": data_format,
        }
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/exported-form-data",
            payload=payload,
            payload_model=PdfExportFormDataPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def flatten_pdf_forms(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Flatten form fields in a PDF so they are no longer editable.

        Flattens interactive form fields into static page content so values are no longer editable. This is commonly used for finalization and archival workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/flattened-forms-pdf",
            payload=payload,
            payload_model=PdfFlattenFormsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def add_permissions_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        new_permissions_password: str,
        restrictions: Sequence[PdfRestriction] | None = None,
        current_open_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Add a permissions password and optional restrictions to a PDF.

        Applies owner permissions and restriction flags (print/copy/edit controls) to a PDF. This secures document capabilities without requiring an open password.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            new_permissions_password: New owner/permissions password to apply to the output PDF.
            restrictions: Permission restriction literals for protected PDFs.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "new_permissions_password": new_permissions_password,
        }
        if restrictions is not None:
            payload["restrictions"] = restrictions
        if current_open_password is not None:
            payload["current_open_password"] = current_open_password
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/restricted-pdf",
            payload=payload,
            payload_model=PdfRestrictPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def change_permissions_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_permissions_password: str,
        new_permissions_password: str,
        restrictions: Sequence[PdfRestriction] | None = None,
        current_open_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Rotate the permissions password and optionally update restrictions.

        Updates owner permissions/password settings and restriction flags on an already protected PDF. Use this to rotate credentials or revise allowed actions.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            new_permissions_password: New owner/permissions password to apply to the output PDF.
            restrictions: Permission restriction literals for protected PDFs.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_permissions_password": current_permissions_password,
            "new_permissions_password": new_permissions_password,
        }
        if restrictions is not None:
            payload["restrictions"] = restrictions
        if current_open_password is not None:
            payload["current_open_password"] = current_open_password
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/restricted-pdf",
            payload=payload,
            payload_model=PdfRestrictPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def add_open_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        new_open_password: str,
        current_permissions_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Encrypt a PDF with a new open password.

        Applies a user/open password so the PDF requires authentication before viewing. Optional permissions controls can also be set for opened documents.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            new_open_password: New user/open password required to open the output PDF.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "new_open_password": new_open_password,
        }
        if current_permissions_password is not None:
            payload["current_permissions_password"] = current_permissions_password
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/encrypted-pdf",
            payload=payload,
            payload_model=PdfEncryptPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def change_open_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_open_password: str,
        new_open_password: str,
        current_permissions_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Rotate the open password for an encrypted PDF.

        Replaces the existing open password with a new one while preserving or updating related protection options. Use this for credential rotation.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            new_open_password: New user/open password required to open the output PDF.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_open_password": current_open_password,
            "new_open_password": new_open_password,
        }
        if current_permissions_password is not None:
            payload["current_permissions_password"] = current_permissions_password
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/encrypted-pdf",
            payload=payload,
            payload_model=PdfEncryptPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def remove_open_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_open_password: str,
        current_permissions_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Decrypt a PDF by removing its open password.

        Removes the user/open password requirement from a PDF when the current password is provided. The output document can be opened without viewer authentication.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_open_password": current_open_password,
        }
        if current_permissions_password is not None:
            payload["current_permissions_password"] = current_permissions_password
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/decrypted-pdf",
            payload=payload,
            payload_model=PdfDecryptPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def remove_permissions_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_permissions_password: str,
        current_open_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Remove permissions restrictions from a PDF.

        Removes owner permission restrictions from a PDF when authorized with the existing owner password. This restores unrestricted editing/printing capabilities.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_permissions_password": current_permissions_password,
        }
        if current_open_password is not None:
            payload["current_open_password"] = current_open_password
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/unrestricted-pdf",
            payload=payload,
            payload_model=PdfUnrestrictPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def compress_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        compression_level: CompressionLevel,
        profile: PdfRestFile | Sequence[PdfRestFile] | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Compress a PDF using preset or custom compression profiles.

        Reduces PDF file size using preset or custom compression settings, with optional profile uploads. Use this for storage/bandwidth optimization while balancing quality.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            compression_level: Compression level or strategy option.
            profile: Uploaded color/compression profile as a `PdfRestFile`.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "compression_level": compression_level,
        }
        if profile is not None:
            payload["profile"] = profile
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/compressed-pdf",
            payload=payload,
            payload_model=PdfCompressPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def add_attachment_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        attachment: PdfRestFile | Sequence[PdfRestFile],
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Attach an uploaded file to a PDF.

        Embeds an uploaded file as an attachment inside a PDF container document. This supports package-style delivery where supplemental files travel with the PDF.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            attachment: Uploaded file to embed as an attachment in the output PDF.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "attachment": attachment}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-added-attachment",
            payload=payload,
            payload_model=PdfAddAttachmentPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def sign_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        signature_configuration: PdfSignatureConfiguration,
        credentials: PdfSignatureCredentials,
        logo: PdfRestFile | Sequence[PdfRestFile] | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Digitally sign a PDF using PFX credentials or a certificate/private key.

        Applies digital signatures using either PFX credentials or certificate/private-key inputs, with configurable visible signature placement and appearance. Use this for integrity, authenticity, and non-repudiation workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            signature_configuration: Signature placement and appearance settings.
            credentials: Digital signing credential bundle (PFX or cert/key files).
            logo: Optional uploaded logo file displayed in visible digital signature appearances.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "signature_configuration": signature_configuration,
            "credentials": credentials,
        }

        if logo is not None:
            payload["logo"] = logo
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/signed-pdf",
            payload=payload,
            payload_model=PdfSignPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def blank_pdf(
        self,
        *,
        page_size: PdfPageSize = "letter",
        page_count: int = 1,
        page_orientation: PdfPageOrientation | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Create a blank PDF with configurable size, count, and orientation.

        Creates a new blank PDF with configurable page size, orientation, and page count. This is useful as a template baseline for downstream stamping/filling workflows.

        Args:
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_count: Number of blank pages to generate in the new PDF.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "page_size": page_size,
            "page_count": page_count,
        }
        if page_orientation is not None:
            payload["page_orientation"] = page_orientation
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/blank-pdf",
            payload=payload,
            payload_model=PdfBlankPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_colors(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        color_profile: PdfPresetColorProfile | PdfRestFile | Sequence[PdfRestFile],
        preserve_black: bool = False,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert PDF colors using presets or a custom uploaded ICC profile.

        Converts document color spaces using preset profiles and optional black-preservation behavior. Use this to normalize output for print pipelines or color-management requirements.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            color_profile: Named color profile used by color conversion.
            preserve_black: When true, keeps pure black content from being remapped during color-profile conversion.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "color_profile": color_profile,
            "preserve_black": preserve_black,
        }
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdf-with-converted-colors",
            payload=payload,
            payload_model=PdfConvertColorsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def flatten_transparencies(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        quality: FlattenQuality = "medium",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Flatten transparent objects in a PDF.

        Flattens transparent objects into opaque content using selectable quality levels. This improves compatibility with workflows/devices that do not fully support transparency.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            quality: Quality preset understood by the selected endpoint.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "quality": quality}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/flattened-transparencies-pdf",
            payload=payload,
            payload_model=PdfFlattenTransparenciesPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def linearize_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Linearize a PDF for optimized fast web view.

        Linearizes the PDF for fast web view so first pages render sooner over network delivery. This improves user experience for browser-based document viewing.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/linearized-pdf",
            payload=payload,
            payload_model=PdfLinearizePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def flatten_annotations(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Flatten annotations into the PDF content.

        Burns annotation markup into page content so comments/highlights become static and non-editable. Use this when sharing finalized review copies.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/flattened-annotations-pdf",
            payload=payload,
            payload_model=PdfFlattenAnnotationsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def flatten_layers(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Flatten all layers in a PDF into a single layer.

        Flattens optional content groups (layers) into a single visible page representation. This avoids layer-dependent rendering differences across viewers.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/flattened-layers-pdf",
            payload=payload,
            payload_model=PdfFlattenLayersPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def rasterize_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Rasterize a PDF into a flattened bitmap-based PDF.

        Rasterizes PDF pages into image-based page content at a specified resolution. Use this for visual normalization, redaction hardening, or viewer compatibility scenarios.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/rasterized-pdf",
            payload=payload,
            payload_model=PdfRasterizePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_office_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample = 300,
        tagged_pdf: bool = False,
        locale: PdfConversionLocale | None = None,
        page_size: HtmlPageSize | None = None,
        page_margin: str | None = None,
        page_orientation: HtmlPageOrientation | None = None,
        web_layout: HtmlWebLayout | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a Microsoft Office file (Word, Excel, PowerPoint) to PDF.

        Converts Office documents into PDF output using conversion options for layout and fidelity. This is the main entry point for Word/Excel/PowerPoint-to-PDF workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            tagged_pdf: For Office conversion, toggles generation of tagged PDFs for accessibility workflows.
            locale: Locale used by locale-aware conversion options.
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_margin: Page margin setting (for example `8mm` or `0.5in`) for HTML/URL rendering outputs.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            web_layout: Rendering viewport profile (`desktop`, `tablet`, or `mobile`) for HTML/URL conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
            "compression": compression,
            "downsample": downsample,
            "tagged_pdf": tagged_pdf,
            "locale": locale,
            "page_size": page_size,
            "page_margin": page_margin,
            "page_orientation": page_orientation,
            "web_layout": web_layout,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertOfficeToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_postscript_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PostScript or EPS file to PDF.

        Converts PostScript content to PDF while preserving page content for modern PDF workflows. Use this when ingesting legacy print-oriented document formats.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
            "compression": compression,
            "downsample": downsample,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertPostscriptToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_email_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert an RFC822 email file to PDF.

        Converts email message files into PDF, including rendered message content and supported metadata/body parts. This supports archiving and compliance workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertEmailToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_image_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a supported image file to PDF.

        Converts one or more image files into PDF output and can combine them into multipage documents. Use this to normalize scanned/image assets into PDF containers.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertImageToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_html_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample = 300,
        page_size: HtmlPageSize = "letter",
        page_margin: str = "1.0in",
        page_orientation: HtmlPageOrientation = "portrait",
        web_layout: HtmlWebLayout = "desktop",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert an uploaded HTML file to PDF.

        Renders HTML content into PDF with page-size/orientation/layout and related rendering controls. This supports report generation and web-to-PDF publishing use cases.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_margin: Page margin setting (for example `8mm` or `0.5in`) for HTML/URL rendering outputs.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            web_layout: Rendering viewport profile (`desktop`, `tablet`, or `mobile`) for HTML/URL conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
            "compression": compression,
            "downsample": downsample,
            "page_size": page_size,
            "page_margin": page_margin,
            "page_orientation": page_orientation,
            "web_layout": web_layout,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertHtmlToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_url_to_pdf(
        self,
        url: UrlValue,
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample = 300,
        page_size: HtmlPageSize = "letter",
        page_margin: str = "1.0in",
        page_orientation: HtmlPageOrientation = "portrait",
        web_layout: HtmlWebLayout = "desktop",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert HTML content from one URL to PDF.

        Fetches remote web content by URL and renders it to PDF using HTML rendering options. Use this for automated webpage capture and archival.

        Args:
            url: Remote URL to ingest and convert.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_margin: Page margin setting (for example `8mm` or `0.5in`) for HTML/URL rendering outputs.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            web_layout: Rendering viewport profile (`desktop`, `tablet`, or `mobile`) for HTML/URL conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "url": url,
            "output": output,
            "compression": compression,
            "downsample": downsample,
            "page_size": page_size,
            "page_margin": page_margin,
            "page_orientation": page_orientation,
            "web_layout": web_layout,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertUrlToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def watermark_pdf_with_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        watermark_text: str,
        output: str | None = None,
        font: str | None = None,
        text_size: int = 72,
        text_color: PdfTextColor = (0, 0, 0),
        opacity: float = 0.5,
        horizontal_alignment: WatermarkHorizontalAlignment = "center",
        vertical_alignment: WatermarkVerticalAlignment = "center",
        x: int = 0,
        y: int = 0,
        rotation: int = 0,
        pages: PdfPageSelection | None = None,
        behind_page: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Apply a text watermark to a PDF.

        Applies text watermarks with control over placement, rotation, color, opacity, and alignment. Use this for confidentiality marks, drafts, and document branding.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            watermark_text: Text content to render as the watermark.
            output: Output filename prefix used by pdfRest when creating files.
            font: Font family name for rendered text.
            text_size: Watermark text size in points.
            text_color: Watermark text color as RGB or CMYK channel values.
            opacity: Opacity in range 0.0 to 1.0.
            horizontal_alignment: Horizontal alignment anchor used when placing watermark content.
            vertical_alignment: Vertical alignment anchor used when placing watermark content.
            x: Horizontal position in PDF points.
            y: Vertical position in PDF points.
            rotation: Rotation angle in degrees.
            pages: Page selection to constrain processing to specific pages.
            behind_page: Target page number (or selector) where inserted content should be applied.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "watermark_text": watermark_text,
            "output": output,
            "font": font,
            "text_size": text_size,
            "text_color": text_color,
            "opacity": opacity,
            "horizontal_alignment": horizontal_alignment,
            "vertical_alignment": vertical_alignment,
            "x": x,
            "y": y,
            "rotation": rotation,
            "pages": pages,
            "behind_page": behind_page,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/watermarked-pdf",
            payload=payload,
            payload_model=PdfTextWatermarkPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def watermark_pdf_with_image(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        watermark_file: PdfRestFile | Sequence[PdfRestFile],
        output: str | None = None,
        watermark_file_scale: float = 0.5,
        opacity: float = 0.5,
        horizontal_alignment: WatermarkHorizontalAlignment = "center",
        vertical_alignment: WatermarkVerticalAlignment = "center",
        x: int = 0,
        y: int = 0,
        rotation: int = 0,
        pages: PdfPageSelection | None = None,
        behind_page: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Apply an image watermark to a PDF.

        Applies image watermarks (for example logos/seals) with placement and opacity controls. This is useful for branded overlays and visual ownership marks.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            watermark_file: Uploaded image used as watermark content.
            output: Output filename prefix used by pdfRest when creating files.
            watermark_file_scale: Scale multiplier applied to the watermark file graphic before placement.
            opacity: Opacity in range 0.0 to 1.0.
            horizontal_alignment: Horizontal alignment anchor used when placing watermark content.
            vertical_alignment: Vertical alignment anchor used when placing watermark content.
            x: Horizontal position in PDF points.
            y: Vertical position in PDF points.
            rotation: Rotation angle in degrees.
            pages: Page selection to constrain processing to specific pages.
            behind_page: Target page number (or selector) where inserted content should be applied.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "watermark_file": watermark_file,
            "output": output,
            "watermark_file_scale": watermark_file_scale,
            "opacity": opacity,
            "horizontal_alignment": horizontal_alignment,
            "vertical_alignment": vertical_alignment,
            "x": x,
            "y": y,
            "rotation": rotation,
            "pages": pages,
            "behind_page": behind_page,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return self._post_file_operation(
            endpoint="/watermarked-pdf",
            payload=payload,
            payload_model=PdfImageWatermarkPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_pdfa(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_type: PdfAOutputType,
        output: str | None = None,
        rasterize_if_errors_encountered: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to a specified PDF/A version.

        Converts input PDFs to selected PDF/A conformance levels for long-term archival compatibility. Choose the target conformance profile that matches your compliance requirements.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_type: Output mode for endpoints supporting inline or file output.
            output: Output filename prefix used by pdfRest when creating files.
            rasterize_if_errors_encountered: When enabled, allows rasterized fallback if strict conformance conversion encounters nonconforming content.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_type": output_type,
            "rasterize_if_errors_encountered": rasterize_if_errors_encountered,
        }
        if output is not None:
            payload["output"] = output
        return self._post_file_operation(
            endpoint="/pdfa",
            payload=payload,
            payload_model=PdfToPdfaPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_pdfx(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_type: PdfXType,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to a specified PDF/X version.

        Converts input PDFs to selected PDF/X conformance levels for print-production workflows. Use this when downstream print tooling expects standardized PDF/X output.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_type: Output mode for endpoints supporting inline or file output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "output_type": output_type}
        if output is not None:
            payload["output"] = output

        return self._post_file_operation(
            endpoint="/pdfx",
            payload=payload,
            payload_model=PdfToPdfxPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_png(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: PngColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to PNG images.

        Converts PDF pages to PNG images with configurable color model, smoothing, and page selection controls. Suitable for high-fidelity raster exports and previews.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return self._convert_to_graphic(
            endpoint="/png",
            payload=payload,
            payload_model=PngPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_bmp(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: BmpColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to BMP images.

        Converts PDF pages to BMP images with configurable color model and page selection. Use this for legacy bitmap workflows that require BMP output.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return self._convert_to_graphic(
            endpoint="/bmp",
            payload=payload,
            payload_model=BmpPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_gif(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: GifColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to GIF images.

        Converts PDF pages to GIF images with configurable color model and page selection. Useful for lightweight graphics workflows and compatibility scenarios.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return self._convert_to_graphic(
            endpoint="/gif",
            payload=payload,
            payload_model=GifPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_jpeg(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: JpegColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        jpeg_quality: int = 75,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to JPEG images.

        Converts PDF pages to JPEG images with configurable color model and page selection. Use this for compressed photo-friendly page exports.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            jpeg_quality: JPEG quality setting (1-100) controlling compression level and output fidelity.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
            "jpeg_quality": jpeg_quality,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return self._convert_to_graphic(
            endpoint="/jpg",
            payload=payload,
            payload_model=JpegPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    def convert_to_tiff(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: TiffColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to TIFF images.

        Converts PDF pages to TIFF images with configurable color model and page selection. This is commonly used in archival, scanning, and print-imaging pipelines.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return self._convert_to_graphic(
            endpoint="/tif",
            payload=payload,
            payload_model=TiffPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )


class AsyncPdfRestClient(_AsyncApiClient):
    """Asynchronous client for interacting with the pdfrest API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | URL | None = None,
        timeout: TimeoutTypes | None = None,
        headers: AnyMapping | None = None,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency_limit: int = DEFAULT_FILE_INFO_CONCURRENCY,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """Initialize an asynchronous pdfRest client.

        Args:
            api_key: API key sent in the `Api-Key` header.
            base_url: Base URL for the pdfRest API service.
            timeout: Request timeout override for this call.
            headers: Default headers merged into every request.
            http_client: Optional preconfigured `httpx.Client` instance to reuse.
            transport: Optional custom `httpx` transport.
            concurrency_limit: Maximum concurrent file-info fetch operations used by async file helper methods.
            max_retries: Maximum number of retries for retryable failures.
        """
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            headers=headers,
            http_client=http_client,
            transport=transport,
            concurrency_limit=concurrency_limit,
            max_retries=max_retries,
        )
        files_client: AsyncPdfRestFilesClient = _AsyncFilesClient(self)
        self._files_client = files_client

    @override
    async def __aenter__(self) -> AsyncPdfRestClient:
        """Enter the client context manager and return this client instance.

        Returns:
            The current client instance.
        """
        _ = await super().__aenter__()
        return self

    @override
    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        """Exit the client context manager and close underlying HTTP resources.

        Args:
            exc_type: Exception type raised in the managed context, if any.
            exc: Exception instance raised in the managed context, if any.
            traceback: Traceback object for exceptions raised in the managed context.
        """
        await super().__aexit__(exc_type, exc, traceback)

    @property
    def files(self) -> AsyncPdfRestFilesClient:
        """Return the [AsyncPdfRestFilesClient][pdfrest.AsyncPdfRestFilesClient] helper bound to this client.

        Returns:
            The file-management helper bound to this client.
        """
        return self._files_client

    async def query_pdf_info(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        queries: Sequence[PdfInfoQuery] | PdfInfoQuery = ALL_PDF_INFO_QUERIES,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestInfoResponse:
        """Asynchronous variant of [PdfRestClient.query_pdf_info][pdfrest.PdfRestClient.query_pdf_info].

        Retrieves PDF metadata and structural flags (for example page count, tags, signatures, forms, transparency, and permission state). The `queries` argument controls which info keys pdfRest computes and returns.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            queries: Info fields to query from the `/pdf-info` endpoint.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `PdfRestInfoResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload = PdfInfoPayload.model_validate({"file": file, "queries": queries})
        request = self.prepare_request(
            "POST",
            "/pdf-info",
            json_body=payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_defaults=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = await self._send_request(request)
        return PdfRestInfoResponse.model_validate(raw_payload)

    async def summarize_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        target_word_count: int = 400,
        summary_format: SummaryFormat = "overview",
        pages: PdfPageSelection | None = None,
        output_format: SummaryOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> SummarizePdfTextResponse:
        """Asynchronous variant of [PdfRestClient.summarize_text][pdfrest.PdfRestClient.summarize_text].

        Generates an inline summary from document text and returns it in a structured response model. You can scope to pages, choose summary style, and control output formatting for downstream display.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            target_word_count: Approximate target length for generated summary text.
            summary_format: Summary layout/style requested from pdfRest.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `SummarizePdfTextResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "target_word_count": target_word_count,
            "summary_format": summary_format,
            "output_format": output_format,
            "output_type": "json",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        validated_payload = SummarizePdfTextPayload.model_validate(payload)
        request = self.prepare_request(
            "POST",
            "/summarized-pdf-text",
            json_body=validated_payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = await self._send_request(request)
        return SummarizePdfTextResponse.model_validate(raw_payload)

    async def summarize_text_to_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        target_word_count: int = 400,
        summary_format: SummaryFormat = "overview",
        pages: PdfPageSelection | None = None,
        output_format: SummaryOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.summarize_text_to_file][pdfrest.PdfRestClient.summarize_text_to_file].

        Generates a summary and returns a file-based response containing the produced summary document. Use this when you want downloadable artifacts instead of inline summary text.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            target_word_count: Approximate target length for generated summary text.
            summary_format: Summary layout/style requested from pdfRest.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "target_word_count": target_word_count,
            "summary_format": summary_format,
            "output_format": output_format,
            "output_type": "file",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/summarized-pdf-text",
            payload=payload,
            payload_model=SummarizePdfTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_markdown(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        page_break_comments: bool = False,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_markdown][pdfrest.PdfRestClient.convert_to_markdown].

        Converts document content into Markdown and supports either inline text output or file output. This is useful when preparing PDFs for LLM/RAG indexing and markdown-centric tooling.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            page_break_comments: When true, inserts page-break marker comments in generated Markdown between source pages.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_type": "file",
            "page_break_comments": page_break_comments,
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/markdown",
            payload=payload,
            payload_model=ConvertToMarkdownPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def ocr_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        languages: OcrLanguage | Sequence[OcrLanguage] = "English",
        pages: PdfPageSelection | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.ocr_pdf][pdfrest.PdfRestClient.ocr_pdf].

        Runs OCR on image-based PDFs to produce searchable text layers while preserving PDF layout. Use `language` to guide recognition and `output` to control output naming.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            languages: OCR language(s) to use when recognizing text in scanned or image-based pages.
            pages: Page selection to constrain processing to specific pages.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "languages": languages}
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-ocr-text",
            payload=payload,
            payload_model=OcrPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def translate_pdf_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_language: str,
        pages: PdfPageSelection | None = None,
        output_format: TranslateOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> TranslatePdfTextResponse:
        """Asynchronous variant of [PdfRestClient.translate_pdf_text][pdfrest.PdfRestClient.translate_pdf_text].

        Translates extracted document text and returns translated content inline when `output_type` is JSON. Supports page scoping and output formatting for multilingual text workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_language: Target language for translated output text.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `TranslatePdfTextResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_language": output_language,
            "output_format": output_format,
            "output_type": "json",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        validated_payload = TranslatePdfTextPayload.model_validate(payload)
        request = self.prepare_request(
            "POST",
            "/translated-pdf-text",
            json_body=validated_payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = await self._send_request(request)
        return TranslatePdfTextResponse.model_validate(raw_payload)

    async def translate_pdf_text_to_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_language: str,
        pages: PdfPageSelection | None = None,
        output_format: TranslateOutputFormat = "markdown",
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> TranslatePdfTextFileResponse:
        """Asynchronous variant of [PdfRestClient.translate_pdf_text_to_file][pdfrest.PdfRestClient.translate_pdf_text_to_file].

        Translates document text and returns a file-based response with translated output artifacts. Choose this when you need downloadable translated files instead of inline text.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_language: Target language for translated output text.
            pages: Page selection to constrain processing to specific pages.
            output_format: Text format returned for generated textual output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `TranslatePdfTextFileResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_language": output_language,
            "output_format": output_format,
            "output_type": "file",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/translated-pdf-text",
            payload=payload,
            payload_model=TranslatePdfTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
            response_model=TranslatePdfTextFileResponse,
        )

    async def extract_images(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.extract_images][pdfrest.PdfRestClient.extract_images].

        Extracts embedded images from the source PDF and returns them as output files. This is useful for asset reuse, auditing image quality, or downstream image processing.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/extracted-images",
            payload=payload,
            payload_model=ExtractImagesPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def extract_pdf_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        full_text: Literal["off", "by_page", "document"] = "document",
        preserve_line_breaks: bool = False,
        word_style: bool = False,
        word_coordinates: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> ExtractedTextDocument:
        """Asynchronous variant of [PdfRestClient.extract_pdf_text][pdfrest.PdfRestClient.extract_pdf_text].

        Extracts text from a PDF as inline JSON text content. Use `pages` to limit scope and `granularity`/related options to control how text is aggregated.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            full_text: Controls full-text output mode: disabled, aggregated document text, or per-page text blocks.
            preserve_line_breaks: Preserves detected line breaks in full-text output instead of flattening lines.
            word_style: Includes per-word style metadata such as font, size, and color in structured output.
            word_coordinates: Includes per-word coordinate metadata for positional text extraction.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `ExtractedTextDocument` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "full_text": full_text,
            "preserve_line_breaks": preserve_line_breaks,
            "word_style": word_style,
            "word_coordinates": word_coordinates,
            "output_type": "json",
        }
        if pages is not None:
            payload["pages"] = pages

        validated_payload = ExtractTextPayload.model_validate(payload)
        request = self.prepare_request(
            "POST",
            "/extracted-text",
            json_body=validated_payload.model_dump(
                mode="json", by_alias=True, exclude_none=True, exclude_unset=True
            ),
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
        raw_payload = await self._send_request(request)
        return ExtractedTextDocument.model_validate(raw_payload)

    async def extract_pdf_text_to_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        pages: PdfPageSelection | None = None,
        full_text: ExtractTextGranularity = "document",
        preserve_line_breaks: bool = False,
        word_style: bool = False,
        word_coordinates: bool = False,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.extract_pdf_text_to_file][pdfrest.PdfRestClient.extract_pdf_text_to_file].

        Extracts text into file outputs (including richer structured formats when requested). Use this for large outputs or when you need durable extracted-text artifacts.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            pages: Page selection to constrain processing to specific pages.
            full_text: Controls full-text output mode: disabled, aggregated document text, or per-page text blocks.
            preserve_line_breaks: Preserves detected line breaks in full-text output instead of flattening lines.
            word_style: Includes per-word style metadata such as font, size, and color in structured output.
            word_coordinates: Includes per-word coordinate metadata for positional text extraction.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "full_text": full_text,
            "preserve_line_breaks": preserve_line_breaks,
            "word_style": word_style,
            "word_coordinates": word_coordinates,
            "output_type": "file",
        }
        if pages is not None:
            payload["pages"] = pages
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/extracted-text",
            payload=payload,
            payload_model=ExtractTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def preview_redactions(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        redactions: PdfRedactionInstruction | Sequence[PdfRedactionInstruction],
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.preview_redactions][pdfrest.PdfRestClient.preview_redactions].

        Builds a redaction preview PDF so you can inspect matches before permanently removing content. Redaction rules support literals, regex patterns, and preset detectors.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            redactions: Redaction rules to preview or apply.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "redactions": redactions,
        }
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-redacted-text-preview",
            payload=payload,
            payload_model=PdfRedactionPreviewPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def apply_redactions(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        rgb_color: PdfRGBColor | Sequence[int] | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.apply_redactions][pdfrest.PdfRestClient.apply_redactions].

        Applies irreversible redactions to the PDF based on provided rules and outputs a redacted document. Use this after validating coverage with `preview_redactions`.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            rgb_color: RGB fill color applied to redaction rectangles when previewing/applying redactions.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
        }
        if rgb_color is not None:
            payload["rgb_color"] = rgb_color
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-redacted-text-applied",
            payload=payload,
            payload_model=PdfRedactionApplyPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def add_text_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        text_objects: PdfAddTextObject | Sequence[PdfAddTextObject],
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.add_text_to_pdf][pdfrest.PdfRestClient.add_text_to_pdf].

        Places one or more text overlays onto a PDF with font, size, color, opacity, position, and rotation controls. This supports annotations, stamps, and templated labeling workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            text_objects: Text overlay objects to draw onto the document.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "text_objects": text_objects,
        }
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-added-text",
            payload=payload,
            payload_model=PdfAddTextPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def add_image_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        image: PdfRestFile | Sequence[PdfRestFile],
        x: int,
        y: int,
        page: int,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.add_image_to_pdf][pdfrest.PdfRestClient.add_image_to_pdf].

        Places an uploaded image onto target pages in a PDF with size/position controls. This is commonly used for logos, seals, and branding overlays.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            image: Image/PDF resource to place into the source document.
            x: Horizontal position in PDF points.
            y: Vertical position in PDF points.
            page: Target page number (or selector) where inserted content should be applied.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "image": image,
            "x": x,
            "y": y,
            "page": page,
        }
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-added-image",
            payload=payload,
            payload_model=PdfAddImagePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def up(
        self,
        *,
        extra_headers: AnyMapping | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> UpResponse:
        """Asynchronous variant of [PdfRestClient.up][pdfrest.PdfRestClient.up].

        Calls the health endpoint and returns service metadata such as status, product, version, and release date. Use this as a lightweight connectivity check before running document workflows.

        Args:
            extra_headers: Additional HTTP headers merged into the request.
            extra_query: Additional query parameters merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated `UpResponse` model.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        request = self._prepare_request(
            "GET",
            "/up",
            extra_headers=extra_headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
        )
        payload = await self._send_request(request)
        return UpResponse.model_validate(payload)

    async def _convert_to_graphic(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        payload_model: type[BasePdfRestGraphicPayload[Any]],
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous shared helper for image conversion endpoint methods. Mirrors [PdfRestClient._convert_to_graphic][pdfrest.PdfRestClient._convert_to_graphic].

        Args:
            endpoint: API endpoint path used for this request helper.
            payload: Raw payload values forwarded to payload validation.
            payload_model: Payload model class used to validate and serialize inputs.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.
        """
        return await self._post_file_operation(
            endpoint=endpoint,
            payload=payload,
            payload_model=payload_model,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def split_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        page_groups: Sequence[PdfPageSelection] | PdfPageSelection | None = None,
        output_prefix: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.split_pdf][pdfrest.PdfRestClient.split_pdf].

        Splits a PDF into multiple outputs using page selections and grouping rules. Use this to break long documents into per-range or per-section files.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            page_groups: Page-selection groups that define each split output document.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if page_groups is not None:
            payload["page_groups"] = page_groups
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix

        return await self._post_file_operation(
            endpoint="/split-pdf",
            payload=payload,
            payload_model=PdfSplitPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def merge_pdfs(
        self,
        sources: Sequence[PdfMergeInput],
        *,
        output_prefix: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.merge_pdfs][pdfrest.PdfRestClient.merge_pdfs].

        Merges multiple uploaded PDFs into a single output, with optional per-input page selections. This is useful for packet assembly and document bundling.

        Args:
            sources: Merge source list containing files with optional page selections per source.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"sources": sources}
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix

        return await self._post_file_operation(
            endpoint="/merged-pdf",
            payload=payload,
            payload_model=PdfMergePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def zip_files(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.zip_files][pdfrest.PdfRestClient.zip_files].

        Packages uploaded files into a ZIP archive and returns it as a file-based response. Use this to consolidate multiple outputs for a single download.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": files}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/zip",
            payload=payload,
            payload_model=ZipPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def unzip_file(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        password: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.unzip_file][pdfrest.PdfRestClient.unzip_file].

        Expands an uploaded ZIP archive into individual files on pdfRest storage and returns metadata for the extracted resources. This is useful when reusing uploaded bundles in later API calls.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            password: Password value used by encrypt/decrypt endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if password is not None:
            payload["password"] = password

        return await self._post_file_operation(
            endpoint="/unzip",
            payload=payload,
            payload_model=UnzipPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_excel(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_excel][pdfrest.PdfRestClient.convert_to_excel].

        Converts PDF content into Excel workbook output optimized for tabular data extraction. Use this for spreadsheet-centric review or data cleanup workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/excel",
            payload=payload,
            payload_model=PdfToExcelPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_powerpoint(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_powerpoint][pdfrest.PdfRestClient.convert_to_powerpoint].

        Converts PDF pages into PowerPoint output suitable for slide editing and presentation reuse. This helps repurpose static PDF material into editable decks.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/powerpoint",
            payload=payload,
            payload_model=PdfToPowerpointPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_xfa_to_acroforms(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_xfa_to_acroforms][pdfrest.PdfRestClient.convert_xfa_to_acroforms].

        Converts XFA form PDFs into AcroForm-compatible PDFs for broader tooling compatibility. Use this before importing/exporting form data with AcroForm-focused flows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-acroforms",
            payload=payload,
            payload_model=PdfXfaToAcroformsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_word(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_word][pdfrest.PdfRestClient.convert_to_word].

        Converts PDF content into Word output for document editing workflows. This is useful when users need editable text and layout reconstruction in DOCX format.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/word",
            payload=payload,
            payload_model=PdfToWordPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def import_form_data(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        data_file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.import_form_data][pdfrest.PdfRestClient.import_form_data].

        Imports external form-data files (XFDF/FDF/XML variants) into a source PDF and outputs a filled document. This supports bulk form-filling and integration pipelines.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            data_file: Uploaded form-data file (for example XFDF/FDF/XML/XDP/XFD) to import into the PDF.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "data_file": data_file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-imported-form-data",
            payload=payload,
            payload_model=PdfImportFormDataPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def export_form_data(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        data_format: ExportDataFormat,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.export_form_data][pdfrest.PdfRestClient.export_form_data].

        Exports form field data from a PDF into a structured data format (such as XFDF/FDF/XML). Use this for downstream processing, storage, or migration of form values.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            data_format: Output form-data format to export (for example XFDF, FDF, XML, XDP, or XFD).
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "data_format": data_format,
        }
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/exported-form-data",
            payload=payload,
            payload_model=PdfExportFormDataPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def flatten_pdf_forms(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.flatten_pdf_forms][pdfrest.PdfRestClient.flatten_pdf_forms].

        Flattens interactive form fields into static page content so values are no longer editable. This is commonly used for finalization and archival workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/flattened-forms-pdf",
            payload=payload,
            payload_model=PdfFlattenFormsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def add_permissions_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        new_permissions_password: str,
        restrictions: Sequence[PdfRestriction] | None = None,
        current_open_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.add_permissions_password][pdfrest.PdfRestClient.add_permissions_password].

        Applies owner permissions and restriction flags (print/copy/edit controls) to a PDF. This secures document capabilities without requiring an open password.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            new_permissions_password: New owner/permissions password to apply to the output PDF.
            restrictions: Permission restriction literals for protected PDFs.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "new_permissions_password": new_permissions_password,
        }
        if restrictions is not None:
            payload["restrictions"] = restrictions
        if current_open_password is not None:
            payload["current_open_password"] = current_open_password
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/restricted-pdf",
            payload=payload,
            payload_model=PdfRestrictPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def change_permissions_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_permissions_password: str,
        new_permissions_password: str,
        restrictions: Sequence[PdfRestriction] | None = None,
        current_open_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.change_permissions_password][pdfrest.PdfRestClient.change_permissions_password].

        Updates owner permissions/password settings and restriction flags on an already protected PDF. Use this to rotate credentials or revise allowed actions.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            new_permissions_password: New owner/permissions password to apply to the output PDF.
            restrictions: Permission restriction literals for protected PDFs.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_permissions_password": current_permissions_password,
            "new_permissions_password": new_permissions_password,
        }
        if restrictions is not None:
            payload["restrictions"] = restrictions
        if current_open_password is not None:
            payload["current_open_password"] = current_open_password
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/restricted-pdf",
            payload=payload,
            payload_model=PdfRestrictPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def remove_permissions_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_permissions_password: str,
        current_open_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.remove_permissions_password][pdfrest.PdfRestClient.remove_permissions_password].

        Removes owner permission restrictions from a PDF when authorized with the existing owner password. This restores unrestricted editing/printing capabilities.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_permissions_password": current_permissions_password,
        }
        if current_open_password is not None:
            payload["current_open_password"] = current_open_password
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/unrestricted-pdf",
            payload=payload,
            payload_model=PdfUnrestrictPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def add_open_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        new_open_password: str,
        current_permissions_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.add_open_password][pdfrest.PdfRestClient.add_open_password].

        Applies a user/open password so the PDF requires authentication before viewing. Optional permissions controls can also be set for opened documents.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            new_open_password: New user/open password required to open the output PDF.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "new_open_password": new_open_password,
        }
        if current_permissions_password is not None:
            payload["current_permissions_password"] = current_permissions_password
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/encrypted-pdf",
            payload=payload,
            payload_model=PdfEncryptPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def change_open_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_open_password: str,
        new_open_password: str,
        current_permissions_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.change_open_password][pdfrest.PdfRestClient.change_open_password].

        Replaces the existing open password with a new one while preserving or updating related protection options. Use this for credential rotation.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            new_open_password: New user/open password required to open the output PDF.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_open_password": current_open_password,
            "new_open_password": new_open_password,
        }
        if current_permissions_password is not None:
            payload["current_permissions_password"] = current_permissions_password
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/encrypted-pdf",
            payload=payload,
            payload_model=PdfEncryptPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def remove_open_password(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        current_open_password: str,
        current_permissions_password: str | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.remove_open_password][pdfrest.PdfRestClient.remove_open_password].

        Removes the user/open password requirement from a PDF when the current password is provided. The output document can be opened without viewer authentication.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            current_open_password: Current user/open password required to unlock the source PDF before changes.
            current_permissions_password: Current owner/permissions password used to authorize permission updates/removal.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "current_open_password": current_open_password,
        }
        if current_permissions_password is not None:
            payload["current_permissions_password"] = current_permissions_password
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/decrypted-pdf",
            payload=payload,
            payload_model=PdfDecryptPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def compress_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        compression_level: CompressionLevel,
        profile: PdfRestFile | Sequence[PdfRestFile] | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.compress_pdf][pdfrest.PdfRestClient.compress_pdf].

        Reduces PDF file size using preset or custom compression settings, with optional profile uploads. Use this for storage/bandwidth optimization while balancing quality.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            compression_level: Compression level or strategy option.
            profile: Uploaded color/compression profile as a `PdfRestFile`.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "compression_level": compression_level,
        }
        if profile is not None:
            payload["profile"] = profile
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/compressed-pdf",
            payload=payload,
            payload_model=PdfCompressPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def add_attachment_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        attachment: PdfRestFile | Sequence[PdfRestFile],
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.add_attachment_to_pdf][pdfrest.PdfRestClient.add_attachment_to_pdf].

        Embeds an uploaded file as an attachment inside a PDF container document. This supports package-style delivery where supplemental files travel with the PDF.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            attachment: Uploaded file to embed as an attachment in the output PDF.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "attachment": attachment}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-added-attachment",
            payload=payload,
            payload_model=PdfAddAttachmentPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def sign_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        signature_configuration: PdfSignatureConfiguration,
        credentials: PdfSignatureCredentials,
        logo: PdfRestFile | Sequence[PdfRestFile] | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.sign_pdf][pdfrest.PdfRestClient.sign_pdf].

        Applies digital signatures using either PFX credentials or certificate/private-key inputs, with configurable visible signature placement and appearance. Use this for integrity, authenticity, and non-repudiation workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            signature_configuration: Signature placement and appearance settings.
            credentials: Digital signing credential bundle (PFX or cert/key files).
            logo: Optional uploaded logo file displayed in visible digital signature appearances.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "signature_configuration": signature_configuration,
            "credentials": credentials,
        }

        if logo is not None:
            payload["logo"] = logo
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/signed-pdf",
            payload=payload,
            payload_model=PdfSignPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def blank_pdf(
        self,
        *,
        page_size: PdfPageSize = "letter",
        page_count: int = 1,
        page_orientation: PdfPageOrientation | None = None,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.blank_pdf][pdfrest.PdfRestClient.blank_pdf].

        Creates a new blank PDF with configurable page size, orientation, and page count. This is useful as a template baseline for downstream stamping/filling workflows.

        Args:
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_count: Number of blank pages to generate in the new PDF.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "page_size": page_size,
            "page_count": page_count,
        }
        if page_orientation is not None:
            payload["page_orientation"] = page_orientation
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/blank-pdf",
            payload=payload,
            payload_model=PdfBlankPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_colors(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        color_profile: PdfPresetColorProfile | PdfRestFile | Sequence[PdfRestFile],
        preserve_black: bool = False,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_colors][pdfrest.PdfRestClient.convert_colors].

        Converts document color spaces using preset profiles and optional black-preservation behavior. Use this to normalize output for print pipelines or color-management requirements.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            color_profile: Named color profile used by color conversion.
            preserve_black: When true, keeps pure black content from being remapped during color-profile conversion.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "color_profile": color_profile,
            "preserve_black": preserve_black,
        }
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdf-with-converted-colors",
            payload=payload,
            payload_model=PdfConvertColorsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def flatten_transparencies(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        quality: FlattenQuality = "medium",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.flatten_transparencies][pdfrest.PdfRestClient.flatten_transparencies].

        Flattens transparent objects into opaque content using selectable quality levels. This improves compatibility with workflows/devices that do not fully support transparency.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            quality: Quality preset understood by the selected endpoint.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "quality": quality}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/flattened-transparencies-pdf",
            payload=payload,
            payload_model=PdfFlattenTransparenciesPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def linearize_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.linearize_pdf][pdfrest.PdfRestClient.linearize_pdf].

        Linearizes the PDF for fast web view so first pages render sooner over network delivery. This improves user experience for browser-based document viewing.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/linearized-pdf",
            payload=payload,
            payload_model=PdfLinearizePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def flatten_annotations(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.flatten_annotations][pdfrest.PdfRestClient.flatten_annotations].

        Burns annotation markup into page content so comments/highlights become static and non-editable. Use this when sharing finalized review copies.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/flattened-annotations-pdf",
            payload=payload,
            payload_model=PdfFlattenAnnotationsPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def flatten_layers(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.flatten_layers][pdfrest.PdfRestClient.flatten_layers].

        Flattens optional content groups (layers) into a single visible page representation. This avoids layer-dependent rendering differences across viewers.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/flattened-layers-pdf",
            payload=payload,
            payload_model=PdfFlattenLayersPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def rasterize_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.rasterize_pdf][pdfrest.PdfRestClient.rasterize_pdf].

        Rasterizes PDF pages into image-based page content at a specified resolution. Use this for visual normalization, redaction hardening, or viewer compatibility scenarios.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/rasterized-pdf",
            payload=payload,
            payload_model=PdfRasterizePayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_office_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample = 300,
        tagged_pdf: bool = False,
        locale: PdfConversionLocale | None = None,
        page_size: HtmlPageSize | None = None,
        page_margin: str | None = None,
        page_orientation: HtmlPageOrientation | None = None,
        web_layout: HtmlWebLayout | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_office_to_pdf][pdfrest.PdfRestClient.convert_office_to_pdf].

        Converts Office documents into PDF output using conversion options for layout and fidelity. This is the main entry point for Word/Excel/PowerPoint-to-PDF workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            tagged_pdf: For Office conversion, toggles generation of tagged PDFs for accessibility workflows.
            locale: Locale used by locale-aware conversion options.
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_margin: Page margin setting (for example `8mm` or `0.5in`) for HTML/URL rendering outputs.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            web_layout: Rendering viewport profile (`desktop`, `tablet`, or `mobile`) for HTML/URL conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
            "compression": compression,
            "downsample": downsample,
            "tagged_pdf": tagged_pdf,
            "locale": locale,
            "page_size": page_size,
            "page_margin": page_margin,
            "page_orientation": page_orientation,
            "web_layout": web_layout,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertOfficeToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_postscript_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_postscript_to_pdf][pdfrest.PdfRestClient.convert_postscript_to_pdf].

        Converts PostScript content to PDF while preserving page content for modern PDF workflows. Use this when ingesting legacy print-oriented document formats.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
            "compression": compression,
            "downsample": downsample,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertPostscriptToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_email_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_email_to_pdf][pdfrest.PdfRestClient.convert_email_to_pdf].

        Converts email message files into PDF, including rendered message content and supported metadata/body parts. This supports archiving and compliance workflows.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertEmailToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_image_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_image_to_pdf][pdfrest.PdfRestClient.convert_image_to_pdf].

        Converts one or more image files into PDF output and can combine them into multipage documents. Use this to normalize scanned/image assets into PDF containers.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertImageToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_html_to_pdf(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample = 300,
        page_size: HtmlPageSize = "letter",
        page_margin: str = "1.0in",
        page_orientation: HtmlPageOrientation = "portrait",
        web_layout: HtmlWebLayout = "desktop",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_html_to_pdf][pdfrest.PdfRestClient.convert_html_to_pdf].

        Renders HTML content into PDF with page-size/orientation/layout and related rendering controls. This supports report generation and web-to-PDF publishing use cases.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_margin: Page margin setting (for example `8mm` or `0.5in`) for HTML/URL rendering outputs.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            web_layout: Rendering viewport profile (`desktop`, `tablet`, or `mobile`) for HTML/URL conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output": output,
            "compression": compression,
            "downsample": downsample,
            "page_size": page_size,
            "page_margin": page_margin,
            "page_orientation": page_orientation,
            "web_layout": web_layout,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertHtmlToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_url_to_pdf(
        self,
        url: UrlValue,
        *,
        output: str | None = None,
        compression: PdfConversionCompression = "lossy",
        downsample: PdfConversionDownsample = 300,
        page_size: HtmlPageSize = "letter",
        page_margin: str = "1.0in",
        page_orientation: HtmlPageOrientation = "portrait",
        web_layout: HtmlWebLayout = "desktop",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_url_to_pdf][pdfrest.PdfRestClient.convert_url_to_pdf].

        Fetches remote web content by URL and renders it to PDF using HTML rendering options. Use this for automated webpage capture and archival.

        Args:
            url: Remote URL to ingest and convert.
            output: Output filename prefix used by pdfRest when creating files.
            compression: Compression mode used during conversion.
            downsample: Image downsampling setting for conversion.
            page_size: Target page size preset or custom size settings used for output page dimensions.
            page_margin: Page margin setting (for example `8mm` or `0.5in`) for HTML/URL rendering outputs.
            page_orientation: Page orientation for standard page sizes (portrait or landscape).
            web_layout: Rendering viewport profile (`desktop`, `tablet`, or `mobile`) for HTML/URL conversion.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "url": url,
            "output": output,
            "compression": compression,
            "downsample": downsample,
            "page_size": page_size,
            "page_margin": page_margin,
            "page_orientation": page_orientation,
            "web_layout": web_layout,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/pdf",
            payload=payload,
            payload_model=ConvertUrlToPdfPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def watermark_pdf_with_text(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        watermark_text: str,
        output: str | None = None,
        font: str | None = None,
        text_size: int = 72,
        text_color: PdfTextColor = (0, 0, 0),
        opacity: float = 0.5,
        horizontal_alignment: WatermarkHorizontalAlignment = "center",
        vertical_alignment: WatermarkVerticalAlignment = "center",
        x: int = 0,
        y: int = 0,
        rotation: int = 0,
        pages: PdfPageSelection | None = None,
        behind_page: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.watermark_pdf_with_text][pdfrest.PdfRestClient.watermark_pdf_with_text].

        Applies text watermarks with control over placement, rotation, color, opacity, and alignment. Use this for confidentiality marks, drafts, and document branding.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            watermark_text: Text content to render as the watermark.
            output: Output filename prefix used by pdfRest when creating files.
            font: Font family name for rendered text.
            text_size: Watermark text size in points.
            text_color: Watermark text color as RGB or CMYK channel values.
            opacity: Opacity in range 0.0 to 1.0.
            horizontal_alignment: Horizontal alignment anchor used when placing watermark content.
            vertical_alignment: Vertical alignment anchor used when placing watermark content.
            x: Horizontal position in PDF points.
            y: Vertical position in PDF points.
            rotation: Rotation angle in degrees.
            pages: Page selection to constrain processing to specific pages.
            behind_page: Target page number (or selector) where inserted content should be applied.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "watermark_text": watermark_text,
            "output": output,
            "font": font,
            "text_size": text_size,
            "text_color": text_color,
            "opacity": opacity,
            "horizontal_alignment": horizontal_alignment,
            "vertical_alignment": vertical_alignment,
            "x": x,
            "y": y,
            "rotation": rotation,
            "pages": pages,
            "behind_page": behind_page,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/watermarked-pdf",
            payload=payload,
            payload_model=PdfTextWatermarkPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def watermark_pdf_with_image(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        watermark_file: PdfRestFile | Sequence[PdfRestFile],
        output: str | None = None,
        watermark_file_scale: float = 0.5,
        opacity: float = 0.5,
        horizontal_alignment: WatermarkHorizontalAlignment = "center",
        vertical_alignment: WatermarkVerticalAlignment = "center",
        x: int = 0,
        y: int = 0,
        rotation: int = 0,
        pages: PdfPageSelection | None = None,
        behind_page: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.watermark_pdf_with_image][pdfrest.PdfRestClient.watermark_pdf_with_image].

        Applies image watermarks (for example logos/seals) with placement and opacity controls. This is useful for branded overlays and visual ownership marks.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            watermark_file: Uploaded image used as watermark content.
            output: Output filename prefix used by pdfRest when creating files.
            watermark_file_scale: Scale multiplier applied to the watermark file graphic before placement.
            opacity: Opacity in range 0.0 to 1.0.
            horizontal_alignment: Horizontal alignment anchor used when placing watermark content.
            vertical_alignment: Vertical alignment anchor used when placing watermark content.
            x: Horizontal position in PDF points.
            y: Vertical position in PDF points.
            rotation: Rotation angle in degrees.
            pages: Page selection to constrain processing to specific pages.
            behind_page: Target page number (or selector) where inserted content should be applied.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "watermark_file": watermark_file,
            "output": output,
            "watermark_file_scale": watermark_file_scale,
            "opacity": opacity,
            "horizontal_alignment": horizontal_alignment,
            "vertical_alignment": vertical_alignment,
            "x": x,
            "y": y,
            "rotation": rotation,
            "pages": pages,
            "behind_page": behind_page,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        return await self._post_file_operation(
            endpoint="/watermarked-pdf",
            payload=payload,
            payload_model=PdfImageWatermarkPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_pdfa(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_type: PdfAOutputType,
        output: str | None = None,
        rasterize_if_errors_encountered: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_pdfa][pdfrest.PdfRestClient.convert_to_pdfa].

        Converts input PDFs to selected PDF/A conformance levels for long-term archival compatibility. Choose the target conformance profile that matches your compliance requirements.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_type: Output mode for endpoints supporting inline or file output.
            output: Output filename prefix used by pdfRest when creating files.
            rasterize_if_errors_encountered: When enabled, allows rasterized fallback if strict conformance conversion encounters nonconforming content.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": file,
            "output_type": output_type,
            "rasterize_if_errors_encountered": rasterize_if_errors_encountered,
        }
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdfa",
            payload=payload,
            payload_model=PdfToPdfaPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_pdfx(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_type: PdfXType,
        output: str | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_pdfx][pdfrest.PdfRestClient.convert_to_pdfx].

        Converts input PDFs to selected PDF/X conformance levels for print-production workflows. Use this when downstream print tooling expects standardized PDF/X output.

        Args:
            file: Uploaded input file or files as `PdfRestFile` objects.
            output_type: Output mode for endpoints supporting inline or file output.
            output: Output filename prefix used by pdfRest when creating files.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {"files": file, "output_type": output_type}
        if output is not None:
            payload["output"] = output

        return await self._post_file_operation(
            endpoint="/pdfx",
            payload=payload,
            payload_model=PdfToPdfxPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_png(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: PngColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_png][pdfrest.PdfRestClient.convert_to_png].

        Converts PDF pages to PNG images with configurable color model, smoothing, and page selection controls. Suitable for high-fidelity raster exports and previews.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return await self._convert_to_graphic(
            endpoint="/png",
            payload=payload,
            payload_model=PngPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_bmp(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: BmpColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_bmp][pdfrest.PdfRestClient.convert_to_bmp].

        Converts PDF pages to BMP images with configurable color model and page selection. Use this for legacy bitmap workflows that require BMP output.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return await self._convert_to_graphic(
            endpoint="/bmp",
            payload=payload,
            payload_model=BmpPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_gif(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: GifColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_gif][pdfrest.PdfRestClient.convert_to_gif].

        Converts PDF pages to GIF images with configurable color model and page selection. Useful for lightweight graphics workflows and compatibility scenarios.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return await self._convert_to_graphic(
            endpoint="/gif",
            payload=payload,
            payload_model=GifPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_jpeg(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: JpegColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        jpeg_quality: int = 75,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_jpeg][pdfrest.PdfRestClient.convert_to_jpeg].

        Converts PDF pages to JPEG images with configurable color model and page selection. Use this for compressed photo-friendly page exports.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            jpeg_quality: JPEG quality setting (1-100) controlling compression level and output fidelity.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
            "jpeg_quality": jpeg_quality,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return await self._convert_to_graphic(
            endpoint="/jpg",
            payload=payload,
            payload_model=JpegPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )

    async def convert_to_tiff(
        self,
        files: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_prefix: str | None = None,
        page_range: str | Sequence[str] | None = None,
        resolution: int = 300,
        color_model: TiffColorModel = "rgb",
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] = "none",
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronous variant of [PdfRestClient.convert_to_tiff][pdfrest.PdfRestClient.convert_to_tiff].

        Converts PDF pages to TIFF images with configurable color model and page selection. This is commonly used in archival, scanning, and print-imaging pipelines.

        Args:
            files: Uploaded input file or files as `PdfRestFile` objects.
            output_prefix: Filename prefix used for generated per-page/per-file image outputs.
            page_range: Page selection string/list for image conversion outputs.
            resolution: Raster output resolution in DPI for generated image files.
            color_model: Output image color model.
            smoothing: Graphic smoothing mode for image output endpoints.
            extra_query: Additional query parameters merged into the request.
            extra_headers: Additional HTTP headers merged into the request.
            extra_body: Additional request body fields merged into the payload.
            timeout: Request timeout override for this call.

        Returns:
            Validated file-based response returned by pdfRest.

        Raises:
            PdfRestError: If request execution fails at the client or API layer.
            ValidationError: If local payload validation fails before sending.
        """
        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "smoothing": smoothing,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range

        return await self._convert_to_graphic(
            endpoint="/tif",
            payload=payload,
            payload_model=TiffPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
