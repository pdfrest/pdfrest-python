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
    ConvertToMarkdownPayload,
    DeletePayload,
    ExtractImagesPayload,
    ExtractTextPayload,
    GifPdfRestPayload,
    JpegPdfRestPayload,
    OcrPdfPayload,
    PdfCompressPayload,
    PdfFlattenAnnotationsPayload,
    PdfFlattenFormsPayload,
    PdfFlattenTransparenciesPayload,
    PdfInfoPayload,
    PdfLinearizePayload,
    PdfMergePayload,
    PdfRasterizePayload,
    PdfRedactionApplyPayload,
    PdfRedactionPreviewPayload,
    PdfRestRawFileResponse,
    PdfSplitPayload,
    PdfToExcelPayload,
    PdfToPdfaPayload,
    PdfToPdfxPayload,
    PdfToPowerpointPayload,
    PdfToWordPayload,
    PdfXfaToAcroformsPayload,
    PngPdfRestPayload,
    SummarizePdfTextPayload,
    TiffPdfRestPayload,
    TranslatePdfTextPayload,
    UploadURLs,
)
from .types import (
    ALL_PDF_INFO_QUERIES,
    BmpColorModel,
    CompressionLevel,
    ExtractTextGranularity,
    FlattenQuality,
    GifColorModel,
    GraphicSmoothing,
    JpegColorModel,
    OcrLanguage,
    PdfAType,
    PdfInfoQuery,
    PdfMergeInput,
    PdfPageSelection,
    PdfRedactionInstruction,
    PdfRGBColor,
    PdfXType,
    PngColorModel,
    SummaryFormat,
    SummaryOutputFormat,
    TiffColorModel,
    TranslateOutputFormat,
)

__all__ = ("AsyncPdfRestClient", "PdfRestClient")
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
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(
                    "Response %s status=%s", request_label, response.status_code
                )
            return self._decode_json(response)

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
        payload = self._send_request(request)
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
        payload = await self._send_request(request)
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
        """Create a synchronous pdfRest client."""

        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            headers=headers,
            http_client=http_client,
            transport=transport,
            max_retries=max_retries,
        )
        self._files_client = _FilesClient(self)

    @override
    def __enter__(self) -> PdfRestClient:
        _ = super().__enter__()
        return self

    @override
    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        super().__exit__(exc_type, exc, traceback)

    @property
    def files(self) -> _FilesClient:
        return self._files_client

    def up(
        self,
        *,
        extra_headers: AnyMapping | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> UpResponse:
        """Call the `/up` health endpoint and return server metadata."""

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
        """Query pdfRest for metadata describing a PDF document."""

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

        Always requests JSON output and returns the inline summary response defined in
        the pdfRest API reference.
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
        """Summarize a document and return the result as a downloadable file."""

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
        """Convert a PDF to Markdown and return a file-based response."""

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
        """Perform OCR on a PDF to make text searchable and extractable."""

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
        """Translate the textual content of a PDF, Markdown, or text document (JSON)."""

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
        """Translate textual content and receive a file-based response."""

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
        """Extract embedded images from a PDF."""

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
        """Extract text content from a PDF and return a file-based response."""

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
        """Generate a PDF redaction preview with annotated redaction rectangles."""

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
        """Apply previously previewed redactions and return the final redacted PDF."""

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
        """Split a PDF into one or more PDF files based on the provided page groups."""

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
        """Merge multiple PDFs (or page subsets) into a single PDF file."""

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
        """Convert a PDF to an Excel spreadsheet."""

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
        """Convert a PDF to a PowerPoint presentation."""

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
        """Convert an XFA PDF to an AcroForm-enabled PDF."""

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
        """Convert a PDF to a Word document."""

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
        """Flatten form fields in a PDF so they are no longer editable."""

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
        """Compress a PDF using preset or custom compression profiles."""

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
        """Flatten transparent objects in a PDF."""

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
        """Linearize a PDF for optimized fast web view."""

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
        """Flatten annotations into the PDF content."""

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
        """Rasterize a PDF into a flattened bitmap-based PDF."""

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

    def convert_to_pdfa(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_type: PdfAType,
        output: str | None = None,
        rasterize_if_errors_encountered: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert a PDF to a specified PDF/A version."""

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
        """Convert a PDF to a specified PDF/X version."""

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to PNG images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to BMP images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to GIF images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        jpeg_quality: int = 75,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to JPEG images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "jpeg_quality": jpeg_quality,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Convert one or more pdfRest files to TIFF images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        """Create an asynchronous pdfRest client."""

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
        self._files_client = _AsyncFilesClient(self)

    @override
    async def __aenter__(self) -> AsyncPdfRestClient:
        _ = await super().__aenter__()
        return self

    @override
    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await super().__aexit__(exc_type, exc, traceback)

    @property
    def files(self) -> _AsyncFilesClient:
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
        """Query pdfRest for metadata describing a PDF document asynchronously."""

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
        """Summarize the textual content of a PDF, Markdown, or text document.

        Always requests JSON output and returns the inline summary response defined in
        the pdfRest API reference.
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
        """Summarize a document and return the result as a downloadable file."""

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
        """Convert a PDF to Markdown and return a file-based response."""

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
        """Perform OCR on a PDF to make text searchable and extractable."""

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
        """Translate the textual content of a PDF, Markdown, or text document (JSON)."""

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
        """Translate textual content and receive a file-based response."""

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
        """Extract embedded images from a PDF."""

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
        """Extract text content from a PDF and return a file-based response."""

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
        """Asynchronously generate a PDF redaction preview."""

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
        """Asynchronously apply PDF redactions."""

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

    async def up(
        self,
        *,
        extra_headers: AnyMapping | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> UpResponse:
        """Call the `/up` health endpoint asynchronously and return server metadata."""

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
        """Asynchronously split a PDF into one or more PDF files."""

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
        """Asynchronously merge multiple PDFs (or page subsets) into a single PDF."""

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
        """Asynchronously convert a PDF to an Excel spreadsheet."""

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
        """Asynchronously convert a PDF to a PowerPoint presentation."""

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
        """Asynchronously convert an XFA PDF to an AcroForm-enabled PDF."""

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
        """Asynchronously convert a PDF to a Word document."""

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
        """Asynchronously flatten form fields in a PDF."""

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
        """Asynchronously compress a PDF."""

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
        """Asynchronously flatten transparent objects in a PDF."""

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
        """Asynchronously linearize a PDF for optimized fast web view."""

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
        """Asynchronously flatten annotations into the PDF content."""

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
        """Asynchronously rasterize a PDF into a flattened bitmap-based PDF."""

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

    async def convert_to_pdfa(
        self,
        file: PdfRestFile | Sequence[PdfRestFile],
        *,
        output_type: PdfAType,
        output: str | None = None,
        rasterize_if_errors_encountered: bool = False,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronously convert a PDF to a specified PDF/A version."""

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
        """Asynchronously convert a PDF to a specified PDF/X version."""

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronously convert one or more pdfRest files to PNG images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronously convert one or more pdfRest files to BMP images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronously convert one or more pdfRest files to GIF images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        jpeg_quality: int = 75,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronously convert one or more pdfRest files to JPEG images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
            "jpeg_quality": jpeg_quality,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

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
        smoothing: GraphicSmoothing | Sequence[GraphicSmoothing] | None = None,
        extra_query: Query | None = None,
        extra_headers: AnyMapping | None = None,
        extra_body: Body | None = None,
        timeout: TimeoutTypes | None = None,
    ) -> PdfRestFileBasedResponse:
        """Asynchronously convert one or more pdfRest files to TIFF images."""

        payload: dict[str, Any] = {
            "files": files,
            "resolution": resolution,
            "color_model": color_model,
        }
        if output_prefix is not None:
            payload["output_prefix"] = output_prefix
        if page_range is not None:
            payload["page_range"] = page_range
        if smoothing is not None:
            payload["smoothing"] = smoothing

        return await self._convert_to_graphic(
            endpoint="/tif",
            payload=payload,
            payload_model=TiffPdfRestPayload,
            extra_query=extra_query,
            extra_headers=extra_headers,
            extra_body=extra_body,
            timeout=timeout,
        )
