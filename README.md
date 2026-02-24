# pdfRest Python SDK

[![Tests](https://img.shields.io/github/actions/workflow/status/pdfrest/pdfrest-python/test-and-publish.yml?branch=main&label=tests)](https://github.com/pdfrest/pdfrest-python/actions/workflows/test-and-publish.yml)
[![PyPI Version](https://img.shields.io/pypi/v/pdfrest)](https://pypi.org/project/pdfrest/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pdfrest)](https://pypi.org/project/pdfrest/)
[![llms.txt](https://img.shields.io/badge/llms.txt-available-2ea44f)](https://python.pdfrest.com/llms.txt)

Build production-grade PDF automation with the official Python SDK for
[pdfRest](https://pdfrest.com/): a powerful PDF API platform for conversion,
OCR, extraction, redaction, security, forms, and AI-ready document workflows.

- Homepage: [pdfrest.com](https://pdfrest.com/)
- API docs: [docs.pdfrest.com](https://docs.pdfrest.com/api-reference-guides/directory/)
- Python SDK docs: [python.pdfrest.com](https://python.pdfrest.com/)
- API Lab: [pdfrest.com/apilab](https://pdfrest.com/apilab/)

## Why pdfRest

- Enterprise PDF quality powered by Adobe PDF Library technology.
- Fast onboarding with API Lab, code samples, and straightforward REST patterns.
- Chainable API workflows that let you pass outputs between calls.
- Deployment flexibility: Cloud, self-hosted on AWS, or self-hosted container.
- Security and compliance resources published in the trust center and product
  documentation.

## Why this SDK

- Official typed Python interface to pdfRest (`PdfRestClient` and
  `AsyncPdfRestClient`).
- Pydantic-backed request/response models for safer integrations.
- High-level helpers for the endpoints teams use most in production.
- Consistent error handling, request customization, and file management helpers.

## What you can build

Use this PDF API for workflows like:

- Convert and transform: PDF to Word/Excel/PowerPoint/images/Markdown, and
  convert files to PDF/PDF-A/PDF-X.
- Extract and analyze: OCR, text extraction, image extraction, PDF metadata.
- Secure and govern: redaction, encryption, permissions, signing, watermarking.
- Compose and optimize: merge/split, compress, flatten, rasterize, color
  conversion.
- Form operations: import/export form data, flatten forms, XFA to Acroforms.

## Built for AI and LLM pipelines

pdfRest is especially useful for document AI systems:

- Convert PDFs to structured Markdown for downstream retrieval and training data
  prep.
- Extract clean text and metadata for indexing and chunking pipelines.
- Summarize and translate document content with API-native operations.
- Keep multi-step pipelines efficient by chaining outputs between operations.

## Installation

`pdfrest` supports Python `3.10+`.

Recommended (`uv`):

```bash
uv add pdfrest
```

Fallback (`pip`):

```bash
pip install pdfrest
```

## Quick start

Set your API key in `PDFREST_API_KEY`:

```bash
export PDFREST_API_KEY="your-api-key"
```

Run your script:

```bash
uv run python your_script.py
```

Example (upload + extract text):

```python
from pathlib import Path

from pdfrest import PdfRestClient

with PdfRestClient() as client:
    uploaded = client.files.create_from_paths([Path("input.pdf")])[0]
    result = client.extract_pdf_text(uploaded, full_text="document")

preview = ""
if result.full_text is not None and result.full_text.document_text is not None:
    preview = result.full_text.document_text[:500]
print(preview)
```

Async example:

```python
import asyncio
from pathlib import Path

from pdfrest import AsyncPdfRestClient


async def main() -> None:
    async with AsyncPdfRestClient() as client:
        uploaded = (await client.files.create_from_paths([Path("input.pdf")]))[0]
        result = await client.extract_pdf_text(uploaded, full_text="document")
        preview = ""
        if result.full_text is not None and result.full_text.document_text is not None:
            preview = result.full_text.document_text[:500]
        print(preview)


asyncio.run(main())
```

## Deployment options

- Cloud (default): use `PdfRestClient()` with `PDFREST_API_KEY`.
- Self-hosted: set `base_url="https://your-api-host"` and keep the same Python
  SDK surface.

## Learn more

- API toolkit overview: [pdfrest.com](https://pdfrest.com/)
- Resources and insights:
  [pdfrest.com/resources](https://pdfrest.com/resources/)
- Example scripts: `examples/README.md`
- Python SDK docs: [python.pdfrest.com](https://python.pdfrest.com/)

## For contributors

Contributor workflows live in `CONTRIBUTING.md`.
