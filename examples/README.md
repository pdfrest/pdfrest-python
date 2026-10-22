# Examples

Each example script includes [PEP 723](https://peps.python.org/pep-0723/)
metadata so `uv` can create a disposable environment and install the script's
dependencies without touching the project-wide virtualenv. Run them directly
with `uv run` instead of relying on `--project` mode:

```bash
# Default (Python 3.11+)
uv run examples/delete/delete_example.py

# Version-specific overrides
uv run --python 3.10 examples/delete/python-3.10/delete_example.py
```

The commands above read `PDFREST_API_KEY` from your environment (you can manage
that via `.env` if desired), upload the checked-in sample assets under
`examples/resources/`, and exercise the async client end-to-end. Use
`uvx nox -s examples` when you want to execute every example across the
supported interpreter matrix.

## Available Examples

- `examples/add_shapes/add_shapes_to_pdf_example.py` – add a styled rectangle
  and divider line to a PDF with accessibility tagging enabled.
- `examples/convert_structured_documents/convert_structured_documents_to_pdf_example.py`
  – convert Markdown, plain text, JSON, XML, and CSV documents to PDF with
  format-specific options.
- `examples/convert_postscript_to_pdf/convert_postscript_with_job_options_example.py`
  – convert PostScript to PDF with an uploaded custom `.joboptions` profile.
- `examples/convert_to_image/convert_password_protected_pdf_to_png_example.py` –
  convert a password-protected PDF into PNG images by supplying its open
  password.
- `examples/convert_pdf_to_postscript/convert_pdf_to_postscript_example.py` –
  synchronously convert selected PDF pages and verify the PostScript output.
- `examples/convert_pdf_to_postscript/async_convert_pdf_to_postscript_example.py`
  – asynchronously convert a PDF page and verify the PostScript output.
- `examples/delete/delete_example.py` – demonstrate file deletion (sync + async
  variants).
- `examples/extract_text/extract_pdf_text_example.py` – run `extract_pdf_text`
  with word coordinates/style enabled and render the output as a Rich table.
