"""Public type definitions for the pdfrest client."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, cast, get_args

from typing_extensions import Required, TypedDict

if TYPE_CHECKING:
    from pdfrest.models import PdfRestFile
else:  # pragma: no cover - used only for typing at runtime
    PdfRestFile = Any

__all__ = (
    "ALL_OCR_LANGUAGES",
    "ALL_PDF_INFO_QUERIES",
    "BmpColorModel",
    "CompressionLevel",
    "ExtractTextGranularity",
    "FlattenQuality",
    "GifColorModel",
    "GraphicSmoothing",
    "JpegColorModel",
    "OcrLanguage",
    "PdfAType",
    "PdfInfoQuery",
    "PdfMergeInput",
    "PdfMergeSource",
    "PdfPageSelection",
    "PdfRGBColor",
    "PdfRedactionInstruction",
    "PdfRedactionPreset",
    "PdfRedactionType",
    "PdfXType",
    "PngColorModel",
    "SummaryFormat",
    "SummaryOutputFormat",
    "SummaryOutputType",
    "TiffColorModel",
    "TranslateOutputFormat",
)

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

PdfRedactionType = Literal["literal", "regex", "preset"]

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
    type: PdfRedactionType
    value: PdfRedactionPreset | str


PdfRGBColor = tuple[int, int, int]

PdfPageSelection = str | int | Sequence[str | int]


class PdfMergeSource(TypedDict, total=False):
    file: Required[PdfRestFile]
    pages: PdfPageSelection | None


PdfMergeInput = PdfRestFile | PdfMergeSource | tuple[PdfRestFile, PdfPageSelection]

PdfAType = Literal["PDF/A-1b", "PDF/A-2b", "PDF/A-2u", "PDF/A-3b", "PDF/A-3u"]
PdfXType = Literal["PDF/X-1a", "PDF/X-3", "PDF/X-4", "PDF/X-6"]
ExtractTextGranularity = Literal["off", "by_page", "document"]
CompressionLevel = Literal["low", "medium", "high", "custom"]
FlattenQuality = Literal["low", "medium", "high"]
PngColorModel = Literal["rgb", "rgba", "gray"]
BmpColorModel = Literal["rgb", "gray"]
GifColorModel = Literal["rgb", "gray"]
JpegColorModel = Literal["rgb", "cmyk", "gray"]
TiffColorModel = Literal["rgb", "rgba", "cmyk", "lab", "gray"]
GraphicSmoothing = Literal["none", "all", "text", "line", "image"]

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

SummaryOutputFormat = Literal["plaintext", "markdown"]
SummaryOutputType = Literal["json", "file"]

TranslateOutputFormat = Literal["plaintext", "markdown"]

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
