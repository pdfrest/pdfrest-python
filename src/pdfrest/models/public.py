"""Pydantic models for pdfrest API payloads."""

from __future__ import annotations

import re
import uuid as _uuid
from datetime import date
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    RootModel,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from typing_extensions import override

from ._demo_value_sanitizers import (
    demo_bool_false_or_passthrough,
    demo_bool_true_or_passthrough,
    demo_int_or_passthrough,
)

__all__ = (
    "ExtractTextResponse",
    "ExtractedTextDocument",
    "ExtractedTextFullText",
    "ExtractedTextFullTextPage",
    "ExtractedTextFullTextPages",
    "ExtractedTextPoint",
    "ExtractedTextWord",
    "ExtractedTextWordColor",
    "ExtractedTextWordCoordinates",
    "ExtractedTextWordFont",
    "ExtractedTextWordStyle",
    "PdfRestDeletionResponse",
    "PdfRestErrorResponse",
    "PdfRestFile",
    "PdfRestFileBasedResponse",
    "PdfRestFileID",
    "PdfRestInfoResponse",
    "PdfZugferdFinding",
    "PdfZugferdValidationResponse",
    "SummarizePdfTextResponse",
    "TranslatePdfTextFileResponse",
    "TranslatePdfTextResponse",
    "UpResponse",
)


class PdfRestFileID(str):
    """Str-like identifier for pdfRest files.

    Format:
      [optional '1' or '2' prefix] + [UUIDv4 with hyphens]

    Examples:
      - "de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39"          # no prefix
      - "1de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39"        # prefix '1'
      - "2DE305D2-B6A0-4B5D-9A55-4E4E6D8C2D39"        # prefix '2' (upper-case input accepted)

    Canonical representation is lowercase.
    """

    __slots__ = ()

    # For Python validation (case-insensitive)
    _PY_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:[12])?(?:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
        re.IGNORECASE,
    )

    # For JSON Schema (no inline flags; must include both cases)
    _PATTERN_STR: ClassVar[str] = (
        r"^(?:[12])?(?:[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12})$"
    )

    def __new__(cls, value: str) -> PdfRestFileID:
        """Create a normalized file identifier from a validated string.

        Args:
            value: Candidate pdfRest file id string.

        Returns:
            Lower-cased, validated file id value.

        Raises:
            ValueError: If `value` is not a valid prefixed UUIDv4 identifier.
        """
        if not cls._PY_PATTERN.fullmatch(value):
            msg = (
                "Invalid PdfRestPrefixedUUID4. Expected: "
                "optional '1' or '2' prefix + UUIDv4 with hyphens and RFC 4122 variant"
            )
            raise ValueError(msg)
        return str.__new__(cls, value.lower())

    @override
    def __str__(self) -> str:
        return str.__str__(self)

    @override
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

    @property
    def prefix(self) -> str | None:
        """The leading prefix digit ('1' or '2') if present, else None.

        Note: Presence is unambiguous by length:
          - 36 chars => no prefix
          - 37 chars => prefix present
        """
        return self[0] if len(self) == 37 else None

    @property
    def uuid(self) -> str:
        """The UUID part (without the optional prefix)."""
        return self[1:] if len(self) == 37 else self

    @property
    def uuid_obj(self) -> _uuid.UUID:
        """The UUID object for the UUID part."""
        return _uuid.UUID(self.uuid)

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Quick validity check without constructing the object."""
        return bool(cls._PY_PATTERN.fullmatch(value))

    @classmethod
    def from_parts(
        cls, u: str | _uuid.UUID, prefix: int | str | None = None
    ) -> PdfRestFileID:
        """Build a file id from a UUIDv4 and optional prefix.

        Args:
            u: UUID value as string or `uuid.UUID`.
            prefix: Optional leading prefix (`1` or `2`).

        Raises:
            ValueError: If the UUID is not version 4 or the prefix is invalid.
        """
        if isinstance(prefix, int):
            prefix = str(prefix)  # allow 1/2 as int
        if prefix not in (None, "1", "2"):
            msg = "prefix must be None, '1', or '2'"
            raise ValueError(msg)

        if isinstance(u, _uuid.UUID):
            if u.version != 4:
                msg = "UUID must be version 4"
                raise ValueError(msg)
            u_text = str(u)
        else:
            u_text = str(u)
            if not re.fullmatch(
                r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}",
                u_text,
            ):
                msg = "UUID text must be version 4 with RFC 4122 variant"
                raise ValueError(msg)

        return cls((prefix or "") + u_text)

    @classmethod
    def generate(cls, prefix: int | str | None = None) -> PdfRestFileID:
        """Generate a new value with an optional prefix (1 or 2)."""
        if isinstance(prefix, int):
            prefix = str(prefix)
        if prefix not in (None, "1", "2"):
            msg = "prefix must be None, '1', or '2'"
            raise ValueError(msg)
        return cls.from_parts(_uuid.uuid4(), prefix=prefix)

    # -------------------------
    # Pydantic v2 integration
    # -------------------------
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> CoreSchema:
        """Build a Pydantic v2 core schema for `PdfRestFileID`.

        Accepted inputs:
        - a UUID (validated as v4) converted to this type with no prefix
        - a string matching the `PdfRestFileID` pattern
        """
        from pydantic_core import core_schema

        str_schema = core_schema.str_schema(pattern=cls._PATTERN_STR)
        uuid_schema = core_schema.uuid_schema(version=4)
        union = core_schema.union_schema([uuid_schema, str_schema])

        def to_class(v: Any) -> PdfRestFileID:
            if isinstance(v, _uuid.UUID):
                # UUID input: no prefix
                return cls(str(v))
            # string already pattern-validated by inner schema
            return cls(v)

        return core_schema.no_info_after_validator_function(
            to_class,
            union,
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: Any, handler: Any
    ) -> JsonSchemaValue:
        """Provide a clean JSON Schema for OpenAPI/JSON Schema generators."""
        # Prefer a single-string schema with pattern and examples
        return {
            "type": "string",
            "title": cls.__name__,
            "description": "UUIDv4 with hyphens, optionally prefixed by '1' or '2'.",
            "pattern": cls._PATTERN_STR,
            "examples": [
                "de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39",
                "1de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39",
            ],
        }


class UpResponse(BaseModel):
    """Response payload returned by the `/up` health endpoint."""

    status: str
    """Service health status string returned by pdfRest."""

    product: str
    """Product identifier reported by the service."""

    release_date: date = Field(alias="releaseDate")
    """Release date for the deployed pdfRest version."""

    version: str
    """Semantic version identifier for the running service."""

    model_config = ConfigDict(frozen=True)


class PdfRestErrorResponse(BaseModel):
    """Error response payloads from pdfRest."""

    error: str | None = Field(alias="message")
    """Human-readable error message returned by the API."""

    model_config = ConfigDict(extra="allow", frozen=True)


class PdfRestFile(BaseModel):
    """Represents a file on the pdfRest server."""

    id: PdfRestFileID = Field(
        min_length=1,
        description="Identifier of the file on the pdfRest server",
    )
    """Identifier of the file on the pdfRest server."""

    name: str = Field(
        min_length=1,
        description="Name of the file",
    )
    """Name of the file."""

    url: HttpUrl = Field(
        description="URL from which the file can be downloaded",
    )
    """URL from which the file can be downloaded."""

    type: str = Field(
        min_length=1,
        description="MIME type of the file",
    )
    """MIME type of the file."""

    size: int = Field(
        description="Size of the file",
    )
    """Size of the file."""

    modified: AwareDatetime = Field(
        description="The last modified time of the file, which must include time zone "
        "info.",
    )
    """The last modified time of the file, which must include time zone info."""

    scheduled_deletion_time_utc: AwareDatetime | None = Field(
        alias="scheduledDeletionTimeUtc",
        default=None,
        description="The UTC time at which the file will be deleted from the server.",
    )
    """The UTC time at which the file will be deleted from the server."""

    model_config = ConfigDict(frozen=True)


class PdfRestFileBasedResponse(BaseModel):
    """Response model for file-based pdfRest operations.

    Includes input file identifiers, output files, and optional warnings from
    the API response payload.
    """

    # Allow all extra fields to be stored and serialized
    # See: https://docs.pydantic.dev/latest/concepts/models/#extra-fields
    model_config = ConfigDict(extra="allow")

    input_ids: Annotated[
        list[PdfRestFileID],
        Field(
            description="The ids of the files that were input to the pdfRest operation",
            validation_alias=AliasChoices("input_id", "inputId"),
        ),
    ]
    """The ids of the files that were input to the pdfRest operation."""

    # Optional because some endpoints may not make output
    output_files: Annotated[
        list[PdfRestFile],
        Field(
            description="The list of files returned by the pdfRest operation",
            validation_alias=AliasChoices("output_file", "outputFile"),
        ),
    ]
    """The list of files returned by the pdfRest operation."""

    warning: Annotated[
        str | None,
        Field(
            description="A warning that was generated during the pdfRest operation",
        ),
    ] = None
    """A warning that was generated during the pdfRest operation."""

    @property
    def input_id(self) -> PdfRestFileID:
        """Return the lone input id when exactly one input file was supplied.

        Raises:
            ValueError: If no input id is available or multiple input ids exist.
        """
        if len(self.input_ids) == 1:
            return self.input_ids[0]
        if len(self.input_ids) == 0:
            msg = "no input id was specified"
        else:
            msg = "multiple input ids were specified"
        raise ValueError(msg)

    @property
    def output_file(self) -> PdfRestFile:
        """Return the lone output file when exactly one output is available.

        Raises:
            ValueError: If no output file is available or multiple outputs exist.
        """
        if len(self.output_files) == 1:
            return self.output_files[0]
        if len(self.output_files) == 0:
            msg = "no output file was returned by the pdfRest operation"
        else:
            msg = "multiple output files were returned by the pdfRest operation"
        raise ValueError(msg)


class PdfZugferdFinding(BaseModel):
    """A finding reported while validating a ZUGFeRD or Factur-X PDF."""

    code: str
    """Stable finding code reported by the validation tooling."""

    severity: Literal["INFO", "WARNING", "BLOCKING", "ERROR"]
    """Severity assigned to the finding by the validation tooling."""

    message: str
    """Human-readable summary of the finding."""

    field: str | None = None
    """Invoice field associated with the finding, when available."""

    status: str | None = None
    """Status detail associated with the finding, when available."""

    comparison_reason: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices("comparison_reason", "comparisonReason"),
            pattern=r"^[A-Z][A-Z0-9_]{0,63}$",
        ),
    ] = None
    """Machine-readable reason for a visual-comparison result, when available."""

    model_config = ConfigDict(extra="allow", frozen=True)


class PdfZugferdValidationResponse(BaseModel):
    """Result returned after validating a ZUGFeRD or Factur-X PDF."""

    status: Literal["VALID", "INVALID"]
    """Overall ZUGFeRD package, XML, business-rule, and PDF/A-3 result."""

    pdfa: bool
    """Whether the independent PDFChecker result confirms PDF/A-3 conformance."""

    content_match_status: Annotated[
        Literal[
            "NOT_APPLICABLE",
            "CONFIRMED",
            "UNVERIFIED",
            "FAILED",
            "ERROR",
            "DEMO_REDACTED",
        ],
        Field(
            validation_alias=AliasChoices("content_match_status", "contentMatchStatus")
        ),
    ]
    """Result of comparing visible PDF content with the embedded invoice XML."""

    input_id: Annotated[
        PdfRestFileID,
        Field(validation_alias=AliasChoices("input_id", "inputId")),
    ]
    """Identifier of the validated PDF resource."""

    input_url: Annotated[
        str,
        Field(validation_alias=AliasChoices("input_url", "inputUrl")),
    ]
    """Download URL for the validated PDF resource."""

    findings: list[PdfZugferdFinding] | None = None
    """Actionable validation findings and non-blocking warnings, when present."""

    message: str | None = None
    """Free-tier notice when detailed validation data has been redacted."""

    model_config = ConfigDict(extra="allow", frozen=True)


class PdfRestDeletionResponse(BaseModel):
    """Response returned by the delete tool."""

    model_config = ConfigDict(extra="allow")

    deletion_responses: Annotated[
        dict[PdfRestFileID, str],
        Field(
            alias="deletionResponses",
            validation_alias=AliasChoices("deletion_responses", "deletionResponses"),
            description="Mapping of file ids to deletion results.",
            min_length=1,
        ),
    ]
    """Mapping of file ids to deletion results."""


class SummarizePdfTextResponse(BaseModel):
    """Response returned by the summarize-pdf-text tool."""

    model_config = ConfigDict(extra="allow")

    summary: Annotated[
        str | None,
        Field(
            description="Summary content",
            default=None,
        ),
    ] = None
    """Summary content."""

    input_id: Annotated[
        PdfRestFileID,
        Field(
            validation_alias=AliasChoices("input_id", "inputId"),
            description="The id of the input file.",
        ),
    ]
    """The id of the input file."""


class TranslatePdfTextResponse(BaseModel):
    """Response returned by the translated-pdf-text tool."""

    model_config = ConfigDict(extra="allow")

    source_languages: Annotated[
        list[str] | None,
        Field(
            alias="source_languages",
            validation_alias=AliasChoices("source_languages", "sourceLanguages"),
            description="Languages detected in the source content.",
            default=None,
        ),
    ] = None
    """Languages detected in the source content."""

    output_language: Annotated[
        str | None,
        Field(
            alias="output_language",
            validation_alias=AliasChoices("output_language", "outputLanguage"),
            description="Target language used for the translation.",
            default=None,
        ),
    ] = None
    """Target language used for the translation."""

    translated_text: Annotated[
        str | None,
        Field(
            alias="translated_text",
            validation_alias=AliasChoices("translated_text", "translatedText"),
            description="Inline translation content when output_type is json.",
            default=None,
        ),
    ] = None
    """Inline translation content when output_type is json."""

    input_id: Annotated[
        PdfRestFileID,
        Field(
            validation_alias=AliasChoices("input_id", "inputId"),
            description="The id of the input file.",
        ),
    ]
    """The id of the input file."""


class TranslatePdfTextFileResponse(PdfRestFileBasedResponse):
    """File-based response returned by the translated-pdf-text tool."""

    model_config = ConfigDict(extra="allow")

    source_languages: Annotated[
        list[str] | None,
        Field(
            alias="source_languages",
            validation_alias=AliasChoices("source_languages", "sourceLanguages"),
            description="Languages detected in the source content.",
            default=None,
        ),
    ] = None
    """Languages detected in the source content."""

    output_language: Annotated[
        str | None,
        Field(
            alias="output_language",
            validation_alias=AliasChoices("output_language", "outputLanguage"),
            description="Target language used for the translation.",
            default=None,
        ),
    ] = None
    """Target language used for the translation."""


class ExtractTextResponse(BaseModel):
    """Response returned by the extracted-text tool."""

    model_config = ConfigDict(extra="allow")

    full_text: Annotated[
        str | None,
        Field(
            alias="fullText",
            validation_alias=AliasChoices("full_text", "fullText"),
            description="Inline extracted text when output_type is json.",
            default=None,
        ),
    ] = None
    """Inline extracted text when output_type is json."""

    input_id: Annotated[
        PdfRestFileID,
        Field(
            validation_alias=AliasChoices("input_id", "inputId"),
            description="The id of the input file.",
        ),
    ]
    """The id of the input file."""

    warning: Annotated[
        str | None,
        Field(description="A warning that was generated during text extraction."),
    ] = None
    """A warning that was generated during text extraction."""


class ExtractedTextPoint(BaseModel):
    """A point in PDF coordinate space expressed in points."""

    model_config = ConfigDict(extra="allow")

    x: Annotated[
        float,
        Field(description="Horizontal position in PDF points."),
    ]
    """Horizontal position in PDF points."""

    y: Annotated[
        float,
        Field(description="Vertical position in PDF points."),
    ]
    """Vertical position in PDF points."""


class ExtractedTextWordCoordinates(BaseModel):
    """Bounding box describing where a word appears on the page."""

    model_config = ConfigDict(extra="allow")

    top_left: Annotated[
        ExtractedTextPoint,
        Field(
            alias="topLeft",
            validation_alias=AliasChoices("top_left", "topLeft"),
            description="Upper-left corner of the word bounds.",
        ),
    ]
    """Upper-left corner of the word bounds."""

    top_right: Annotated[
        ExtractedTextPoint,
        Field(
            alias="topRight",
            validation_alias=AliasChoices("top_right", "topRight"),
            description="Upper-right corner of the word bounds.",
        ),
    ]
    """Upper-right corner of the word bounds."""

    bottom_left: Annotated[
        ExtractedTextPoint,
        Field(
            alias="bottomLeft",
            validation_alias=AliasChoices("bottom_left", "bottomLeft"),
            description="Lower-left corner of the word bounds.",
        ),
    ]
    """Lower-left corner of the word bounds."""

    bottom_right: Annotated[
        ExtractedTextPoint,
        Field(
            alias="bottomRight",
            validation_alias=AliasChoices("bottom_right", "bottomRight"),
            description="Lower-right corner of the word bounds.",
        ),
    ]
    """Lower-right corner of the word bounds."""


class ExtractedTextWordColor(BaseModel):
    """Font color applied to an extracted word."""

    model_config = ConfigDict(extra="allow")

    space: Annotated[
        str,
        Field(description="Color space name reported by pdfRest (e.g., DeviceRGB)."),
    ]
    """Color space name reported by pdfRest (e.g., DeviceRGB)."""

    values: Annotated[
        list[float],
        Field(
            description="Numeric components in the reported color space.",
            min_length=1,
        ),
    ]
    """Numeric components in the reported color space."""


class ExtractedTextWordFont(BaseModel):
    """Font metadata applied to an extracted word."""

    model_config = ConfigDict(extra="allow")

    name: Annotated[
        str,
        Field(description="Reported font face name."),
    ]
    """Reported font face name."""

    size: Annotated[
        float,
        Field(description="Font size in points."),
    ]
    """Font size in points."""


class ExtractedTextWordStyle(BaseModel):
    """Style information for an extracted word."""

    model_config = ConfigDict(extra="allow")

    color: Annotated[
        ExtractedTextWordColor,
        Field(description="Color information for the word."),
    ]
    """Color information for the word."""

    font: Annotated[
        ExtractedTextWordFont,
        Field(description="Font information for the word."),
    ]
    """Font information for the word."""


class ExtractedTextWord(BaseModel):
    """A single word extracted from a PDF page."""

    model_config = ConfigDict(extra="allow")

    text: Annotated[
        str,
        Field(description="Word content as rendered by the PDF."),
    ]
    """Word content as rendered by the PDF."""

    page: Annotated[
        int,
        Field(description="1-indexed page number containing the word.", ge=1),
    ]
    """1-indexed page number containing the word."""

    coordinates: Annotated[
        ExtractedTextWordCoordinates | None,
        Field(
            description="Bounding box for the word when positional data is requested.",
            default=None,
        ),
    ] = None
    """Bounding box for the word when positional data is requested."""

    style: Annotated[
        ExtractedTextWordStyle | None,
        Field(
            description="Font/color details captured for the word.",
            default=None,
        ),
    ] = None
    """Font/color details captured for the word."""


class ExtractedTextFullTextPage(BaseModel):
    """Per-page representation of the aggregated text content."""

    model_config = ConfigDict(extra="allow")

    page: Annotated[
        int,
        Field(description="1-indexed page number.", ge=1),
    ]
    """1-indexed page number."""

    text: Annotated[
        str,
        Field(description="Concatenated text for the page."),
    ]
    """Concatenated text for the page."""


class ExtractedTextFullTextPages(BaseModel):
    """Container for per-page text output."""

    model_config = ConfigDict(extra="allow")

    pages: Annotated[
        list[ExtractedTextFullTextPage],
        Field(
            description="Ordered text for each page present in the document.",
            min_length=1,
        ),
    ]
    """Ordered text for each page present in the document."""


class ExtractedTextFullText(RootModel[str | ExtractedTextFullTextPages]):
    """Full-text extraction payload in document or per-page mode.

    Wraps either a single document-level string or a per-page text object and
    provides convenience accessors for both shapes.
    """

    root: str | ExtractedTextFullTextPages
    """Raw payload in document-text or per-page form."""

    @property
    def document_text(self) -> str | None:
        """Return document-level text for either payload shape.

        Falls back to joining per-page text when only the page-structured
        payload is available.
        """
        if isinstance(self.root, str):
            return self.root
        return " ".join(page.text for page in self.root.pages)

    @property
    def pages(self) -> list[ExtractedTextFullTextPage]:
        """Return per-page text entries when page mode is available.

        Raises:
            ValueError: If the payload is in document-string mode.
        """
        if isinstance(self.root, ExtractedTextFullTextPages):
            return self.root.pages
        msg = "full text payload was emitted in document mode; page data unavailable"
        raise ValueError(msg)

    def iter_pages(self) -> list[ExtractedTextFullTextPage]:
        """Return per-page text entries or an empty list in document mode.

        This helper avoids forcing callers to catch mode errors when they only
        need an iterable.
        """
        try:
            return self.pages
        except ValueError:
            return []


class ExtractedTextDocument(BaseModel):
    """Structured representation of the JSON output returned by extract_text_to_file."""

    model_config = ConfigDict(extra="allow")

    input_id: Annotated[
        PdfRestFileID,
        Field(
            alias="inputId",
            validation_alias=AliasChoices("input_id", "inputId"),
            description="Identifier of the uploaded PDF.",
        ),
    ]
    """Identifier of the uploaded PDF."""

    words: Annotated[
        list[ExtractedTextWord] | None,
        Field(
            description="Individual word records when word-level extraction is enabled.",
            default=None,
        ),
    ] = None
    """Individual word records when word-level extraction is enabled."""

    full_text: Annotated[
        ExtractedTextFullText | None,
        Field(
            alias="fullText",
            validation_alias=AliasChoices("full_text", "fullText"),
            description="Full text output (document string or per-page content).",
            default=None,
        ),
    ] = None
    """Full text output (document string or per-page content)."""


class ConvertToMarkdownResponse(BaseModel):
    """Response returned by the markdown conversion tool."""

    model_config = ConfigDict(extra="allow")

    markdown: Annotated[
        str | None,
        Field(
            description="Inline markdown content when output_type is json.",
            default=None,
        ),
    ] = None
    """Inline markdown content when output_type is json."""

    input_id: Annotated[
        PdfRestFileID,
        Field(
            validation_alias=AliasChoices("input_id", "inputId"),
            description="The id of the input file.",
        ),
    ]
    """The id of the input file."""

    output_url: Annotated[
        HttpUrl | None,
        Field(
            alias="outputUrl",
            validation_alias=AliasChoices("output_url", "outputUrl"),
            description="Download URL for file output.",
            default=None,
        ),
    ] = None
    """Download URL for file output."""

    output_id: Annotated[
        PdfRestFileID | None,
        Field(
            alias="outputId",
            validation_alias=AliasChoices("output_id", "outputId"),
            description="The id of the generated output when output_type is file.",
            default=None,
        ),
    ] = None
    """The id of the generated output when output_type is file."""

    warning: Annotated[
        str | None,
        Field(description="A warning that was generated during markdown conversion."),
    ] = None
    """A warning that was generated during markdown conversion."""


class PdfRestInfoResponse(BaseModel):
    """A response containing the output from the /info route."""

    # Allow all extra fields to be stored and serialized
    # See: https://docs.pydantic.dev/latest/concepts/models/#extra-fields
    model_config = ConfigDict(extra="allow")

    input_id: Annotated[
        PdfRestFileID,
        Field(
            validation_alias=AliasChoices("input_id", "inputId"),
            description="The id of the input file",
        ),
    ]
    """The id of the input file."""

    tagged: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether structure tags are present in the PDF "
            "document. The result is true or false."
        ),
    ] = None
    """Indicates whether structure tags are present in the PDF document. The result is true or false."""

    image_only: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description=(
                "Indicates whether the document is 'image only,' meaning it consists "
                "solely of embedded graphical images with no text or other standard "
                "PDF document features except for metadata. The result is true or "
                "false."
            )
        ),
    ] = None
    """Indicates whether the document is 'image only,' meaning it consists solely of embedded graphical images with no text or other standard PDF document features except for metadata. The result is true or false."""

    title: Annotated[
        str | None,
        Field(
            description=(
                "The title of the PDF as retrieved from the metadata. The result is a "
                "string that may be empty if the document does not have a title."
            )
        ),
    ] = None
    """The title of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have a title."""

    subject: Annotated[
        str | None,
        Field(
            description=(
                "The subject of the PDF as retrieved from the metadata. The result is "
                "a string that may be empty if the document does not have a subject."
            )
        ),
    ] = None
    """The subject of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have a subject."""

    author: Annotated[
        str | None,
        Field(
            description=(
                "The author of the PDF as retrieved from the metadata. The result is "
                "a string that may be empty if the document does not have an author."
            )
        ),
    ] = None
    """The author of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have an author."""

    producer: Annotated[
        str | None,
        Field(
            description=(
                "The producer of the PDF as retrieved from the metadata. The result "
                "is a string that may be empty if the document does not have a "
                "producer."
            )
        ),
    ] = None
    """The producer of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have a producer."""

    creator: Annotated[
        str | None,
        Field(
            description=(
                "The creator of the PDF as retrieved from the metadata. The result is "
                "a string that may be empty if the document does not have a creator."
            )
        ),
    ] = None
    """The creator of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have a creator."""

    creation_date: Annotated[
        str | None,
        Field(
            description=(
                "The creation date of the PDF as retrieved from the metadata. The "
                "result is a string that may be empty if the document does not "
                "have a creation date."
            )
        ),
    ] = None
    """The creation date of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have a creation date."""

    modified_date: Annotated[
        str | None,
        Field(
            description=(
                "The most recent modification date of the PDF as retrieved from the "
                "metadata. The result is a string that may be empty if the document "
                "does not have a modification date."
            )
        ),
    ] = None
    """The most recent modification date of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not have a modification date."""

    keywords: Annotated[
        str | None,
        Field(
            description=(
                "The keywords of the PDF as retrieved from the metadata. The result "
                "is a string that may be empty if the document does not include "
                "keywords."
            )
        ),
    ] = None
    """The keywords of the PDF as retrieved from the metadata. The result is a string that may be empty if the document does not include keywords."""

    custom_metadata: Annotated[
        dict[str, Any] | None,
        Field(
            description=(
                "Custom metadata entries extracted from the PDF. The result is a "
                "dictionary mapping keys to their stored values, or None when no "
                "custom metadata exists."
            )
        ),
    ] = None
    """Custom metadata entries extracted from the PDF. The result is a dictionary mapping keys to their stored values, or None when no custom metadata exists."""

    doc_language: Annotated[
        str | None,
        Field(
            description="The language of the document as declared in its metadata. "
            "The result is a string."
        ),
    ] = None
    """The language of the document as declared in its metadata. The result is a string."""

    page_count: Annotated[
        int | None,
        Field(
            description="The number of pages in the PDF document. The result is an "
            "integer."
        ),
    ] = None
    """The number of pages in the PDF document. The result is an integer."""

    contains_annotations: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description=(
                "Indicates whether the PDF document contains annotations such as "
                "notes, highlighted text, file attachments, crossed-out text, or text "
                "callout boxes. The result is true or false."
            )
        ),
    ] = None
    """Indicates whether the PDF document contains annotations such as notes, highlighted text, file attachments, crossed-out text, or text callout boxes. The result is true or false."""

    contains_signature: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains any digital signatures. "
            "The result is true or false."
        ),
    ] = None
    """Indicates whether the PDF contains any digital signatures. The result is true or false."""

    pdf_version: Annotated[
        str | None,
        Field(
            description=(
                "The version of the PDF standard used to create the document. The "
                "result is a string in the format X.Y.Z, where X, Y, and Z represent "
                "the major, minor, and extension versions."
            )
        ),
    ] = None
    """The version of the PDF standard used to create the document. The result is a string in the format X.Y.Z, where X, Y, and Z represent the major, minor, and extension versions."""

    file_size: Annotated[
        int | None,
        BeforeValidator(demo_int_or_passthrough),
        Field(
            description="The size of the PDF file in bytes. The result is an integer."
        ),
    ] = None
    """The size of the PDF file in bytes. The result is an integer."""

    filename: Annotated[
        str | None,
        Field(description="The name of the PDF file. The result is a string."),
    ] = None
    """The name of the PDF file. The result is a string."""

    restrict_permissions_set: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description=(
                "Indicates whether the PDF file has restricted permissions, such as "
                "preventing printing, copying, or signing. The result is true or "
                "false."
            )
        ),
    ] = None
    """Indicates whether the PDF file has restricted permissions, such as preventing printing, copying, or signing. The result is true or false."""

    contains_xfa: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains XFA forms. The result is "
            "true or false."
        ),
    ] = None
    """Indicates whether the PDF contains XFA forms. The result is true or false."""

    contains_acroforms: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains Acroforms. The result is "
            "true or false."
        ),
    ] = None
    """Indicates whether the PDF contains Acroforms. The result is true or false."""

    contains_javascript: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains JavaScript. The result is "
            "true or false."
        ),
    ] = None
    """Indicates whether the PDF contains JavaScript. The result is true or false."""

    contains_transparency: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains transparent objects. The "
            "result is true or false."
        ),
    ] = None
    """Indicates whether the PDF contains transparent objects. The result is true or false."""

    contains_embedded_file: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains one or more embedded "
            "files. The result is true or false."
        ),
    ] = None
    """Indicates whether the PDF contains one or more embedded files. The result is true or false."""

    uses_embedded_fonts: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains fully embedded fonts. "
            "The result is true or false."
        ),
    ] = None
    """Indicates whether the PDF contains fully embedded fonts. The result is true or false."""

    uses_nonembedded_fonts: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the PDF contains non-embedded fonts. The "
            "result is true or false."
        ),
    ] = None
    """Indicates whether the PDF contains non-embedded fonts. The result is true or false."""

    pdfa: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the document conforms to the PDF/A "
            "standard. The result is true or false."
        ),
    ] = None
    """Indicates whether the document conforms to the PDF/A standard. The result is true or false."""

    pdfua_claim: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the document claims to conform to the "
            "PDF/UA standard. The result is true or false."
        ),
    ] = None
    """Indicates whether the document claims to conform to the PDF/UA standard. The result is true or false."""

    pdfe_claim: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the document claims to conform to the "
            "PDF/E standard. The result is true or false."
        ),
    ] = None
    """Indicates whether the document claims to conform to the PDF/E standard. The result is true or false."""

    pdfx_claim: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description="Indicates whether the document claims to conform to the "
            "PDF/X standard. The result is true or false."
        ),
    ] = None
    """Indicates whether the document claims to conform to the PDF/X standard. The result is true or false."""

    requires_password_to_open: Annotated[
        bool | None,
        BeforeValidator(demo_bool_false_or_passthrough),
        Field(
            description=(
                "Indicates whether the PDF requires a password to open. The result "
                "is true or false. *Note*: A document requiring a password cannot be "
                "opened by this route and will not provide much other information."
            )
        ),
    ] = None
    """Indicates whether the PDF requires a password to open. The result is true or false. *Note*: A document requiring a password cannot be opened by this route and will not provide much other information."""

    all_queries_processed: Annotated[
        bool,
        BeforeValidator(demo_bool_true_or_passthrough),
        Field(
            validation_alias=AliasChoices(
                "all_queries_processed", "allQueriesProcessed"
            ),
            description=(
                "Indicates whether all possible queries about the PDF document were "
                "successfully processed. This field is required, and the result is "
                "true or false."
            ),
        ),
    ]
    """Indicates whether all possible queries about the PDF document were successfully processed. This field is required, and the result is true or false."""

    warning: Annotated[
        str | None,
        Field(
            description="A warning indicating why not all queries could be processed.",
        ),
    ] = None
    """A warning indicating why not all queries could be processed."""
