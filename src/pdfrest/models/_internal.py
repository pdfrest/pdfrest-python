from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import PurePath
from typing import Annotated, Any, Generic, Literal, TypeVar

from langcodes import tag_is_valid
from pydantic import (
    AfterValidator,
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    PlainSerializer,
    model_serializer,
    model_validator,
)
from pydantic_core import to_json

from pdfrest.types.public import PdfRedactionPreset

from ..types import (
    OcrLanguage,
    PdfAType,
    PdfInfoQuery,
    PdfRestriction,
    PdfXType,
    SummaryFormat,
    SummaryOutputFormat,
    SummaryOutputType,
    TranslateOutputFormat,
)
from .public import PdfRestFile, PdfRestFileID


def _ensure_list(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return value  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return [value]


def _list_of_strings(value: list[Any]) -> list[str]:
    return [str(e) for e in value]


def _validate_output_prefix(value: str | None) -> str | None:
    """Validate output prefix to prevent directory traversal and reserved or unsafe names."""
    if value is None:
        return None
    if "/" in value or "\\" in value or ":" in value:
        msg = "The output prefix must not contain a directory separator."
        raise ValueError(msg)
    if value.startswith("."):
        msg = "The output prefix must not start with a `.`."
        raise ValueError(msg)
    if ".." in value:
        msg = "The output prefix must not contain `..`."
        raise ValueError(msg)
    basename = PurePath(value).name
    if value != basename:
        msg = "The output prefix must not include directory components."
        raise ValueError(msg)
    if basename in {"profile.json", "metadata.json"}:
        msg = "The output prefix is a reserved name."
        raise ValueError(msg)
    special_chars_pattern = r"[`!@#$%^&*()+=\[\]{};':\"\\|,<>?~]"
    matches = re.findall(special_chars_pattern, value)
    if matches:
        violations: list[str] = []
        for char in matches:
            if char not in violations:
                violations.append(char)
        msg = (
            "The output prefix must not contain special characters: "
            + ", ".join(repr(char) for char in violations)
            + "."
        )
        raise ValueError(msg)
    return value


def _split_comma_list(value: Any) -> Any:
    if isinstance(value, str):
        return value.split(",")
    if isinstance(value, list):
        return value  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    msg = "Must be a comma separated string or a list of strings."
    raise ValueError(msg)


def _split_comma_string(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.split(",")
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    msg = "Must be a list, or a comma separated string."
    raise ValueError(msg)


def _serialize_as_first_file_id(value: list[PdfRestFile]) -> str:
    return str(value[0].id)


def _serialize_as_comma_separated_string(value: list[Any] | None) -> str | None:
    if value is None:
        return None
    return ",".join(str(element) for element in value)


def _serialize_file_ids(value: list[PdfRestFile]) -> str:
    return ",".join(str(file.id) for file in value)


def _bool_to_on_off(value: Any) -> Any:
    if isinstance(value, bool):
        return "on" if value else "off"
    return value


def _serialize_page_ranges(value: list[str | int | tuple[str | int, ...]]) -> str:
    def join_tuple(value: str | int | tuple[str | int, ...]) -> str:
        if isinstance(value, tuple):
            return "-".join(str(e) for e in value)
        return str(value)

    return ",".join(join_tuple(v) for v in value)


def _serialize_grouped_page_ranges(
    value: list[list[str | int | tuple[str | int, ...]]],
) -> list[str]:
    return [_serialize_page_ranges(v) for v in value]


def _serialize_redactions(value: list[_PdfRedactionVariant]) -> str:
    return (
        "["
        + ",".join(entry.model_dump_json(exclude_none=True) for entry in value)
        + "]"
    )


def _serialize_text_object_value(value: Any) -> Any:
    if isinstance(value, str):
        return value
    return to_json(value).decode()


def _serialize_text_objects(value: list[BaseModel]) -> str:
    payload = [
        {
            key: _serialize_text_object_value(field_value)
            for key, field_value in entry.model_dump(
                mode="json", exclude_none=True
            ).items()
        }
        for entry in value
    ]
    return to_json(payload).decode()


def _serialize_signature_configuration(
    value: _PdfSignatureConfigurationModel,
) -> str:
    payload = value.model_dump(mode="json", exclude_none=True)
    return to_json(payload).decode()


def _allowed_mime_types(
    allowed_mime_types: str, *more_allowed_mime_types: str, error_msg: str | None
) -> Callable[[Any], Any]:
    combined_allowed_mime_types = [allowed_mime_types, *more_allowed_mime_types]

    def allowed_mime_types_validator(
        value: PdfRestFile | list[PdfRestFile],
    ) -> PdfRestFile | list[PdfRestFile]:
        if isinstance(value, list):
            for item in value:
                _ = allowed_mime_types_validator(item)
            return value
        if value.type not in combined_allowed_mime_types:
            msg = error_msg or f"The file type must be one of: {allowed_mime_types}"
            raise ValueError(msg)
        return value

    return allowed_mime_types_validator


def _int_to_string(value: Any) -> Any:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return [_int_to_string(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


_OUTPUT_LANGUAGE_ERROR = (
    "The provided 'output_language' language tag is invalid. Format 'output_language' as "
    "a valid 2-3 character ISO 639 language code (e.g., 'en', 'es', 'fra'), optionally "
    "with a script, alphabetic region, or numeric region (e.g., 'zh-Hant', 'eng-US', "
    "'es-419'). See documentation for recommended formats."
)


def _validate_output_language(value: str) -> str:
    if not value:
        raise ValueError(_OUTPUT_LANGUAGE_ERROR)

    trimmed = value.strip()
    if not trimmed:
        raise ValueError(_OUTPUT_LANGUAGE_ERROR)

    segments = trimmed.split("-")
    if len(segments) > 2:
        raise ValueError(_OUTPUT_LANGUAGE_ERROR)

    language = segments[0]
    if not re.fullmatch(r"[A-Za-z]{2,3}", language):
        raise ValueError(_OUTPUT_LANGUAGE_ERROR)

    if len(segments) == 2:
        subtag = segments[1]
        if not (
            re.fullmatch(r"[A-Za-z]{4}", subtag)
            or re.fullmatch(r"[A-Za-z]{2}", subtag)
            or re.fullmatch(r"[0-9]{3}", subtag)
        ):
            raise ValueError(_OUTPUT_LANGUAGE_ERROR)

    if not tag_is_valid(trimmed):
        raise ValueError(_OUTPUT_LANGUAGE_ERROR)

    return trimmed


class UploadURLs(BaseModel):
    url: Annotated[
        list[HttpUrl] | HttpUrl,
        Field(min_length=1),
        BeforeValidator(_list_of_strings),
        BeforeValidator(_ensure_list),
    ]


class DeletePayload(BaseModel):
    """Adapt caller options into a pdfRest-ready delete request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="ids",
        ),
        BeforeValidator(_ensure_list),
        PlainSerializer(_serialize_file_ids),
    ]


PageNumber = Annotated[int, Field(ge=1), PlainSerializer(lambda x: str(x))]


def _split_page_range_tuple(x: str) -> tuple[str, str]:
    start, end = x.split("-", maxsplit=1)
    return start, end


def _ascending_page_range(
    range: tuple[int, int | Literal["last"]],
) -> tuple[int, int | Literal["last"]]:
    start, end = range
    if end != "last" and int(start) > int(end):
        msg = "The start page must be less than or equal to the end page."
        raise ValueError(msg)
    return range


_PageRangeTupleWithLast = Annotated[
    tuple[PageNumber, PageNumber]
    | tuple[Literal["last"], PageNumber]
    | tuple[PageNumber, Literal["last"]],
    BeforeValidator(_split_page_range_tuple),
]

SplitMergePageRange = (
    Literal["even", "odd", "last"] | PageNumber | _PageRangeTupleWithLast
)

_AscendingPageRangeTuple = Annotated[
    tuple[PageNumber, PageNumber] | tuple[PageNumber, Literal["last"]],
    BeforeValidator(_split_page_range_tuple),
    AfterValidator(_ascending_page_range),
]

AscendingPageRange = PageNumber | Literal["last"] | _AscendingPageRangeTuple


class PdfInfoPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready pdf-info request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    queries: Annotated[
        list[PdfInfoQuery],
        Field(min_length=1),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        PlainSerializer(_serialize_as_comma_separated_string),
    ]


class SummarizePdfTextPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready summarize request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types(
                "application/pdf",
                "text/markdown",
                "text/plain",
                error_msg="Must be a PDF, Markdown, or plain text file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    target_word_count: Annotated[
        int | None, Field(serialization_alias="target_word_count", ge=1, default=400)
    ] = 400
    summary_format: Annotated[
        SummaryFormat, Field(serialization_alias="summary_format", default="overview")
    ] = "overview"
    pages: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ] = None
    output_format: Annotated[
        SummaryOutputFormat,
        Field(serialization_alias="output_format", default="markdown"),
    ] = "markdown"
    output_type: Annotated[
        SummaryOutputType, Field(serialization_alias="output_type", default="json")
    ] = "json"
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class OcrPdfPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready OCR request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    languages: Annotated[
        list[OcrLanguage],
        Field(
            serialization_alias="languages",
            validation_alias=AliasChoices("languages", "language"),
            min_length=1,
            default_factory=lambda: ["English"],
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        PlainSerializer(_serialize_as_comma_separated_string),
    ]
    pages: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class ExtractTextPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready extract text request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    pages: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ] = None
    full_text: Literal["off", "by_page", "document"] = "document"
    preserve_line_breaks: Annotated[
        Literal["off", "on"], BeforeValidator(_bool_to_on_off)
    ] = "off"
    word_style: Annotated[Literal["off", "on"], BeforeValidator(_bool_to_on_off)] = (
        "off"
    )
    word_coordinates: Annotated[
        Literal["off", "on"], BeforeValidator(_bool_to_on_off)
    ] = "off"
    output_type: Literal["json", "file"] = "json"
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class ConvertToMarkdownPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready markdown conversion payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    pages: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ] = None
    output_type: Annotated[
        SummaryOutputType, Field(serialization_alias="output_type", default="json")
    ] = "json"
    page_break_comments: Annotated[
        Literal["on", "off"] | None,
        Field(serialization_alias="page_break_comments", default=None),
        BeforeValidator(_bool_to_on_off),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class TranslatePdfTextPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready translate request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types(
                "application/pdf",
                "text/markdown",
                "text/plain",
                error_msg="Must be a PDF, Markdown, or plain text file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output_language: Annotated[
        str,
        Field(serialization_alias="output_language"),
        AfterValidator(_validate_output_language),
    ]
    pages: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ] = None
    output_format: Annotated[
        TranslateOutputFormat,
        Field(serialization_alias="output_format", default="markdown"),
    ] = "markdown"
    output_type: Annotated[
        Literal["json", "file"],
        Field(serialization_alias="output_type", default="json"),
    ] = "json"
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class ExtractImagesPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready extract images request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    pages: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


RgbChannel = Annotated[int, Field(ge=0, le=255)]
CmykChannel = Annotated[int, Field(ge=0, le=100)]


class PdfLiteralRedactionModel(BaseModel):
    type: Literal["literal"]
    value: Annotated[str, Field(min_length=1)]


class PdfRegexRedactionModel(BaseModel):
    type: Literal["regex"]
    value: Annotated[str, Field(min_length=1)]


class PdfPresetRedactionModel(BaseModel):
    type: Literal["preset"]
    value: PdfRedactionPreset


class _PdfSignaturePointModel(BaseModel):
    x: str | int | float
    y: str | int | float


class _PdfSignatureLocationModel(BaseModel):
    bottom_left: _PdfSignaturePointModel
    top_right: _PdfSignaturePointModel
    page: str | int


class _PdfSignatureDisplayModel(BaseModel):
    include_distinguished_name: bool | None = None
    include_datetime: bool | None = None
    contact: str | None = None
    location: str | None = None
    name: str | None = None
    reason: str | None = None


class _PdfSignatureConfigurationModel(BaseModel):
    type: Literal["new"]
    name: str | None = None
    logo_opacity: Annotated[float | None, Field(ge=0, le=1, default=None)] = None
    location: _PdfSignatureLocationModel | None = None
    display: _PdfSignatureDisplayModel | None = None


_PdfRedactionVariant = Annotated[
    PdfLiteralRedactionModel | PdfRegexRedactionModel | PdfPresetRedactionModel,
    Field(discriminator="type"),
]


class PdfRedactionPreviewPayload(BaseModel):
    """Adapt caller options into a pdfRest-compatible redaction preview request."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    redactions: Annotated[
        list[_PdfRedactionVariant],
        Field(min_length=1),
        BeforeValidator(_ensure_list),
        PlainSerializer(_serialize_redactions),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfRedactionApplyPayload(BaseModel):
    """Adapt caller options into a pdfRest-compatible redaction application request."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    rgb_color: Annotated[
        tuple[RgbChannel, RgbChannel, RgbChannel] | None,
        Field(serialization_alias="rgb_color", default=None),
        BeforeValidator(_split_comma_string),
        PlainSerializer(_serialize_as_comma_separated_string),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


ColorModelT = TypeVar("ColorModelT", bound=str)


class BasePdfRestGraphicPayload(BaseModel, Generic[ColorModelT]):
    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        BeforeValidator(_ensure_list),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output_prefix: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ]
    page_range: Annotated[
        list[AscendingPageRange] | None,
        Field(serialization_alias="pages", min_length=1, default=None),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_page_ranges),
    ]
    resolution: Annotated[int, Field(ge=12, le=2400, default=300)]
    color_model: Annotated[ColorModelT, Field(default=...)]
    smoothing: Annotated[
        list[Literal["none", "all", "text", "line", "image"]],
        Field(default="none"),
        BeforeValidator(_ensure_list),
        BeforeValidator(_split_comma_list),
        PlainSerializer(_serialize_as_comma_separated_string),
    ]


class PngPdfRestPayload(BasePdfRestGraphicPayload[Literal["rgb", "rgba", "gray"]]):
    """Adapt caller options into a pdfRest-ready PNG request payload."""

    color_model: Annotated[Literal["rgb", "rgba", "gray"], Field(default="rgb")]


_DEFAULT_FULL_DOCUMENT_RANGE: list[str] = ["1-last"]


class PdfSplitPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready split request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    page_groups: Annotated[
        list[
            Annotated[
                list[SplitMergePageRange],
                BeforeValidator(_ensure_list),
                BeforeValidator(_split_comma_string),
            ]
        ]
        | None,
        Field(
            default=None,
            validation_alias=AliasChoices("pages", "page_groups"),
            serialization_alias="pages",
            min_length=1,
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(_int_to_string),
        PlainSerializer(_serialize_grouped_page_ranges),
    ]
    output_prefix: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class _PdfMergeItem(BaseModel):
    file: Annotated[
        PdfRestFile,
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
    ]
    pages: Annotated[
        list[SplitMergePageRange],
        Field(
            min_length=1,
            default_factory=lambda: list(_DEFAULT_FULL_DOCUMENT_RANGE).copy(),
        ),
        BeforeValidator(_list_of_strings),
        BeforeValidator(_ensure_list),
        PlainSerializer(_serialize_page_ranges),
    ]

    @model_validator(mode="before")
    @classmethod
    def _transform_input(cls, data: Any) -> Any:
        if isinstance(data, tuple):
            if len(data) != 2:  # pyright: ignore[reportUnknownArgumentType]
                msg = (
                    "Tuple merge entries must contain exactly two items: (file, pages)."
                )
                raise ValueError(msg)
            file_candidate, pages = data  # pyright: ignore[reportUnknownVariableType]
            return {"file": file_candidate, "pages": pages}  # pyright: ignore[reportUnknownVariableType]
        if isinstance(data, PdfRestFile):
            return {"file": data}
        return data


class PdfMergePayload(BaseModel):
    """Adapt caller options into a pdfRest-ready merge request payload."""

    sources: Annotated[
        list[_PdfMergeItem],
        Field(
            min_length=2,
            validation_alias=AliasChoices("sources", "documents", "files"),
        ),
        BeforeValidator(_ensure_list),
    ]
    output_prefix: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None

    @model_serializer(mode="wrap")
    def _serialize_pdf_merge_payload(
        self, handler: Callable[[PdfMergePayload], dict[str, Any]]
    ) -> dict[str, Any]:
        # Invoke all the serializers on the payload, which then properly serializes
        # all the fields.
        payload = handler(self)
        # Reorganize the serialized data into the parallel arrays that pdfRest expects
        payload["type"] = ["id"] * len(self.sources)
        payload["pages"] = [
            source.get("pages", _DEFAULT_FULL_DOCUMENT_RANGE[0])
            for source in payload["sources"]
        ]
        payload["id"] = [source["file"]["id"] for source in payload["sources"]]
        del payload["sources"]
        return payload


class PdfToWordPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready Word request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfToExcelPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready Excel request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfToPowerpointPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready PowerPoint request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfToPdfaPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready PDF/A request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output_type: Annotated[PdfAType, Field(serialization_alias="output_type")]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None
    rasterize_if_errors_encountered: Annotated[
        Literal["on", "off"] | None,
        Field(
            serialization_alias="rasterize_if_errors_encountered",
            default=None,
        ),
        BeforeValidator(_bool_to_on_off),
    ] = None


class PdfToPdfxPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready PDF/X request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output_type: Annotated[PdfXType, Field(serialization_alias="output_type")]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfFlattenFormsPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready flatten-forms request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfSignPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready sign request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    signature_configuration: Annotated[
        _PdfSignatureConfigurationModel,
        Field(serialization_alias="signature_configuration"),
        PlainSerializer(_serialize_signature_configuration),
    ]
    pfx_credential: Annotated[
        list[PdfRestFile] | None,
        Field(
            default=None,
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("pfx", "pfx_credential"),
            serialization_alias="pfx_credential_id",
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(
            _allowed_mime_types(
                "application/x-pkcs12",
                "application/pkcs12",
                "application/octet-stream",
                error_msg="PFX credentials must be a .pfx or .p12 file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ] = None
    pfx_passphrase: Annotated[
        list[PdfRestFile] | None,
        Field(
            default=None,
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("pfx_passphrase", "passphrase"),
            serialization_alias="pfx_passphrase_id",
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(
            _allowed_mime_types(
                "text/plain",
                "application/octet-stream",
                error_msg="PFX passphrase must be a text file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ] = None
    certificate: Annotated[
        list[PdfRestFile] | None,
        Field(
            default=None,
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("certificate", "cert"),
            serialization_alias="certificate_id",
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(
            _allowed_mime_types(
                "application/pkix-cert",
                "application/x-x509-ca-cert",
                "application/x-pem-file",
                "application/octet-stream",
                error_msg="Certificate must be a .pem or .der file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ] = None
    private_key: Annotated[
        list[PdfRestFile] | None,
        Field(
            default=None,
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("private_key", "key"),
            serialization_alias="private_key_id",
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(
            _allowed_mime_types(
                "application/pkcs8",
                "application/x-pem-file",
                "application/octet-stream",
                error_msg="Private key must be a .pem or .der file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ] = None
    logo: Annotated[
        list[PdfRestFile] | None,
        Field(
            default=None,
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("logo", "logos"),
            serialization_alias="logo_id",
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(
            _allowed_mime_types(
                "image/jpeg",
                "image/png",
                "image/tiff",
                "image/bmp",
                error_msg="Logo must be an image file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None

    @model_validator(mode="after")
    def _validate_credentials(self) -> PdfSignPayload:
        has_pfx = self.pfx_credential is not None or self.pfx_passphrase is not None
        has_pem = self.certificate is not None or self.private_key is not None

        if has_pfx and has_pem:
            msg = "Provide either PFX credentials (pfx + passphrase) or certificate/private_key, not both."
            raise ValueError(msg)
        if has_pfx:
            if not self.pfx_credential or not self.pfx_passphrase:
                msg = "Both pfx and passphrase are required when supplying PFX credentials."
                raise ValueError(msg)
        elif has_pem:
            if not self.certificate or not self.private_key:
                msg = "Both certificate and private_key are required when supplying PEM/DER credentials."
                raise ValueError(msg)
        else:
            msg = "Either PFX credentials (pfx + passphrase) or certificate/private_key credentials are required."
            raise ValueError(msg)

        return self


class PdfCompressPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready compress request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    compression_level: Annotated[
        Literal["low", "medium", "high", "custom"],
        Field(serialization_alias="compression_level"),
    ]
    profile: Annotated[
        list[PdfRestFile] | None,
        Field(
            default=None,
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("profile", "profiles"),
            serialization_alias="profile_id",
        ),
        BeforeValidator(_ensure_list),
        BeforeValidator(
            _allowed_mime_types(
                "application/json",
                "text/json",
                error_msg="Profile must be a JSON file",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None

    @model_validator(mode="after")
    def _validate_profile_dependency(self) -> PdfCompressPayload:
        if self.compression_level == "custom":
            if not self.profile:
                msg = "compression_level 'custom' requires a profile to be provided."
                raise ValueError(msg)
        elif self.profile:
            msg = "A profile can only be provided when compression_level is 'custom'."
            raise ValueError(msg)
        return self


class PdfAddTextObjectModel(BaseModel):
    """Adapt caller text options for insertion into a PDF."""

    font: Annotated[str, Field(min_length=1, serialization_alias="font")]
    max_width: Annotated[
        float,
        Field(serialization_alias="max_width", gt=0),
    ]
    opacity: Annotated[
        float,
        Field(serialization_alias="opacity", ge=0.0, le=1.0),
    ]
    page: Annotated[
        Literal["all"] | Annotated[int, Field(ge=1)],
        Field(serialization_alias="page"),
    ]
    rotation: Annotated[float, Field(serialization_alias="rotation")]
    text: Annotated[str, Field(min_length=1, serialization_alias="text")]
    text_color_rgb: Annotated[
        tuple[RgbChannel, RgbChannel, RgbChannel] | None,
        Field(serialization_alias="text_color_rgb", default=None),
        BeforeValidator(_split_comma_string),
        PlainSerializer(_serialize_as_comma_separated_string),
    ] = None
    text_color_cmyk: Annotated[
        tuple[CmykChannel, CmykChannel, CmykChannel, CmykChannel] | None,
        Field(serialization_alias="text_color_cmyk", default=None),
        BeforeValidator(_split_comma_string),
        PlainSerializer(_serialize_as_comma_separated_string),
    ] = None
    text_size: Annotated[
        float,
        Field(serialization_alias="text_size", ge=5, le=100),
    ]
    x: Annotated[float, Field(serialization_alias="x")]
    y: Annotated[float, Field(serialization_alias="y")]
    is_rtl: Annotated[
        bool | None,
        Field(
            validation_alias=AliasChoices("is_right_to_left", "is_rtl"),
            serialization_alias="is_rtl",
            default=None,
        ),
    ] = None

    @model_validator(mode="after")
    def _ensure_single_color_option(self) -> PdfAddTextObjectModel:
        if self.text_color_rgb is None and self.text_color_cmyk is None:
            msg = "Either text_color_rgb or text_color_cmyk must be provided."
            raise ValueError(msg)
        if self.text_color_rgb is not None and self.text_color_cmyk is not None:
            msg = "Provide only one of text_color_rgb or text_color_cmyk."
            raise ValueError(msg)
        return self


class PdfAddTextPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready add-text request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    text_objects: Annotated[
        list[PdfAddTextObjectModel],
        Field(
            serialization_alias="text_objects",
            min_length=1,
        ),
        BeforeValidator(_ensure_list),
        PlainSerializer(_serialize_text_objects),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfAddImagePayload(BaseModel):
    """Adapt caller options into a pdfRest-ready add-image request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    image: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("image", "images", "image_file", "image_id"),
            serialization_alias="image_id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types(
                "image/jpeg",
                "image/png",
                "image/tiff",
                "image/gif",
                error_msg="Image must be JPEG, PNG, TIFF, or GIF",
            )
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    x: Annotated[int, Field(serialization_alias="x")]
    y: Annotated[int, Field(serialization_alias="y")]
    page: Annotated[int, Field(serialization_alias="page", ge=1)]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfXfaToAcroformsPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready XFA-to-AcroForms request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfLinearizePayload(BaseModel):
    """Adapt caller options into a pdfRest-ready linearize PDF request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfRasterizePayload(BaseModel):
    """Adapt caller options into a pdfRest-ready rasterize PDF request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfFlattenTransparenciesPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready flatten-transparencies request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None
    quality: Literal["low", "medium", "high"] = "medium"


class PdfFlattenAnnotationsPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready flatten-annotations request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfAddAttachmentPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready add-attachment request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    attachments: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices(
                "attachment",
                "attachments",
                "file_to_attach",
                "files_to_attach",
            ),
            serialization_alias="id_to_attach",
        ),
        BeforeValidator(_ensure_list),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfRestrictPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready restrict-PDF request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    new_permissions_password: Annotated[
        str,
        Field(
            serialization_alias="new_permissions_password",
            min_length=6,
            max_length=128,
        ),
    ]
    restrictions: Annotated[
        list[PdfRestriction] | None,
        Field(serialization_alias="restrictions", min_length=1, default=None),
        BeforeValidator(_ensure_list),
    ] = None
    current_permissions_password: Annotated[
        str | None,
        Field(
            serialization_alias="current_permissions_password",
            min_length=1,
            max_length=128,
            default=None,
        ),
    ] = None
    current_open_password: Annotated[
        str | None,
        Field(
            serialization_alias="current_open_password",
            min_length=1,
            max_length=128,
            default=None,
        ),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfUnrestrictPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready unrestrict-PDF request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    current_permissions_password: Annotated[
        str,
        Field(
            serialization_alias="current_permissions_password",
            min_length=1,
            max_length=128,
        ),
    ]
    current_open_password: Annotated[
        str | None,
        Field(
            serialization_alias="current_open_password",
            min_length=1,
            max_length=128,
            default=None,
        ),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfEncryptPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready encrypt-PDF request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    new_open_password: Annotated[
        str,
        Field(
            serialization_alias="new_open_password",
            min_length=6,
            max_length=128,
        ),
    ]
    current_open_password: Annotated[
        str | None,
        Field(
            serialization_alias="current_open_password",
            min_length=1,
            max_length=128,
            default=None,
        ),
    ] = None
    current_permissions_password: Annotated[
        str | None,
        Field(
            serialization_alias="current_permissions_password",
            min_length=1,
            max_length=128,
            default=None,
        ),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class PdfDecryptPayload(BaseModel):
    """Adapt caller options into a pdfRest-ready decrypt-PDF request payload."""

    files: Annotated[
        list[PdfRestFile],
        Field(
            min_length=1,
            max_length=1,
            validation_alias=AliasChoices("file", "files"),
            serialization_alias="id",
        ),
        BeforeValidator(_ensure_list),
        AfterValidator(
            _allowed_mime_types("application/pdf", error_msg="Must be a PDF file")
        ),
        PlainSerializer(_serialize_as_first_file_id),
    ]
    current_open_password: Annotated[
        str,
        Field(
            serialization_alias="current_open_password",
            min_length=1,
            max_length=128,
        ),
    ]
    current_permissions_password: Annotated[
        str | None,
        Field(
            serialization_alias="current_permissions_password",
            min_length=1,
            max_length=128,
            default=None,
        ),
    ] = None
    output: Annotated[
        str | None,
        Field(serialization_alias="output", min_length=1, default=None),
        AfterValidator(_validate_output_prefix),
    ] = None


class BmpPdfRestPayload(BasePdfRestGraphicPayload[Literal["rgb", "gray"]]):
    """Adapt caller options into a pdfRest-ready BMP request payload."""

    color_model: Annotated[Literal["rgb", "gray"], Field(default="rgb")]


class GifPdfRestPayload(BasePdfRestGraphicPayload[Literal["rgb", "gray"]]):
    """Adapt caller options into a pdfRest-ready GIF request payload."""

    color_model: Annotated[Literal["rgb", "gray"], Field(default="rgb")]


class JpegPdfRestPayload(BasePdfRestGraphicPayload[Literal["rgb", "cmyk", "gray"]]):
    """Adapt caller options into a pdfRest-ready JPEG request payload."""

    color_model: Annotated[Literal["rgb", "cmyk", "gray"], Field(default="rgb")]
    jpeg_quality: Annotated[int, Field(ge=1, le=100, default=75)]


class TiffPdfRestPayload(
    BasePdfRestGraphicPayload[Literal["rgb", "rgba", "cmyk", "lab", "gray"]]
):
    """Adapt caller options into a pdfRest-ready TIFF request payload."""

    color_model: Annotated[
        Literal["rgb", "rgba", "cmyk", "lab", "gray"], Field(default="rgb")
    ]


class PdfRestRawUploadedFile(BaseModel):
    """The response sent by /upload is a list of these. /unzip returns files like this
    with outputUrl"""

    name: Annotated[str, Field(description="The name of the file")]
    id: Annotated[PdfRestFileID, Field(description="The id of the file")]
    output_url: Annotated[
        str | None,
        Field(description="The url of the unzipped file", alias="outputUrl"),
        BeforeValidator(_ensure_list),
    ] = None


class PdfRestRawFileResponse(BaseModel):
    """The raw response from file-based pdfRest calls."""

    # Allow all extra fields to be stored and serialized
    # See: https://docs.pydantic.dev/latest/concepts/models/#extra-fields
    model_config = ConfigDict(extra="allow")

    input_id: Annotated[
        list[PdfRestFileID],
        Field(alias="inputId", description="The id of the input file"),
        BeforeValidator(_ensure_list),
    ]
    output_urls: Annotated[
        list[HttpUrl] | None,
        Field(alias="outputUrl", description="The url of the file"),
        BeforeValidator(_ensure_list),
    ] = None
    output_ids: Annotated[
        list[PdfRestFileID] | None,
        Field(alias="outputId", description="The id of the file"),
        BeforeValidator(_ensure_list),
    ] = None
    files: Annotated[
        list[PdfRestRawUploadedFile] | None,
        Field(description="The file(s) returned from the /unzip operation"),
        BeforeValidator(_ensure_list),
    ] = None
    warning: Annotated[
        str | None,
        Field(
            description="A warning that was generated during the pdfRest operation",
        ),
    ] = None

    @property
    def ids(self) -> list[PdfRestFileID] | None:
        if self.output_ids is not None:
            return self.output_ids
        if self.files is not None:
            return [f.id for f in self.files]
        return None
