---
name: pdfrest-client-api
description: Add or compatibly evolve typed PdfRestClient and AsyncPdfRestClient API helpers from a documented PDFCloud-API operation. Use for new endpoints or added endpoint parameters; do not use for unrelated client maintenance.
---

# pdfRest Client API

Implement a documented pdfRest capability as a coherent, forward-compatible
Python SDK API. This skill covers a new helper and a compatible enhancement to
an existing helper, such as an added server parameter.

## Discover the contract first

- Require the PDFCloud-API checkout. Locate it relative to this checkout; do not
  assume a user-specific path.
- Read this repository's `AGENTS.md` and `TESTING_GUIDELINES.md`, then read
  `PDFCloud-API/docs/openapi/openapi-spec.yaml` before editing.
- Treat the OpenAPI operation, schemas, media types, documented errors, and
  async/polling behavior as the public contract. Inspect API source only to
  clarify behavior absent from, or apparently inconsistent with, that contract.
- Do not edit PDFCloud-API unless the user explicitly requests an API-contract
  change.
- Stop and ask the user for direction if the checkout or documented operation is
  missing, a required fixture cannot be obtained, or a compatible SDK adaptation
  cannot be made.

## Public API design

Name a helper for the user outcome, not the path or OpenAPI operation ID.

- Use `snake_case` and lead with a precise action: `convert_`, `add_`,
  `remove_`, `change_`, `flatten_`, `extract_`, `query_`, `preview_`, `apply_`,
  `merge_`, `split_`, `zip_`, or `unzip_`.
- Name the material source/result or effect: `convert_html_to_pdf`,
  `add_text_to_pdf`, and `merge_pdfs`. Include both sides of a conversion.
- Split kitchen-sink routes into distinct helpers when source type, output,
  validation, or user workflow differs. `/pdf` correctly maps to helpers such as
  `convert_office_to_pdf`, `convert_html_to_pdf`, and `convert_url_to_pdf`, not
  one mode-driven endpoint wrapper.
- Use a qualifier only when it changes the contract or workflow, such as
  `preview_redactions` then `apply_redactions`, or text versus image
  watermarking.
- Preserve all existing public method names. Do not rename a method merely to
  fit this standard.

Keep the upload lifecycle separate from execution:

- Upload with `client.files.create*` first. Processing helpers accept uploaded
  `PdfRestFile` resources (or typed sequences/compound inputs containing them),
  never local paths, bytes, multipart values, or exposed raw `PdfRestFileID`s.
- Apply the same rule to optional assets such as profiles, attachments,
  certificates, and merge sources.
- Add matching methods with the same name and contract to `PdfRestClient` and
  `AsyncPdfRestClient`; async behavior differs only by awaiting the operation.

## Compatibility for existing helpers

Before modifying an existing method, compare its signature, defaults, accepted
input shapes, validation behavior, return model, documentation, and serialized
body to the current API contract.

- Preserve existing caller behavior. Additive parameters must be optional, have
  a safe backward-compatible default, and be supported by both transports.
- Do not change positional meaning, narrow accepted types, alter established
  defaults, remove arguments, or change response shapes as part of an API
  adaptation.
- If the server requires a breaking SDK change and no faithful compatible
  translation/default exists, stop and ask the user for a migration decision
  before editing.

## Model-first validation and transformation

Public methods provide Python-friendly inputs; a Pydantic payload model owns
validation and turns them into the exact pdfRest wire contract.

- Create or extend one payload model in `src/pdfrest/models/_internal.py` that
  mirrors the server request field-for-field. Keep reusable public type aliases
  in `src/pdfrest/types/`.
- Keep client methods thin: assemble a payload dict and call
  `_post_file_operation(..., payload_model=...)`. Do not duplicate payload
  validation in the client.
- Use native annotated constraints, literals, and length bounds first. Use
  `BeforeValidator` to adapt friendly input shapes, `AfterValidator` for MIME
  and relational validation, and small field serializers for server formatting.
- Use `validation_alias` for accepted SDK input names and `serialization_alias`
  for the server field name. Serialize uploaded `PdfRestFile` values to the
  required ID field with the existing serializers.
- Validate MIME types and resource cardinality before a request. For payload
  validation failures, raise Pydantic `ValidationError` via `ValueError` or
  `AssertionError`, not `TypeError`.
- Use `model_validator(mode="before")` only to map a friendlier compound input
  onto existing API fields. Do not introduce a payload `@model_serializer`; use
  field serializers and declarative nested models instead.
- Serialize through Pydantic with
  `model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)`,
  not ad hoc JSON encoding.
- Validate the raw response, resolve output IDs to `PdfRestFile` metadata, and
  return the appropriate typed response model.

## Tests and documentation

Follow `TESTING_GUIDELINES.md` and the live-test requirements in `AGENTS.md`.

- Add or extend the endpoint's focused unit module under `tests/` and a matching
  endpoint module under `tests/live/`. Do not put endpoint coverage into a
  generic catch-all file.
- Write distinct sync and async tests for each important path; do not conceal
  transport parity behind parametrization.
- Unit tests use `httpx.MockTransport` to assert method, path, headers, exact
  Pydantic-produced request body, response mapping, request customization, and
  timeout propagation. For local-invalid input, configure the transport to fail
  if called.
- Test payload models directly as well as client methods: accepted ergonomic
  shapes and the exact alias-based serialization must both be covered.
- Cover default and non-default options, accepted literals, numeric bounds,
  MIME/cardinality/dependency rules, and every meaningful response attribute.
  Extend a shared validation suite when a rule applies to a model family.
- Live tests upload deterministic fixtures first, execute with the returned
  `PdfRestFile` resources, and assert IDs, filenames, MIME types, output count,
  warnings, and endpoint-specific behavior. Use `extra_body` or `extra_query` to
  reach and assert server-side negative validation.
- Update the API guide, public exports, and user-facing examples when the new
  capability or parameter changes discoverability or usage.

Run targeted unit and live tests first, then the relevant Ruff and type checks.
Run the full pytest suite and `uvx nox -s tests` when practical. Report the
OpenAPI operation inspected, files changed, checks run, checks skipped, and any
live-validation limitation.
