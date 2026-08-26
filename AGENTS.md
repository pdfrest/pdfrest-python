# Repository Guidelines

## Project Structure & Module Organization

- Source lives in `src/pdfrest/`; expose public APIs via `__all__` and keep
  package metadata in `pyproject.toml`.
- Tests sit in `tests/` mirroring the module layout (e.g.,
  `tests/test_client.py`).
- Workflow definitions are in `.github/workflows/`; adjust only when CI
  requirements change.
- Contributor notes reside at the repo root (`README.md`, `AGENTS.md`), while
  the documentation site content lives in `docs/`. Automation sessions live in
  `noxfile.py`; keep shared task logic there.

## Build, Test, and Development Commands

- `uv sync --group dev` — create/update the virtual environment with lint,
  type-check, and test tooling.
- `uv run pre-commit run --all-files` — enforce formatting and lint rules before
  pushing.
- `uv run pytest` — execute the suite with the active interpreter.
- `uv build` — produce wheels and sdists identical to the release workflow.
- `uv version --bump <major|minor|patch>` — update the project version; use this
  command instead of editing the version manually in `pyproject.toml`.
- `uvx nox -s tests` — create matrix virtualenvs via nox and execute the pytest
  session.
- `nox` executes pytest sessions with built-in parallelism; when invoking pytest
  directly use `pytest -n auto --maxschedchunk 2` to mirror the parallel test
  scheduling and keep runtimes predictable.
- Coverage reports (XML/Markdown/HTML) are produced by the nox `tests` session
  and stored under `coverage/py<version>/` (for example,
  `coverage/py3.12/coverage.xml`, `coverage/py3.12/coverage.md`,
  `coverage/py3.12/html/`).

## Code Quality Checklist

- When code changes are complete, or when asked to "check code quality", run
  this default sequence:
  - `uv run ruff format .`
  - `uv run ruff check .`
  - `uv run basedpyright`
- Do not include pytest or nox runs in the default "code quality" request; treat
  runtime tests as a separate validation step.

## Test Validation Checklist

- Run tests separately from code quality checks:
  - `uv run pytest -n auto --maxschedchunk 2` (or a focused module when
    iterating)
- For full compatibility before handoff/PR, run:
  - `uvx nox -s tests` (Python 3.10-3.14 matrix + coverage artifacts)
- For class-function coverage gate validation (when relevant to client changes),
  run:
  - `uv run python scripts/check_class_function_coverage.py coverage/py<version>/coverage.json --fail-under 90 --class PdfRestClient --class AsyncPdfRestClient --class _FilesClient --class _AsyncFilesClient`
- Always report:
  - files changed
  - tests/checks run and not run
  - why any checks were skipped

## Coding Style & Naming Conventions

- Target Python 3.10–3.14; use 4-space indentation and type hints for public
  APIs.
- Black + isort (via ruff) enforce formatting; run through pre-commit prior to
  review.
- Use `snake_case` for functions/modules, `PascalCase` for classes, and
  `UPPER_SNAKE_CASE` for constants.
- Prefer `pathlib`, f-strings, and other modern stdlib features—pyupgrade rules
  will flag legacy code.
- When calling pdfRest, supply the API key via the `Api-Key` header (not
  `Authorization: Bearer`); keep tests and client defaults in sync with this
  convention.
- Avoid `@field_validator` on payload models. Prefer existing `BeforeValidator`
  helpers (e.g., `_allowed_mime_types`) so validation remains declarative and
  consistent across schemas.
- In Pydantic validators, raise `ValueError`/`AssertionError` (or
  `PydanticCustomError` when needed), not `TypeError`, so callers consistently
  receive `ValidationError` surfaces.
- Keep user-facing `PdfRestClient` and `AsyncPdfRestClient` endpoint helpers
  thin: they should primarily assemble payload dicts and delegate validation to
  payload models (`model_validate`). Avoid duplicating payload validation in
  client methods or raising configuration errors for payload-shape issues that
  Pydantic validators can enforce.
- Prefer Pydantic-backed JSON serialization for performance: use
  `model_dump_json()` for Pydantic models, and use `pydantic_core.to_json()` for
  non-model payloads instead of `json.dumps()` where practical.
- Treat `PdfRestClient` and `AsyncPdfRestClient` as context managers in both
  production code and tests so transports are disposed deterministically.
- When uploading content, always send the multipart field name `file`; when
  uploading by URL, send a JSON payload using the `url` key with a list of
  http/https addresses (single values are promoted to lists internally).
- Always upload local assets before invoking an endpoint helper. Public client
  APIs must accept `PdfRestFile` objects (or sequences) rather than raw paths or
  ids, including optional resources such as compression profiles. Never expose
  `PdfRestFileID` in the interface—callers should upload the profile JSON, get
  the resulting `PdfRestFile`, then pass that object into helpers like
  `compress_pdf`.
- When an endpoint supports both an inline upload parameter and an `*_id`
  variant, ignore the upload form and expose only the base parameter (without
  `_id`) typed as `PdfRestFile`. Serialize via `_serialize_as_first_file_id`
  with `serialization_alias` pointing to the server’s `*_id` field so requests
  always reference already-uploaded resources.
- `prepare_request` rejects mixed multipart (`files`) and JSON payloads; only
  URL uploads (`create_from_urls`) should combine JSON bodies with the request.
- Replicate server-side safeguards when porting validation logic: the output
  prefix must stay basename-only, reject reserved names (`profile.json`,
  `metadata.json`), forbid leading dots or special characters, and report the
  offending characters in error messages. Page-range validation operates on each
  list item individually—accepts positive integers, `last`, or ranges like
  `1-3`/`6-last`—and must raise errors that match the front-end wording.
- Combine multiple synchronous context managers in a single `with` statement
  (ruff enforces `SIM117`). When an async context manager participates (e.g.,
  `async with AsyncPdfRestClient(...)`), nest any synchronous companions such as
  `pytest.raises` inside the async block—Python forbids mixing `async with` and
  regular `with` clauses in the same statement. When working with `HttpUrl`
  objects, cast to `str` before string operations such as suffix checks. *When
  using `pytest.raises`, prefer combining it into the same `with` clause as
  another synchronous context manager when semantics allow.*
- For image conversions, adapt request data with `BasePdfRestGraphicPayload`
  generics; name concrete payloads `BmpPdfRestPayload`, `GifPdfRestPayload`,
  `JpegPdfRestPayload`, `PngPdfRestPayload`, and `TiffPdfRestPayload`. Client
  helpers should accept a `payload_model` argument and use fully spelled-out
  method names such as `convert_to_jpeg`/`convert_to_tiff` (avoid historic
  three-letter suffixes).
- Define reusable literals and simple aliases under `src/pdfrest/types/` and
  import them from `pdfrest.types` (e.g., `PdfInfoQuery`) instead of reaching
  into underscored modules. Treat that package as the public surface for shared
  type contracts consumed by both clients and tests.
- Payload models that reference uploaded resources should accept
  `list[PdfRestFile]` with explicit length bounds and serialize IDs for the
  allowed cardinality (`serialization_alias="id"` plus a serializer that emits
  either the first id when `max_length == 1` or a list when larger). Client
  helpers should pass sequences through without converting to raw IDs manually.
- When a payload accepts uploaded content, validate MIME types via
  `_allowed_mime_types` to surface clear errors before making the request.
- Payload models should mirror pdfRest's request layout field-for-field. Do not
  use `@model_serializer` on payload models. If callers need a friendlier input
  shape, use `@model_validator(mode="before")` to map inputs onto the existing
  pdfRest fields, and keep any wire formatting in field serializers.
- When an endpoint expects JSON-encoded structures (e.g., arrays of redaction
  rules), expose typed arguments (TypedDicts, Literals, etc.) via
  `pdfrest.types` and let the payload serializer produce the JSON string for the
  request body.
- Client helpers that consume existing resources must accept `PdfRestFile`
  instances (optionally sequences) rather than raw IDs or strings; use the
  `files` client helpers to resolve file IDs before invoking conversion or
  metadata routes.
- For document splitting and merging, expose rich Python types on the client
  surface (`PdfPageSelection`, `PdfMergeInput`) and validate them through the
  `PdfSplitPayload`/`PdfMergePayload` models. Normalize per-output page groups
  with the shared page-range validator, default merge items without explicit
  ranges to `"1-last"`, and serialize merge requests into the parallel `id`,
  `pages`, and `type` arrays that pdfRest expects (always emitting `"id"` for
  `type[]`). Split/merge payloads accept descending ranges (e.g., `"9-2"`) and
  the `"even"`/`"odd"` selectors; graphic conversions remain limited to positive
  numbers, `"last"`, and ascending ranges to match the live API behaviour.
- Favor declarative Pydantic validation over bespoke “normalize” helpers: define
  nested models, unions, and annotated tuples that parse complex strings into
  typed structures (as with the split/merge page-range tuples) and let small
  validators enforce the constraints (`BeforeValidator` for parsing,
  `AfterValidator` for relational checks). Reserve standalone normalization
  functions for behaviour that cannot live on the schema—simpler models produce
  clearer errors and are easier for new contributors to understand.
- When `Annotated` field constraints (for example tuple length and `ge`/`le`
  bounds) fully capture an input contract, prefer those native constraints over
  redundant custom validators that only restate the same rules.
- Prefer the newer add-text color pattern over legacy helper-style validation:
  `_validate_rgb_values` / `_validate_cmyk_values` were replaced by tuple
  channel aliases (`RgbChannel`/`CmykChannel`) plus field constraints and should
  remain the default approach. Add custom validators only when they provide
  behavior native constraints cannot (for example, parsing alternate wire
  formats or enforcing cross-field dependencies).
- When pdfRest exposes separate RGB/CMYK wire fields for one semantic color,
  expose one public `<name>_color: PdfColor` input instead of separate
  `<name>_color_rgb`/`<name>_color_cmyk` inputs. Use a channel-count
  `BeforeValidator` with shared `validation_alias` and distinct serialization
  aliases to route three channels to RGB and four to CMYK; keep those wire-field
  names internal to the payload model.
- Keep `BeforeValidator`/`AfterValidator` helpers and field serializers short
  and shape-focused. They should primarily adapt nonconforming inputs or handle
  pdfRest wire quirks (for example, splitting comma-separated values or
  serializing only the first uploaded file ID), not re-implement constraint
  logic already expressed by Pydantic field types/annotations.
- For demo/free-tier redactions, favor parseable-but-useless replacements over
  reconstructing likely true values. The SDK should remain operable (no parsing
  crashes) while preserving demo mode’s intent of withholding useful output
  fidelity.
- Prefer reusable validator factories that take parameters (for example
  allowed-value/extension helpers with keyword-configured fallbacks) over
  bespoke one-off validator functions tied to a single field.
- When adding new services, provide per-endpoint test modules mirroring PNG’s
  coverage: parameterized successes for every allowed literal value, request
  customization (sync + async), validation failures, and multi-file guards. Add
  a shared validation suite when multiple endpoints rely on the same input rules
  (e.g., `tests/test_graphic_payload_validation.py`).
- Do not import from private modules (names beginning with an underscore) in
  production code. In tests, prefer public modules first; allow private-model
  imports only when necessary to validate request serialization or mock
  server-facing payload contracts that are not exposed publicly.

## Testing Guidelines

- **Live Test Requirement (Do Not Skip):** Every new endpoint or service must
  ship with a matching live pytest module under `tests/live/` before the work is
  considered complete. Mirror the naming/structure used by the graphic
  conversion suites: one module per endpoint, parameterized success cases that
  enumerate all accepted literals, at least one invalid input that hits the
  server, and coverage for server-observable endpoint options. Validate
  `extra_query`/`extra_headers`/`extra_body`/`timeout` plumbing in unit tests
  (MockTransport) unless a live assertion depends on those options. If an
  endpoint cannot be exercised live, call that out explicitly in the PR
  description with the reason and the follow-up plan; otherwise reviewers should
  block the change. Treat this as a release gate on par with unit tests.

- **Client coverage criteria:** `PdfRestClient` and `AsyncPdfRestClient` are
  customer-facing entry points and must retain high coverage. Every public
  client method must have at least one unit test that exercises the REST call
  path (MockTransport + request assertions), with distinct sync and async tests.
  Optional payload branches (`pages`, `output`, `rgb_color`, etc.) need explicit
  coverage so serialization regressions are caught.

- **Class function coverage scope:** The class coverage gate targets the main
  client-facing classes (`PdfRestClient`, `AsyncPdfRestClient`, `_FilesClient`,
  `_AsyncFilesClient`). For these classes, underscore-prefixed methods are
  intentionally in scope and should be covered as part of the interface
  contract.

- Write pytest tests: files named `test_*.py`, test functions `test_*`, fixtures
  in `conftest.py` where shared.

- Follow ruff’s SIM117 rule: when combining context managers (e.g., a client and
  `pytest.RaisesGroup`), use a single `with (...)` statement instead of nesting
  them to keep tests idiomatic and lint-clean.

- Cover both client transports in every new test module (unit and live suites):
  add distinct test cases (not parameterized branches) that exercise each
  assertion through `PdfRestClient` and `AsyncPdfRestClient` so sync/async
  behaviour stays independently verifiable.

- For endpoints that accept discriminated JSON objects, test every discriminator
  through both client transports and assert the model's exact JSON-ready
  serialization directly. Parameterize each constrained field at its accepted
  boundaries and immediately outside them; test MIME and single-resource
  cardinality failures through both transports with a transport that fails if
  local validation does not short-circuit. When a helper accepts `timeout`,
  capture `request.extensions["timeout"]` in both customization tests and assert
  every timeout component.

- When endpoints may raise `PdfRestErrorGroup` (or any future pdfRest-specific
  exception groups), assert them with `pytest.RaisesGroup`/`pytest.RaisesExc`,
  and use the `check=` hook to confirm the outer group is the expected class so
  each inner error is validated individually rather than matching the group
  message alone.

- Ensure high-value coverage of public functions and edge cases; document intent
  in test docstrings when non-obvious.

- Use `uvx nox -s tests` to exercise the full interpreter matrix locally when
  validating compatibility.

- When writing live tests for URL uploads, first create the remote resources via
  `create_from_paths`, then reuse the returned URLs in `create_from_urls` to
  avoid relying on third-party availability.

- For parameterized tests prefer `pytest.param(..., id="short-label")` so test
  IDs stay readable; make assertions for every relevant response attribute (name
  prefix, MIME type, size, URLs, warnings).

- Avoid manual loops over test parameters; prefer `@pytest.mark.parametrize`
  with explicit `id=` values so each combination is visible and reproducible.

- Always couple `pytest.raises` with an explicit `match=` regex. For SDK-owned
  validation messages, mirror the human-readable wording; for native Pydantic
  constraint errors, match stable fragments (field path + core bound/type
  phrase) rather than brittle full-text output.

- Mirror PNG’s request/response scenarios for each graphic conversion endpoint:
  maintain per-endpoint test modules (`test_convert_to_png.py`,
  `test_convert_to_bmp.py`, etc.) covering success, parameter customization,
  validation errors, multi-file guards, and async flows. Keep shared payload
  validation (output prefix and page-range cases) in a dedicated suite (e.g.,
  `tests/test_graphic_payload_validation.py`) that exercises every payload
  model.

- When introducing additional pdfRest endpoints, follow the same pattern used
  for graphic conversions: encapsulate shared request validation in a typed
  payload model, expose fully named client methods, and create a dedicated test
  module per endpoint that verifies success paths, request customization,
  validation errors, and async behavior. Centralize any reusable validation
  checks (e.g., common field requirements, payload serialization) in shared
  helper tests so new services inherit consistent coverage with minimal
  duplication.

- Prefer `pytest.mark.parametrize` (with `pytest.param(..., id="...")`) over
  explicit loops or copy/paste blocks—if only the input value or expected error
  changes, parameterize it so failures point to the exact case and reviewers
  don’t have to diff almost-identical code. Nest parametrization for
  multi-dimensional coverage so each combination appears as its own test item.

- Live tests should verify that literal enumerations match pdfRest’s accepted
  values. Exercise format-specific options (e.g., each image format’s
  `color_model`) individually, and run smoothing enumerations through every
  enabled endpoint to confirm consistent server behaviour. Include “wildly”
  invalid values (e.g., bogus literals or mixed lists) alongside boundary
  failures so the server-side error messaging is exercised.

- Provide live integration tests under `tests/live/` (with an `__init__.py` so
  pytest discovers the package) that introspect payload models to enumerate
  valid/invalid literal values and numeric boundaries. These tests should vary a
  single parameter per request, assert success for legal inputs, and confirm
  pdfRest raises errors for out-of-range or unsupported values. When bypassing
  local validation to reach the server (e.g., for negative tests), inject the
  override via `extra_body` and expect `PdfRestApiError` (or the precise
  exception surfaced by the client). When test fixtures produce deterministic
  results (e.g., `tests/resources/report.pdf`), assert the concrete values
  returned by pdfRest rather than only checking for presence or type.

- Use `tests/resources/20-pages.pdf` for high-page-count scenarios such as split
  and merge endpoints so boundary coverage (multi-output splits, staggered page
  selections) remains reproducible. Parameterize live split/merge tests to cover
  multiple page-group patterns, and pair each success case with an invalid input
  that reaches the server by overriding the JSON body via `extra_body`.

- Developers can load a pdfRest API key from `.env` during ad-hoc exploration.
  The repo includes `python-dotenv`; call `load_dotenv()` (optionally pointing
  to `.env`) in temporary scripts to drive the in-flight client against live
  endpoints and capture responses for test data and assertions.

## Example Guidelines

- Every new public endpoint/helper must include a runnable example under
  `examples/`. Group examples by capability in an endpoint-oriented directory
  such as `examples/extract_text/`, and use a descriptive `*_example.py`
  filename. Add the script to the inventory in `examples/README.md` and update
  relevant docs links or usage guidance when the new capability changes
  discoverability.

- Make each example a standalone uv script. Its first lines must be a PEP 723
  metadata block in the single-line form understood by the Nox example discovery
  code:

  ```python
  # /// script
  # requires-python = ">=3.10"
  # dependencies = ["pdfrest", "python-dotenv"]
  # ///
  ```

  Set `requires-python` to the widest supported range the example actually
  supports and list every third-party import in `dependencies`. Keep the block
  first (do not put a shebang above it), because `noxfile.py` reads metadata
  starting at line one. PEP 723 metadata gives `uv run` an isolated environment;
  do not rely on undeclared project or development dependencies.

- Follow the metadata with a module docstring that states the user outcome,
  lists the important upload/API/output steps, and gives the exact command to
  run from the repository root, for example
  `uv run examples/extract_text/extract_pdf_text_example.py`. Name required
  environment variables, input files, and any expected setup in that docstring.

- Prefer deterministic, redistributable inputs under `examples/resources/` and
  resolve them relative to `Path(__file__)`, never the caller's working
  directory. Reuse a suitable checked-in resource when possible. Before adding a
  new binary or specialized input, confirm its provenance, redistribution
  suitability, and expected API behavior; ask the contributor for the required
  asset when those cannot be established.

- Examples exercise the real service, load `PDFREST_API_KEY` from the
  environment (optionally through `python-dotenv`), upload local inputs through
  `client.files.create_from_paths`, and use client context managers. Keep the
  flow short and instructional while printing enough typed response data for a
  user and CI to confirm success.

- Put interpreter-specific alternatives beside the base script as
  `python-X.Y/<same_name>.py`, with a local `ruff.toml` extending the parent
  configuration, only when syntax or compatibility requires a distinct script.
  The base script remains the default for newer supported interpreters.

- Validate a new or changed example directly with `uv run <script>` when the
  published SDK contains the demonstrated API. During development, validate
  against the local checkout with
  `uvx nox -s run-example -- examples/<capability>/<script>.py`; run
  `uvx nox -s examples` for the Python 3.10-3.14 matrix when practical. The CI
  `examples` job runs every discovered script against the live service on each
  supported interpreter and gates publishing, so examples must be safe to run
  repeatedly and must not depend on third-party network resources.

## Commit & Pull Request Guidelines

- Follow the `area: summary` convention seen in `pdfassistant-chatbot` (e.g.,
  `client: Add document merge service`).
- Keep commit messages imperative and focused; squash fixups before opening a
  PR.
- Reference related issues or tickets in the PR description, and highlight
  breaking changes.
- Confirm CI passes (`pre-commit`, Python matrix) and note any manual
  verification or screenshots for behaviour updates.

## CI & Publishing Notes

- GitHub Actions run three workflows: `pre-commit` (no AWS credentials),
  `Test and Publish` (Python 3.10–3.14 matrix), and `Docs` (GitHub Pages build
  and deploy on `main` push/manual dispatch).
- Only the release job assumes the AWS OIDC role to `uv build` and publish with
  `uv publish`.
- Keep CodeArtifact credentials out of source control; day-to-day development
  should rely solely on public dependencies.
