# API guide

This guide organizes `PdfRestClient` and `AsyncPdfRestClient` methods by
workflow, so you can quickly find the right call for a user task.

Notes:

- Every sync method has an async counterpart with the same name.
- Sync client: [PdfRestClient][pdfrest.PdfRestClient]
- Async client: [AsyncPdfRestClient][pdfrest.AsyncPdfRestClient]

## Start here: common flow

1. Upload file(s): [files.create_from_paths][pdfrest.PdfRestFilesClient.create_from_paths]
2. Call one processing method from a category below.
3. Download outputs: [files.read_bytes][pdfrest.PdfRestFilesClient.read_bytes] or
   [files.write_bytes][pdfrest.PdfRestFilesClient.write_bytes]
4. (Optional) clean up: [files.delete][pdfrest.PdfRestFilesClient.delete]

## Service and file operations

Use these methods to check service status and manage uploaded resources.

- Health check:
  [up][pdfrest.PdfRestClient.up]
- File helper:
  [files][pdfrest.PdfRestClient.files]
- File upload and fetch:
  [files.create][pdfrest.PdfRestFilesClient.create],
  [files.create_from_paths][pdfrest.PdfRestFilesClient.create_from_paths],
  [files.create_from_urls][pdfrest.PdfRestFilesClient.create_from_urls],
  [files.get][pdfrest.PdfRestFilesClient.get]
- File read/write:
  [files.read_bytes][pdfrest.PdfRestFilesClient.read_bytes],
  [files.read_text][pdfrest.PdfRestFilesClient.read_text],
  [files.read_json][pdfrest.PdfRestFilesClient.read_json],
  [files.write_bytes][pdfrest.PdfRestFilesClient.write_bytes],
  [files.stream][pdfrest.PdfRestFilesClient.stream]
- File delete:
  [files.delete][pdfrest.PdfRestFilesClient.delete]

## Inspect, extract, summarize, and translate

Use this group when users need metadata or text intelligence.

- Metadata and document properties:
  [query_pdf_info][pdfrest.PdfRestClient.query_pdf_info]
- OCR and text extraction:
  [ocr_pdf][pdfrest.PdfRestClient.ocr_pdf],
  [extract_pdf_text][pdfrest.PdfRestClient.extract_pdf_text],
  [extract_pdf_text_to_file][pdfrest.PdfRestClient.extract_pdf_text_to_file]
- Image extraction:
  [extract_images][pdfrest.PdfRestClient.extract_images]
- Summaries:
  [summarize_text][pdfrest.PdfRestClient.summarize_text],
  [summarize_text_to_file][pdfrest.PdfRestClient.summarize_text_to_file]
- Translation:
  [translate_pdf_text][pdfrest.PdfRestClient.translate_pdf_text],
  [translate_pdf_text_to_file][pdfrest.PdfRestClient.translate_pdf_text_to_file]
- Markdown output:
  [convert_to_markdown][pdfrest.PdfRestClient.convert_to_markdown]

## Compose, split, merge, and package

Use this group for document assembly and distribution.

- Create or partition documents:
  [blank_pdf][pdfrest.PdfRestClient.blank_pdf],
  [split_pdf][pdfrest.PdfRestClient.split_pdf]
- Combine documents:
  [merge_pdfs][pdfrest.PdfRestClient.merge_pdfs]
- Package/unpackage output sets:
  [zip_files][pdfrest.PdfRestClient.zip_files],
  [unzip_file][pdfrest.PdfRestClient.unzip_file]
- Embed attachments:
  [add_attachment_to_pdf][pdfrest.PdfRestClient.add_attachment_to_pdf]

## Markup, branding, and redaction

Use this group to add visible content or remove sensitive content.

- Add overlays:
  [add_text_to_pdf][pdfrest.PdfRestClient.add_text_to_pdf],
  [add_image_to_pdf][pdfrest.PdfRestClient.add_image_to_pdf],
  [add_shapes_to_pdf][pdfrest.PdfRestClient.add_shapes_to_pdf]
- Watermarking:
  [watermark_pdf_with_text][pdfrest.PdfRestClient.watermark_pdf_with_text],
  [watermark_pdf_with_image][pdfrest.PdfRestClient.watermark_pdf_with_image]
- Redaction workflow:
  [preview_redactions][pdfrest.PdfRestClient.preview_redactions] first,
  then [apply_redactions][pdfrest.PdfRestClient.apply_redactions]

## Security, signing, and compliance

Use this group for password protection, permissions, signatures, and standards.

- Permissions password:
  [add_permissions_password][pdfrest.PdfRestClient.add_permissions_password],
  [change_permissions_password][pdfrest.PdfRestClient.change_permissions_password],
  [remove_permissions_password][pdfrest.PdfRestClient.remove_permissions_password]
- Open password:
  [add_open_password][pdfrest.PdfRestClient.add_open_password],
  [change_open_password][pdfrest.PdfRestClient.change_open_password],
  [remove_open_password][pdfrest.PdfRestClient.remove_open_password]
- Digital signatures:
  [sign_pdf][pdfrest.PdfRestClient.sign_pdf]
- Archival/print conformance:
  [convert_to_pdfa][pdfrest.PdfRestClient.convert_to_pdfa],
  [convert_to_pdfx][pdfrest.PdfRestClient.convert_to_pdfx]

## PDF cleanup and rendering normalization

Use this group to improve compatibility, performance, or file size.

- Size and optimization:
  [compress_pdf][pdfrest.PdfRestClient.compress_pdf],
  [linearize_pdf][pdfrest.PdfRestClient.linearize_pdf]
- Flattening:
  [flatten_pdf_forms][pdfrest.PdfRestClient.flatten_pdf_forms],
  [flatten_annotations][pdfrest.PdfRestClient.flatten_annotations],
  [flatten_layers][pdfrest.PdfRestClient.flatten_layers],
  [flatten_transparencies][pdfrest.PdfRestClient.flatten_transparencies]
- Raster and color normalization:
  [rasterize_pdf][pdfrest.PdfRestClient.rasterize_pdf],
  [convert_colors][pdfrest.PdfRestClient.convert_colors]

## Convert into or out of PDF

Use this group when the user starts with non-PDF content or needs downstream
formats.

- Into PDF:
  [convert_office_to_pdf][pdfrest.PdfRestClient.convert_office_to_pdf],
  [convert_postscript_to_pdf][pdfrest.PdfRestClient.convert_postscript_to_pdf],
  [convert_email_to_pdf][pdfrest.PdfRestClient.convert_email_to_pdf],
  [convert_image_to_pdf][pdfrest.PdfRestClient.convert_image_to_pdf],
  [convert_html_to_pdf][pdfrest.PdfRestClient.convert_html_to_pdf],
  [convert_url_to_pdf][pdfrest.PdfRestClient.convert_url_to_pdf]
- Out of PDF:
  [convert_to_word][pdfrest.PdfRestClient.convert_to_word],
  [convert_to_excel][pdfrest.PdfRestClient.convert_to_excel],
  [convert_to_powerpoint][pdfrest.PdfRestClient.convert_to_powerpoint],
  [convert_xfa_to_acroforms][pdfrest.PdfRestClient.convert_xfa_to_acroforms]
- PDF to image:
  [convert_to_png][pdfrest.PdfRestClient.convert_to_png],
  [convert_to_bmp][pdfrest.PdfRestClient.convert_to_bmp],
  [convert_to_gif][pdfrest.PdfRestClient.convert_to_gif],
  [convert_to_jpeg][pdfrest.PdfRestClient.convert_to_jpeg],
  [convert_to_tiff][pdfrest.PdfRestClient.convert_to_tiff]

## Forms data workflows

Use this group when users need to transfer form field values in/out of PDFs.

- Import external form data into a PDF:
  [import_form_data][pdfrest.PdfRestClient.import_form_data]
- Export form data from a PDF:
  [export_form_data][pdfrest.PdfRestClient.export_form_data]

## Async equivalents

For any sync method listed above, use the same method name on
[AsyncPdfRestClient][pdfrest.AsyncPdfRestClient] when your app is async. For
file helpers, use
[AsyncPdfRestFilesClient][pdfrest.AsyncPdfRestFilesClient].
