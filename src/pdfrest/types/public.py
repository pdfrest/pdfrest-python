"""Public type definitions for the pdfrest client."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast, get_args

from typing_extensions import Required, TypedDict

if TYPE_CHECKING:
    from pdfrest.models import PdfRestFile
else:  # pragma: no cover - used only for typing at runtime
    PdfRestFile = Any

__all__ = (
    "ALL_OCR_LANGUAGES",
    "ALL_PDF_INFO_QUERIES",
    "ALL_PDF_RESTRICTIONS",
    "BmpColorModel",
    "CompressionLevel",
    "ExportDataFormat",
    "ExtractTextGranularity",
    "FlattenQuality",
    "GifColorModel",
    "GraphicSmoothing",
    "HtmlPageOrientation",
    "HtmlPageSize",
    "HtmlWebLayout",
    "JpegColorModel",
    "OcrLanguage",
    "PdfAType",
    "PdfAddLineObject",
    "PdfAddRectangleObject",
    "PdfAddShapeObject",
    "PdfAddTextObject",
    "PdfCMYKColor",
    "PdfColor",
    "PdfColorProfile",
    "PdfContentStructureType",
    "PdfConversionCompression",
    "PdfConversionDownsample",
    "PdfConversionLocale",
    "PdfCustomPageSize",
    "PdfInfoQuery",
    "PdfMergeInput",
    "PdfMergeSource",
    "PdfPageOrientation",
    "PdfPageSelection",
    "PdfPageSize",
    "PdfPresetColorProfile",
    "PdfRGBColor",
    "PdfRedactionInstruction",
    "PdfRedactionPreset",
    "PdfRedactionType",
    "PdfRestriction",
    "PdfSignatureConfiguration",
    "PdfSignatureCredentials",
    "PdfSignatureDisplay",
    "PdfSignatureLocation",
    "PdfSignaturePoint",
    "PdfStructuredTextCellPadding",
    "PdfStructuredTextCsvColumn",
    "PdfStructuredTextDataPresentation",
    "PdfStructuredTextImageSources",
    "PdfStructuredTextLineHandling",
    "PdfStructuredTextMargin",
    "PdfStructuredTextMissingImageAltText",
    "PdfStructuredTextPageOrientation",
    "PdfStructuredTextPageSetup",
    "PdfStructuredTextStyle",
    "PdfStructuredTextTableStyle",
    "PdfStructuredTextTextAlignment",
    "PdfTextColor",
    "PdfXType",
    "PngColorModel",
    "SummaryFormat",
    "SummaryOutputFormat",
    "SummaryOutputType",
    "TiffColorModel",
    "TranslateOutputFormat",
    "WatermarkHorizontalAlignment",
    "WatermarkVerticalAlignment",
)

#: Supported query keys for
#: [PdfRestClient.query_pdf_info][pdfrest.PdfRestClient.query_pdf_info] and
#: [AsyncPdfRestClient.query_pdf_info][pdfrest.AsyncPdfRestClient.query_pdf_info].
PdfInfoQuery = Literal[
    "tagged",
    "image_only",
    "title",
    "subject",
    "author",
    "producer",
    "creator",
    "creation_date",
    "modified_date",
    "keywords",
    "custom_metadata",
    "doc_language",
    "page_count",
    "contains_annotations",
    "contains_signature",
    "pdf_version",
    "file_size",
    "filename",
    "restrict_permissions_set",
    "contains_xfa",
    "contains_acroforms",
    "contains_javascript",
    "contains_transparency",
    "contains_embedded_file",
    "uses_embedded_fonts",
    "uses_nonembedded_fonts",
    "pdfa",
    "pdfua_claim",
    "pdfe_claim",
    "pdfx_claim",
    "requires_password_to_open",
]

ALL_PDF_INFO_QUERIES: tuple[PdfInfoQuery, ...] = cast(
    tuple[PdfInfoQuery, ...], get_args(PdfInfoQuery)
)

#: Redaction match mode used by [PdfRedactionInstruction][].
PdfRedactionType = Literal["literal", "regex", "preset"]

#: Built-in redaction presets accepted by pdfRest.
PdfRedactionPreset = Literal[
    "email",
    "phone_number",
    "date",
    "us_ssn",
    "url",
    "credit_card",
    "credit_debit_pin",
    "bank_routing_number",
    "international_bank_account_number",
    "swift_bic_number",
    "ipv4",
    "ipv6",
]


class PdfRedactionInstruction(TypedDict):
    """Single redaction rule for preview/apply redaction operations."""

    type: PdfRedactionType
    value: PdfRedactionPreset | str


PdfCMYKColor = tuple[int, int, int, int]
PdfRGBColor = tuple[int, int, int]
PdfColor = PdfRGBColor | PdfCMYKColor
PdfTextColor = PdfColor

PdfStructuredTextDataPresentation: TypeAlias = Literal["source", "hierarchy"]
"""JSON/XML presentation accepted by structured document conversion helpers.

Accepted values:

- `source`: Preserve JSON or XML syntax and indentation.
- `hierarchy`: Render JSON or XML as a readable hierarchy.
"""

PdfStructuredTextPageOrientation: TypeAlias = Literal["auto", "portrait", "landscape"]
"""Page orientation accepted by structured document conversion helpers.

Accepted values:

- `auto`: Let the converter choose an orientation appropriate for the content.
- `portrait`: Use portrait page orientation.
- `landscape`: Use landscape page orientation.
"""

PdfStructuredTextMissingImageAltText: TypeAlias = Literal["warn", "fail", "artifact"]
"""Policy for Markdown images that do not have alternate text.

Accepted values:

- `warn`: Continue conversion and report missing alternate text according to
  converter behavior.
- `fail`: Reject conversion when an image lacks alternate text.
- `artifact`: Treat an image without alternate text as an artifact.
"""

PdfStructuredTextLineHandling: TypeAlias = Literal["reflow", "preserve"]
"""Line-break handling accepted by ``convert_plain_text_to_pdf``.

Accepted values:

- `reflow`: Reflow plain-text lines to fit the page width.
- `preserve`: Preserve source line breaks.
"""

PdfStructuredTextTextAlignment: TypeAlias = Literal["left", "center", "right"]
"""CSV column text alignment accepted by ``convert_csv_to_pdf``.

Accepted values:

- `left`: Align text to the left of the column.
- `center`: Center text within the column.
- `right`: Align text to the right of the column.
"""


class PdfStructuredTextMargin(TypedDict, total=False):
    """Per-side page margins for structured document conversion.

    Attributes:
        top: Optional top margin in PDF points. Must be at least 0.
        right: Optional right margin in PDF points. Must be at least 0.
        bottom: Optional bottom margin in PDF points. Must be at least 0.
        left: Optional left margin in PDF points. Must be at least 0.
    """

    top: float
    right: float
    bottom: float
    left: float


class PdfStructuredTextPageSetup(TypedDict, total=False):
    """Page geometry for structured document conversion.

    Attributes:
        size: Optional non-empty page-size name understood by pdfRest, such as
            ``Letter`` or ``A4``.
        width: Optional custom page width in PDF points. Must be greater than 0
            and supplied together with ``height``.
        height: Optional custom page height in PDF points. Must be greater than
            0 and supplied together with ``width``.
        orientation: Optional ``auto``, ``portrait``, or ``landscape`` page
            orientation.
        margin: Optional per-side margins in PDF points.
    """

    size: str
    width: float
    height: float
    orientation: PdfStructuredTextPageOrientation
    margin: PdfStructuredTextMargin


class PdfStructuredTextCellPadding(TypedDict, total=False):
    """Per-side table-cell padding for Markdown and CSV conversion.

    Attributes:
        top: Optional top padding in PDF points, from 0 through 72.
        right: Optional right padding in PDF points, from 0 through 72.
        bottom: Optional bottom padding in PDF points, from 0 through 72.
        left: Optional left padding in PDF points, from 0 through 72.
    """

    top: float
    right: float
    bottom: float
    left: float


class PdfStructuredTextTableStyle(TypedDict, total=False):
    """Table presentation for Markdown and CSV conversion.

    Attributes:
        column_width_weights: Optional non-empty relative column-width weights;
            every value must be greater than 0.
        keep_header_with_first_row: Optional flag to keep the table header with
            its first data row during pagination.
        repeat_headers_on_overflow: Optional flag to repeat headers on
            continuation pages.
        show_borders: Optional flag to draw table-cell borders.
        border_width: Optional border width in PDF points, from 0 through 12.
        border_color_rgb: Optional RGB border color with channels from 0 through
            255.
        header_fill_color_rgb: Optional RGB header background color.
        header_text_color_rgb: Optional RGB header text color.
        row_fill_color_rgb: Optional RGB data-row background color.
        alternate_row_fill_color_rgb: Optional RGB alternating-row background
            color.
        cell_padding: Optional per-side cell padding in PDF points.
    """

    column_width_weights: Sequence[float]
    keep_header_with_first_row: bool
    repeat_headers_on_overflow: bool
    show_borders: bool
    border_width: float
    border_color_rgb: PdfRGBColor
    header_fill_color_rgb: PdfRGBColor
    header_text_color_rgb: PdfRGBColor
    row_fill_color_rgb: PdfRGBColor
    alternate_row_fill_color_rgb: PdfRGBColor
    cell_padding: PdfStructuredTextCellPadding


class PdfStructuredTextStyle(TypedDict, total=False):
    """Typography shared by all structured document conversion helpers.

    Attributes:
        font: Optional non-empty body-text font family.
        heading_font: Optional non-empty heading font family.
        code_font: Optional non-empty code/preformatted-text font family.
        cjk_font: Optional non-empty Chinese, Japanese, and Korean font family.
        fallback_fonts: Optional non-empty ordered fallback-font family list.
        text_size: Optional body-text size in PDF points, from 6 through 72.
        text_color_rgb: Optional RGB body-text color with channels from 0
            through 255.
        heading_scale: Optional heading scale greater than 0 and at most 4.
    """

    font: str
    heading_font: str
    code_font: str
    cjk_font: str
    fallback_fonts: Sequence[str]
    text_size: float
    text_color_rgb: PdfRGBColor
    heading_scale: float


class PdfStructuredTextCsvColumn(TypedDict, total=False):
    """One CSV column presentation override.

    Attributes:
        index: Required zero-based CSV column index.
        text_align: Optional ``left``, ``center``, or ``right`` alignment.
        width_weight: Optional relative width weight greater than 0.
    """

    index: Required[int]
    text_align: PdfStructuredTextTextAlignment
    width_weight: float


PdfStructuredTextImageSources: TypeAlias = Mapping[str, PdfRestFile]
"""Markdown image-target mapping consumed by ``convert_markdown_to_pdf``."""

PdfContentStructureType = Literal[
    "P",
    "H",
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "Lbl",
    "Span",
    "Quote",
    "Note",
    "Reference",
    "BibEntry",
    "Code",
    "Link",
    "Annot",
    "Ruby",
    "RB",
    "RT",
    "RP",
    "Warichu",
    "WT",
    "WP",
    "Figure",
    "Formula",
    "Form",
]


class PdfAddLineObject(TypedDict, total=False):
    """Line shape inserted by [pdfrest.PdfRestClient.add_shapes_to_pdf][].

    Attributes:
        type: Required discriminator. Must be ``"line"``.
        page: Required one-based page number or ``"all"``.
        x1: Required horizontal start coordinate in PDF points. Must be at least 0.
        y1: Required vertical start coordinate in PDF points. Must be at least 0.
        x2: Required horizontal end coordinate in PDF points. Must be at least 0.
        y2: Required vertical end coordinate in PDF points. Must be at least 0.
        stroke_color: Optional RGB ``(red, green, blue)`` or CMYK
            ``(cyan, magenta, yellow, black)`` tuple. RGB channels range from 0
            through 255; CMYK channels range from 0 through 100.
        stroke_width: Optional line width in PDF points. Must be greater than 0.
        opacity: Optional opacity from 0 (transparent) through 1 (opaque).
        tag_actual_text: Optional non-empty accessible text. Requires
            ``tag_enabled=True`` on the client method.
        tag_is_artifact: Optional artifact marker. Requires ``tag_enabled=True``
            on the client method.
        tag_structure_type: Optional PDF structure type. Requires
            ``tag_enabled=True`` on the client method.
    """

    type: Required[Literal["line"]]
    page: Required[Literal["all"] | int]
    x1: Required[float]
    y1: Required[float]
    x2: Required[float]
    y2: Required[float]
    stroke_color: PdfColor
    stroke_width: float
    opacity: float
    tag_actual_text: str
    tag_is_artifact: bool
    tag_structure_type: PdfContentStructureType


class PdfAddRectangleObject(TypedDict, total=False):
    """Rectangle shape inserted by [pdfrest.PdfRestClient.add_shapes_to_pdf][].

    Attributes:
        type: Required discriminator. Must be ``"rectangle"``.
        page: Required one-based page number or ``"all"``.
        x: Required horizontal lower-left coordinate in PDF points. Must be at
            least 0.
        y: Required vertical lower-left coordinate in PDF points. Must be at
            least 0.
        width: Required width in PDF points. Must be greater than 0.
        height: Required height in PDF points. Must be greater than 0.
        fill_color: Optional RGB ``(red, green, blue)`` or CMYK
            ``(cyan, magenta, yellow, black)`` tuple. RGB channels range from 0
            through 255; CMYK channels range from 0 through 100.
        stroke_color: Optional RGB or CMYK tuple with the same channel ranges as
            ``fill_color``.
        stroke_width: Optional border width in PDF points. Must be greater than
            0.
        opacity: Optional opacity from 0 (transparent) through 1 (opaque).
        tag_actual_text: Optional non-empty accessible text. Requires
            ``tag_enabled=True`` on the client method.
        tag_is_artifact: Optional artifact marker. Requires ``tag_enabled=True``
            on the client method.
        tag_structure_type: Optional PDF structure type. Requires
            ``tag_enabled=True`` on the client method.
    """

    type: Required[Literal["rectangle"]]
    page: Required[Literal["all"] | int]
    x: Required[float]
    y: Required[float]
    width: Required[float]
    height: Required[float]
    fill_color: PdfColor
    stroke_color: PdfColor
    stroke_width: float
    opacity: float
    tag_actual_text: str
    tag_is_artifact: bool
    tag_structure_type: PdfContentStructureType


PdfAddShapeObject: TypeAlias = PdfAddLineObject | PdfAddRectangleObject
"""A line or rectangle object accepted by
[pdfrest.PdfRestClient.add_shapes_to_pdf][]."""


class PdfAddTextObject(TypedDict, total=False):
    """Text overlay object used by add-text style operations.

    Attributes:
        font: Font family name used to render text.
        max_width: Maximum text box width in PDF points.
        opacity: Opacity value from 0.0 (transparent) to 1.0 (opaque).
        page: One-based page number or ``"all"`` for every page.
        rotation: Rotation angle in degrees.
        text: Text content to draw.
        text_color_rgb: Optional RGB text color tuple.
        text_color_cmyk: Optional CMYK text color tuple.
        text_size: Font size in points.
        x: Horizontal origin in PDF points.
        y: Vertical origin in PDF points.
        is_right_to_left: Whether text should be rendered right-to-left.
    """

    font: Required[str]
    max_width: Required[float]
    opacity: Required[float]
    page: Required[Literal["all"] | int]
    rotation: Required[float]
    text: Required[str]
    text_color_rgb: PdfRGBColor
    text_color_cmyk: PdfCMYKColor
    text_size: Required[float]
    x: Required[float]
    y: Required[float]
    is_right_to_left: bool


class PdfCustomPageSize(TypedDict):
    """Custom page dimensions for page-size aware conversions.

    Attributes:
        custom_height: Page height in points.
        custom_width: Page width in points.
    """

    custom_height: Required[float]
    custom_width: Required[float]


#: Page selector accepted by endpoints that support page filtering.
PdfPageSelection = str | int | Sequence[str | int]


class PdfMergeSource(TypedDict, total=False):
    """Merge item containing an uploaded file and optional page selection."""

    file: Required[PdfRestFile]
    pages: PdfPageSelection | None


#: Merge input item accepted by merge APIs.
PdfMergeInput = PdfRestFile | PdfMergeSource | tuple[PdfRestFile, PdfPageSelection]

PdfConversionCompression = Literal["lossy", "lossless"]
PdfConversionDownsample = Literal["off", 75, 150, 300, 600, 1200]
PdfConversionLocale = Literal["US", "Germany"]
HtmlPageSize = Literal["letter", "legal", "ledger", "A3", "A4", "A5"]
HtmlPageOrientation = Literal["portrait", "landscape"]
HtmlWebLayout = Literal["desktop", "tablet", "mobile"]


class PdfSignaturePoint(TypedDict):
    """Coordinate point used for signature placement in PDF points.

    Attributes:
        x: Horizontal position in points.
        y: Vertical position in points.
    """

    x: float
    y: float


class PdfSignatureLocation(TypedDict):
    """Bounding box and page where a signature field should be rendered.

    Attributes:
        bottom_left: Bottom-left [PdfSignaturePoint][pdfrest.types.PdfSignaturePoint] of the signature rectangle.
        top_right: Top-right [PdfSignaturePoint][pdfrest.types.PdfSignaturePoint] of the signature rectangle.
        page: One-based page index or ``"all"``.
    """

    bottom_left: Required[PdfSignaturePoint]
    top_right: Required[PdfSignaturePoint]
    page: Required[str | int]


class PdfSignatureDisplay(TypedDict, total=False):
    """Optional text fields included in visible signature appearances.

    Attributes:
        include_distinguished_name: Whether to include signer DN text.
        include_datetime: Whether to include signing date/time text.
        contact: Contact text shown in the visible signature.
        location: Location text shown in the visible signature.
        name: Signer name text shown in the visible signature.
        reason: Signing reason text shown in the visible signature.
    """

    include_distinguished_name: bool
    include_datetime: bool
    contact: str
    location: str
    name: str
    reason: str


class PdfNewSignatureConfiguration(TypedDict, total=False):
    """Configuration for creating and signing a new signature field.

    Attributes:
        type: Must be ``"new"``.
        location: Placement rectangle and page as [PdfSignatureLocation][pdfrest.types.PdfSignatureLocation].
        name: Optional name for the signature field.
        logo_opacity: Optional logo opacity in the range ``[0, 1]``.
        display: Optional visible-signature settings as [PdfSignatureDisplay][pdfrest.types.PdfSignatureDisplay].
    """

    type: Required[Literal["new"]]
    location: Required[PdfSignatureLocation]
    name: str
    logo_opacity: float
    display: PdfSignatureDisplay


class PdfExistingSignatureConfiguration(TypedDict, total=False):
    """Configuration for signing an existing signature field.

    Attributes:
        type: Must be ``"existing"``.
        location: Optional placement override as [PdfSignatureLocation][pdfrest.types.PdfSignatureLocation].
        name: Optional existing signature field name.
        logo_opacity: Optional logo opacity in the range ``[0, 1]``.
        display: Optional visible-signature settings as [PdfSignatureDisplay][pdfrest.types.PdfSignatureDisplay].
    """

    type: Required[Literal["existing"]]
    location: PdfSignatureLocation
    name: str
    logo_opacity: float
    display: PdfSignatureDisplay


#: Signature placement configuration accepted by
#: [PdfRestClient.sign_pdf][pdfrest.PdfRestClient.sign_pdf] and
#: [AsyncPdfRestClient.sign_pdf][pdfrest.AsyncPdfRestClient.sign_pdf].
PdfSignatureConfiguration = (
    PdfNewSignatureConfiguration | PdfExistingSignatureConfiguration
)


class PdfPfxCredentials(TypedDict):
    """Credentials bundle using a PFX/P12 file plus passphrase file.

    Attributes:
        pfx: Uploaded credentials archive as a [PdfRestFile][pdfrest.models.PdfRestFile].
        passphrase: Uploaded text passphrase as a [PdfRestFile][pdfrest.models.PdfRestFile].
    """

    pfx: Required[PdfRestFile]
    passphrase: Required[PdfRestFile]


class PdfPemCredentials(TypedDict):
    """Credentials bundle using certificate and private key uploads.

    Attributes:
        certificate: Uploaded certificate as a [PdfRestFile][pdfrest.models.PdfRestFile].
        private_key: Uploaded private key as a [PdfRestFile][pdfrest.models.PdfRestFile].
    """

    certificate: Required[PdfRestFile]
    private_key: Required[PdfRestFile]


#: Credentials accepted by
#: [PdfRestClient.sign_pdf][pdfrest.PdfRestClient.sign_pdf] and
#: [AsyncPdfRestClient.sign_pdf][pdfrest.AsyncPdfRestClient.sign_pdf].
PdfSignatureCredentials = PdfPfxCredentials | PdfPemCredentials

#: Canonical PDF/A conformance targets accepted by ``convert_to_pdfa``.
#: Payload validation accepts case-insensitive string input and normalizes it
#: to one of these literals before serialization.
PdfAType = Literal["PDF/A-1b", "PDF/A-2b", "PDF/A-2u", "PDF/A-3b", "PDF/A-3u"]
#: PDF/X conformance targets accepted by ``convert_to_pdfx``.
PdfXType = Literal["PDF/X-1a", "PDF/X-3", "PDF/X-4", "PDF/X-6"]
#: Granularity modes for extracted full text payloads.
ExtractTextGranularity = Literal["off", "by_page", "document"]
#: Compression levels accepted by ``compress_pdf``.
CompressionLevel = Literal["low", "medium", "high", "custom"]
#: Quality presets for transparency flattening.
FlattenQuality = Literal["low", "medium", "high"]
#: PNG output color models accepted by ``convert_to_png``.
PngColorModel = Literal["rgb", "rgba", "gray"]
#: BMP output color models accepted by ``convert_to_bmp``.
BmpColorModel = Literal["rgb", "gray"]
#: GIF output color models accepted by ``convert_to_gif``.
GifColorModel = Literal["rgb", "gray"]
#: JPEG output color models accepted by ``convert_to_jpeg``.
JpegColorModel = Literal["rgb", "cmyk", "gray"]
#: TIFF output color models accepted by ``convert_to_tiff``.
TiffColorModel = Literal["rgb", "rgba", "cmyk", "lab", "gray"]
#: Graphic smoothing modes for image conversion endpoints.
GraphicSmoothing = Literal["none", "all", "text", "line", "image"]
# Server accepts all values here, but enforces form-type subsets at runtime:
# AcroForm -> xfdf/fdf/xml, XFA -> xfd/xdp/xml.
ExportDataFormat = Literal["fdf", "xfdf", "xml", "xdp", "xfd"]

#: Summary styles accepted by summarize-text endpoints.
SummaryFormat = Literal[
    "overview",
    "highlight",
    "abstract",
    "bullet_points",
    "numbered_list",
    "table_of_contents",
    "outline",
    "question_answer",
    "action_items",
]

#: Output text format for summary endpoints.
SummaryOutputFormat = Literal["plaintext", "markdown"]
#: Output mode for summary endpoints.
SummaryOutputType = Literal["json", "file"]

#: Output text format for translate-text endpoints.
TranslateOutputFormat = Literal["plaintext", "markdown"]

#: OCR languages accepted by ``ocr_pdf``.
OcrLanguage = Literal[
    "ChineseSimplified",
    "ChineseTraditional",
    "Dutch",
    "English",
    "French",
    "German",
    "Italian",
    "Japanese",
    "Korean",
    "Portuguese",
    "Spanish",
]

ALL_OCR_LANGUAGES: tuple[OcrLanguage, ...] = cast(
    tuple[OcrLanguage, ...], get_args(OcrLanguage)
)

#: Document permissions accepted by password restriction endpoints.
PdfRestriction = Literal[
    "print_low",
    "print_high",
    "edit_document_assembly",
    "edit_fill_and_sign_form_fields",
    "edit_annotations",
    "edit_content",
    "copy_content",
    "accessibility_off",
]

ALL_PDF_RESTRICTIONS: tuple[PdfRestriction, ...] = cast(
    tuple[PdfRestriction, ...], get_args(PdfRestriction)
)

PdfPageSize = Literal["letter", "legal", "ledger", "A3", "A4", "A5"] | PdfCustomPageSize
PdfPageOrientation = Literal["portrait", "landscape"]
PdfPresetColorProfile = Literal[
    "lab-d50",
    "srgb",
    "apple-rgb",
    "color-match-rgb",
    "gamma-18",
    "gamma-22",
    "dot-gain-10",
    "dot-gain-15",
    "dot-gain-20",
    "dot-gain-25",
    "dot-gain-30",
    "monitor-rgb",
    "acrobat5-cmyk",
    "acrobat9-cmyk",
]

PdfColorProfile = PdfPresetColorProfile
WatermarkHorizontalAlignment = Literal["left", "center", "right"]
WatermarkVerticalAlignment = Literal["top", "center", "bottom"]
