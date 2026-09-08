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

## Jira branch setup

When the prompt handed to this skill mentions a Jira work item, create a branch
before making substantive edits.

- Derive the name as `pdfcloud-<number>-<short-description>`, using the Jira key
  lowercased and a concise lowercase, hyphen-separated description. For example,
  `PDFCLOUD-6233 Add PDF outlines` becomes `pdfcloud-6233-add-pdf-outlines`.
- Use `upstream/main` as the branch's upstream when an `upstream` remote exists.
  If `origin` is the only remote, use `origin/main` instead. Do not silently
  select a fork remote when another remote configuration is ambiguous.
- When HEAD is attached, create the branch from the current commit, then set its
  upstream explicitly with `git branch --set-upstream-to=<remote>/main`.
- When HEAD is detached, first fetch the selected remote's `main` branch, then
  create the branch from `<remote>/main` and set that same ref as its upstream.
- Do not overwrite an existing branch or discard local changes. Stop and ask the
  user for direction if the derived name already exists or the remote/main ref
  cannot be resolved.

## Public API design

Name a helper for the user outcome, not the path or OpenAPI operation ID.

### Decide helper granularity with an applicability matrix

Before choosing one helper or several, derive a matrix from the OpenAPI
contract. Use one row per user-recognizable source type or workflow and record:

- accepted MIME types and filename extensions;
- required inputs and resource cardinality;
- optional fields, classified as universal, subset-only, or variant-exclusive;
- output/response shape and any materially different validation or lifecycle.

Prefer focused helpers when the caller knows the source/workflow before the call
and a combined signature would expose keywords that are invalid for some rows,
depend on a mode or file type for their meaning, require extensive cross-field
runtime rejection, or prevent the type checker/editor from showing the valid
option set. Distinct file-family validation or a meaningful cluster of
row-specific options is strong evidence for a split. The fact that variants
share an HTTP path, OpenAPI operation, or nested wire object is not evidence
that they should share a public helper.

Keep one helper when the rows share one coherent input contract and outcome and
nearly all options apply uniformly. A single helper can also be appropriate when
a natural discriminated `TypedDict`/model union expresses each variant without a
kitchen-sink keyword signature and static typing rejects invalid combinations.
Do not add a synthetic mode discriminator merely to avoid naming clear user
workflows.

When splitting, keep universal keywords and request-customization arguments
consistent across helpers, reuse internal base/nested models for common wire
fields, and give each helper a narrow payload model for its applicable options
and file-family validation. Add tests proving every helper rejects the other
families before transport and never serializes an option that is inapplicable to
its row.

## Versioning new APIs

Adding a public API is a feature release and requires a minor-version bump.
Before editing, compare `pyproject.toml` with the current branch's base and
commits:

- If this branch has not changed the project version, increment the minor
  version and reset the patch component to `0` with `uv version --bump minor`.

- If this branch includes only a patch-version change, replace that patch bump
  with the appropriate next minor version and reset the patch component to `0`
  with `uv version --bump minor`.

- If the branch already includes the required minor-version bump, retain it. Do
  not make a major-version change unless the user explicitly requests one.

- Use `snake_case` and lead with a precise action: `convert_`, `add_`,
  `remove_`, `change_`, `flatten_`, `extract_`, `query_`, `preview_`, `apply_`,
  `merge_`, `split_`, `zip_`, or `unzip_`.

- Name the material source/result or effect: `convert_html_to_pdf`,
  `add_text_to_pdf`, and `merge_pdfs`. Include both sides of a conversion.

- Split kitchen-sink routes according to the applicability-matrix decision
  above. `/pdf` correctly maps to helpers such as `convert_office_to_pdf`,
  `convert_html_to_pdf`, and `convert_url_to_pdf`, not one mode-driven endpoint
  wrapper.

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
- When one semantic color is represented by separate RGB/CMYK wire fields,
  expose a single public `<name>_color: PdfColor` input. Route it by tuple
  channel count with a `BeforeValidator` on internal RGB/CMYK fields that share
  the public `validation_alias` but have distinct serialization aliases. Do not
  expose the server's `*_rgb` or `*_cmyk` field names in public methods or
  TypedDicts.
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
- For unified color inputs, assert RGB and CMYK tuples each serialize to only
  their corresponding wire field, and reject unsupported channel counts before a
  request is sent.
- Cover default and non-default options, accepted literals, numeric bounds,
  MIME/cardinality/dependency rules, and every meaningful response attribute.
  Extend a shared validation suite when a rule applies to a model family.
- Treat each public text `Literal` as both a documentation and test contract.
  Give its `TypeAlias` a PEP 258 docstring immediately after the assignment:
  explain the option, then provide an `Accepted values:` Markdown list with one
  bullet per literal spelling and its user-visible meaning. Derive those
  meanings from the OpenAPI contract or verified server behavior. Parameterize
  every accepted spelling with a readable test ID in payload tests and in
  distinct sync and async client tests; matching live tests must send every
  spelling through both transports. Do not use one representative happy path.
  Add an invalid spelling through `extra_body` when a server-side rejection must
  be demonstrated. This is the evidence expected by `pr-review-auditor`.
- For a payload containing a discriminated JSON-object union, add a direct
  serialization assertion for every discriminator and distinct sync/async client
  tests that send each form. Parameterize all `ge`/`gt`/`le`/`lt` constraints at
  their legal boundaries and immediately-invalid neighbors. Test MIME and
  one-resource cardinality failures through both clients with a transport that
  fails if a request is attempted. In both timeout-customization tests, capture
  `request.extensions["timeout"]` and assert every component.
- When optional per-object metadata requires a request-level flag, cover both
  the valid dependency combination and the locally rejected missing/false flag;
  use `extra_body` in live tests to verify an invalid combination reaches the
  server and raises the expected API exception.
- Live tests upload deterministic fixtures first, execute with the returned
  `PdfRestFile` resources, and assert IDs, filenames, MIME types, output count,
  warnings, and endpoint-specific behavior. Use `extra_body` or `extra_query` to
  reach and assert server-side negative validation.
- Update the API guide, public exports, and user-facing examples when the new
  capability or parameter changes discoverability or usage.

### Runnable example requirement

Every new public endpoint/helper requires a runnable example; it is part of the
API deliverable, not optional follow-up documentation. For a compatible change
to an existing helper, extend or add an example when the new parameter changes a
user workflow or demonstrates behavior that is not otherwise discoverable.

- Before creating the example, identify every input asset it needs and inspect
  `examples/resources/` for a suitable deterministic, redistributable fixture.
  If any required file is absent, ask the user to provide it, naming the needed
  file type and relevant characteristics (for example, a signed PDF, a
  multi-page TIFF, a font, or a profile JSON). Do not fabricate, download, or
  substitute a semantically unsuitable input. Stop if a required fixture cannot
  be obtained.

- Add one endpoint-oriented script at
  `examples/<capability>/<descriptive_name>_example.py` and list it in
  `examples/README.md`. Reuse checked-in assets via a path derived from
  `Path(__file__)`; place an approved new shared asset under
  `examples/resources/`.

- Start the script at line one with the repository's single-line PEP 723 header:

  ```python
  # /// script
  # requires-python = ">=3.10"
  # dependencies = ["pdfrest", "python-dotenv"]
  # ///
  ```

  Adjust the Python constraint and declare every third-party import. Do not add
  a shebang before the metadata. Inline metadata isolates `uv run` from the
  project environment, and `noxfile.py` parses this exact line-one structure.

- Immediately follow the header with a module docstring that explains the user
  outcome, enumerates the upload/API/result steps, names `PDFREST_API_KEY` and
  all input prerequisites, and provides the repository-root command
  `uv run examples/<capability>/<descriptive_name>_example.py`.

- Use the public SDK exactly as a customer would: load the API key environment,
  enter the sync or async client context manager, upload local assets first,
  call the new helper with `PdfRestFile` values, and print concise,
  endpoint-relevant response details. Keep it deterministic, repeatable, and
  independent of third-party URLs.

- When a public `TypedDict` represents a structured API input, construct it in
  examples with its keyword constructor, such as `PdfAddLineObject(...)`,
  instead of an anonymous dictionary literal. Annotate heterogeneous collections
  with the public union alias, such as `list[PdfAddShapeObject]`. Reserve
  dictionary literals for dynamic data, intentionally invalid input, and raw
  wire-format overrides.

- Use `python-X.Y/<same_name>.py` plus an extending `ruff.toml` only when an
  older interpreter needs a distinct implementation. Otherwise keep one script
  compatible across the supported range.

- Validate the example against the local checkout with
  `uvx nox -s run-example -- examples/<capability>/<script>.py`. When practical,
  run `uvx nox -s examples` to cover Python 3.10-3.14; direct
  `uv run examples/<capability>/<script>.py` is also required once the published
  `pdfrest` release contains the new API.

### Generated API-reference contracts

The API reference is generated from the public source. Keep request-shape
documentation with its types; do not hand-copy a shape schema into Markdown.

- For every public `TypedDict` accepted by a client helper, write a Google-style
  `Attributes:` docstring that explains every field: required versus optional
  status, accepted values, units or coordinate origin where relevant, declared
  bounds, and any request-level dependency. Derive those details from the
  Pydantic payload model and OpenAPI contract; do not guess missing behavior.
- For a public union alias, declare it as `Name: TypeAlias = ...` and add its
  PEP 258 attribute docstring immediately after the assignment. The docstring
  must identify the union members and link to the consuming client helper.
- For a public text `Literal` alias, use the same immediate PEP 258 docstring
  placement and an `Accepted values:` list whose bullets document each literal
  spelling and meaning. Inspect generated HTML to confirm the list renders with
  the alias rather than only in the source file.
- Public types are re-exported through `pdfrest.types`. Verify that the rendered
  reference resolves the re-export to its source union and member types. A
  self-reference such as `PdfAddShapeObject = PdfAddShapeObject` is a rendering
  defect, not acceptable documentation.
- Do not enable broad rendering of undocumented module attributes merely to
  expose a public alias. That also exposes convenience constants such as
  `ALL_*`, which are not API-reference contracts. Document the alias at its
  source instead.
- Build the docs with `uv run mkdocs build --strict`. For a newly documented
  union or structured input, inspect the generated API-reference HTML (or make
  an equivalent focused assertion) to confirm the union members, its docstring,
  and field-level descriptions render; links from the client method signature
  must target that entry.

Run targeted unit and live tests first, then the relevant Ruff and type checks.
Run the full pytest suite and `uvx nox -s tests` when practical. For API
reference changes, also run the strict docs build. Run the focused example and
the example matrix as described above. Report the OpenAPI operation inspected,
files changed, checks run, checks skipped, and any live-validation limitation.
