# Testing Guidelines

The existing suite already exercises uploads, conversions, compression,
redaction, metadata queries, and file utilities through both synchronous and
asynchronous clients. The expectations below condense every technique we rely on
so new endpoints launch with complete coverage on the first pass—no reviewer
iteration required.

## Core Principles

- **Cover both transports everywhere.** Write distinct sync (`PdfRestClient`)
  and async (`AsyncPdfRestClient`) tests for every scenario—such as happy paths,
  request customization, validation failures, file helpers, and live calls. Do
  not hide the transport behind a parameter; the test name itself should reveal
  which client is under test.
- **Maintain high client coverage.** `PdfRestClient` and `AsyncPdfRestClient`
  are the primary customer-facing entry points. Every public client method must
  have at least one unit test that exercises the REST call path (MockTransport
  asserting method/path/headers/body). Optional payload branches (for example,
  `pages`, `output`, `rgb_color`, and output-prefix fields) require explicit
  tests so serialization differences are caught early.
- **Keep endpoint tests in their home files.** When adding or restoring coverage
  for an endpoint, place the test in that endpoint's existing test module (for
  example, `tests/test_convert_to_excel.py`), not in a generic cross-endpoint
  coverage file.
- **Check client coverage regularly.** Run `uvx nox -s class-coverage` to
  enforce minimum function-level coverage for `PdfRestClient` and
  `AsyncPdfRestClient`.
- **Exercise both sides of the contract.** Hermetic tests (via
  `httpx.MockTransport`) validate serialization and local validation. Live
  suites prove the server behaves the same way, including invalid literal
  handling.
- **Know where coverage lands.** The nox `tests` session writes coverage reports
  to `coverage/py<version>/` (XML, Markdown, and HTML). Example:
  `coverage/py3.12/coverage.xml`, `coverage/py3.12/coverage.md`,
  `coverage/py3.12/html/`.
- **Reset global state per test.** Use
  `monkeypatch.delenv("PDFREST_API_KEY", raising=False)` (or `setenv`) so
  clients never inherit accidental API keys. Patch `importlib.metadata.version`
  when asserting SDK headers.
- **Lean on shared helpers.** Reuse `tests/graphics_test_helpers.py`
  (`make_pdf_file`, `build_file_info_payload`, `PdfRestFileID.generate()`),
  `tests/resources/`, and fixtures from `tests/conftest.py` to keep payloads
  deterministic.
- **Assert behaviour, not just invocation.** Validate outbound payloads,
  headers, query params, response contents, warnings, and timeouts. Track
  request counts (`seen = {"post": 0, "get": 0}`) so redundant HTTP calls fail
  loudly.

## Environment & Configuration Coverage

- Verify API keys sourced from kwargs vs environment variables, and ensure
  invalid/missing keys raise `PdfRestConfigurationError`.
- Confirm SDK identity headers (`wsn`, `User-Agent`, `Accept`) by patching
  `importlib.metadata.version`.
- Assert `PdfRestClient` omits `Api-Key` when pointed at custom hosts and honors
  caller-provided headers/query params even for control-plane calls like
  `.up()`.

## Mocked (Unit) Tests

### Transports & Request Inspection

- Use `httpx.MockTransport` handlers that assert:
  - HTTP method + path (`/png`, `/compressed-pdf`, `/resource/{id}`, etc.).
  - Query parameters and headers (trace/debug flags, mode switches, custom auth
    headers).
  - JSON payloads obtained via `json.loads(request.content)` and compared to the
    relevant Pydantic payload’s
    `.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)`.
- For “should not happen” cases (invalid IDs, missing profiles), set the
  transport to immediately raise
  (`lambda request: (_ for _ in ()).throw(RuntimeError)` or `pytest.fail`) so
  local validation is guaranteed.

### Error Translation & Retries

- Simulate 4xx/5xx responses and assert the correct exception surfaces:
  `PdfRestAuthenticationError` (401/403), `PdfRestApiError` (other status codes,
  include error text), `PdfRestTimeoutError` (raise `httpx.TimeoutException`),
  `PdfRestTransportError` (raise `httpx.TransportError`).
- Cover retry logic by returning retriable responses multiple times and
  confirming the client retries before raising (see `tests/test_client.py`
  patterns for `Retry-After`).
- Include `pytest.raises(..., match="...")` to ensure exception messages capture
  server warnings, retry hints, or timeout wording.

### Sync vs Async Coverage

- Sync tests wrap clients in `with PdfRestClient(...):`.
- Async tests use `@pytest.mark.asyncio` and
  `async with AsyncPdfRestClient(...):`.
- When asserting async failures, place `pytest.raises` inside the `async with`
  block. Python forbids mixing `with` and `async with` in a single statement.

### Request Customization

- For every endpoint that accepts `extra_query`, `extra_headers`, `extra_body`,
  or `timeout`, add explicit tests (sync + async) proving those options
  propagate. Capture `request.extensions["timeout"]` and assert every component
  equals `pytest.approx(expected)`.
- For both sync and async endpoint helpers, ensure request-customization or
  success tests also exercise endpoint-specific optional payload branches (for
  example `output`, `output_prefix`, `pages`, `page_groups`, redaction payloads)
  so non-live class-function coverage does not depend on live suites.

### Validation & Payload Modeling

- Use the payload models directly (`PngPdfRestPayload`, `PdfCompressPayload`,
  `PdfMergePayload`, `PdfSplitPayload`, `PdfRedactionApplyPayload`, etc.) to
  assert serialization, output-prefix validation, and range normalization in
  isolation from the client.
- Through the client surface, pair calls with
  `pytest.raises(ValidationError, match="...")` for MIME enforcement (“Must be a
  PDF file”), dependency rules (“compression_level 'custom' requires a
  profile”), profile MIME validation (“Profile must be a JSON file”), and list
  length bounds.
- Cover all accepted literal shapes: single literal vs list vs tuple for
  `PdfInfoQuery`; dict vs tuple vs sequence for `PdfMergeInput`; tuple/list/None
  for `PdfRGBColor`; JSON-friendly dicts for redaction instructions.

### Enumerations, Numeric Ranges, and Options

- Use `pytest.mark.parametrize` with `pytest.param(..., id="friendly")` to
  enumerate literals such as `color_model`, `smoothing`, `compression_level`,
  `page_range`, merge selectors, JPEG quality boundaries, or any future literal
  surfaced by new APIs.
- Include invalid literals (such as `"extreme"` compression levels, unsupported
  `color_model` values, or smoothing arrays containing
  duplicates/more-than-allowed entries) to ensure validation errors remain
  descriptive—use `re.escape(...)` when asserting. A published-name literal
  combined with open `str` is different: an unlisted non-empty name is valid,
  while an empty name should fail local shape validation.
- For numeric fields (resolution, DPI, percentages, counts, radii, opacity,
  etc.), exercise the extremes: the documented minimum/maximum, the first legal
  value just inside each bound, and at least one value just outside the range.
  Treat every `ge`, `le`, `gt`, `lt`, or `Annotated` constraint as requiring
  explicit boundary tests.
- For textual ranges, cover ascending permutations, `"last"`, `"1-last"`,
  descending segments (where allowed), and disallowed selectors (such as
  `"even"`/`"odd"` when the server forbids them).
- When endpoints expose optional payload arguments (output prefixes, diagnostics
  toggles, merge metadata, future knobs), include both defaulted and explicitly
  provided cases so serialization doesn’t regress.

### Response Verification

- Assert the concrete response types (`PdfRestFileBasedResponse`, `PdfRestFile`,
  `PdfRestInfoResponse`, etc.).
- Inspect every relevant attribute:
  - File metadata (`name`, `type`, `size`, `url`, `warning`).
  - `input_id` echoes the uploaded file ID (string comparison).
  - `output_files` count matches the number of IDs returned by the mock service.
- For file-service helpers, compare results against `_build_file_info_payload`
  via `_assert_file_matches_payload`.

### Files API Scenarios

- Uploads: assert multipart bodies include the correct number of `name="file"`
  parts and filenames, and that
  `client.files.create`/`create_from_paths`/`create_from_urls` fetch info
  documents afterward.
- Downloads: cover `download_file`, `files.read_bytes/text/json`, and
  `files.write_bytes` with `tmp_path`. Confirm file contents match expected
  bytes.
- Streaming: tests should enter `files.stream()` via `with`/`async with`,
  iterate over `iter_raw`, `iter_bytes`, `iter_text`, and `iter_lines`, and join
  chunks back to the original payload. Manage nested async context managers
  using `ExitStack` / `AsyncExitStack`.
- ID validation: ensure malformed IDs raise before sending HTTP requests
  (transport should error if called).

### Document, Compression, and Other Endpoint Examples

- Conversions (such as `convert_to_png`, `convert_to_jpeg`, `convert_to_word`,
  or any future format helper) must verify payload serialization, request
  customization, MIME enforcement, multi-file guards, and smoothing/quality
  enumerations.
- Compression helpers (such as `compress_pdf`) enforce the profile dependency
  (custom requires JSON profile; presets reject profiles) and validate MIME
  types for both PDFs and profiles in sync + async contexts.
- Split/Merge style endpoints (such as `split_pdf` or `merge_pdfs`) should
  exercise tuples/dicts/lists, ensure payload serializers emit the correct
  parallel arrays, and include validation errors for insufficient sources or
  invalid page groups.
- Redaction and metadata helpers (such as `preview_redactions`,
  `apply_redactions`, `query_pdf_info`) must cover literal shapes, optional
  parameters, and invalid presets.
- Treat these as templates for any future API from
  `pdfrest_api_reference_guide.html`: identify its payload model, enumerate
  literals/numeric bounds, and apply the same sync+async/unit+live layering.

### File Fixtures & Helpers

- Generate fake uploads with `make_pdf_file`, `build_file_info_payload`, and
  `PdfRestFileID.generate()` to keep IDs valid.
- When triggering MIME validation, fabricate `PdfRestFile` objects with
  deliberately incorrect `type` values (PNG for PDF-only endpoints, PDF for
  JSON-only profiles).
- Use `_StaticStream` / `_StaticAsyncStream` from `tests/test_files.py` to
  simulate streaming responses without touching disk.

## Live Tests

- **Location & structure:** Place suites under `tests/live/` with one module per
  endpoint (`test_live_compress_pdf.py`, `test_live_convert_to_png.py`,
  `test_live_files.py`, etc.).
- **Fixtures:** Reuse shared fixtures (`pdfrest_api_key`,
  `pdfrest_live_base_url`). Upload deterministic assets from `tests/resources/`
  via `create_from_paths` (or `client.files.create`) so responses are
  predictable. Use `pytest.fixture(scope="module"/"class")` and
  `pytest_asyncio.fixture` to cache uploaded PDFs/profiles for both transports.
- **Sync + async parity:** Every live module should contain matching sync and
  async tests for success, streaming, and invalid paths (compression levels,
  conversion options, file streaming helpers). Treat transport-plumbing
  customization (`extra_query`, `extra_headers`, `extra_body`, `timeout`) as a
  unit-test responsibility unless the endpoint exposes server-observable
  behavior tied to those options.
- **Enumerate closed literals:** Parameterize over every accepted literal
  (compression levels, `color_model`, `smoothing`, merge selectors, redaction
  presets). Each value should hit the server once per transport. When a literal
  supplies known names inside an open `Literal[...] | str` union, cover every
  listed spelling in payload and sync/async client tests, then live-test
  representative listed and unlisted names through both transports; server
  availability of a particular installed font may vary.
- **Optional arguments:** Exercise options such as custom output prefixes,
  diagnostics toggles, merge metadata, and URL uploads. Validate the server
  honors them (filenames start with the user-provided prefix, warnings appear
  when expected).
- **Customization placement:** Verify request customization wiring in mocked
  tests (sync + async) for each endpoint. Live customization tests are optional
  and should be added only when they validate server-side behavior beyond client
  request assembly.
- **Negative live cases:** Override JSON via `extra_body`/`extra_query` to
  bypass local validation and assert `PdfRestApiError` (or the exact server
  exception) surfaces—for example, sending an invalid compression literal or
  smoothing option.
- **Streaming + downloads:** In live `files` suites, cover `write_bytes`,
  `files.stream().iter_*`, and URL uploads. Manage nested `async with` blocks
  using `AsyncExitStack` to ensure resources are released.
- **Assertions:** Verify file names, MIME types, sizes, warnings, and that
  `input_id` matches the uploaded ID. When fixtures are deterministic
  (`report.pdf`, `compression_profile.json`), assert exact values rather than
  generic truthiness.
- **Resource reuse:** For `create_from_urls`, first upload files to retrieve
  stable URLs, then call the URL endpoint—never rely on arbitrary third-party
  hosts.

## Error Handling Patterns

- Always combine clients with `pytest.raises` (including descriptive `match=`)
  when testing validation or HTTP errors. For sync contexts you can use a
  compound `with (PdfRestClient(...) as client, pytest.raises(...)):`; for
  async, place `pytest.raises` inside the `async with` block.
- Distinguish between:
  - Local validation failures (`ValidationError`, `ValueError`) that should
    prevent HTTP calls.
  - Server/transport failures (`PdfRestApiError`, `PdfRestAuthenticationError`,
    `PdfRestTimeoutError`, `PdfRestTransportError`, `PdfRestErrorGroup`, etc.).
- When behaviour should short-circuit locally (bad UUIDs, empty query lists,
  missing profiles), configure the transport to raise if invoked so the test
  proves no HTTP request occurs.
- When endpoints intentionally raise pdfRest-specific `ExceptionGroup`
  subclasses (such as `PdfRestErrorGroup` produced by delete failures), capture
  them with `pytest.RaisesGroup`/`pytest.RaisesExc`, and use the `check=` hook
  to assert the aggregate is the expected group class. This verifies both the
  group message and each individual member (`PdfRestDeleteError`, future custom
  errors) instead of relying on the aggregate text alone.

## Additional Expectations

- **Context managers everywhere:** Treat clients and file streams as context
  managers so transports close cleanly.
- **pytest fixtures:** Use readable fixtures (such as `client`,
  `uploaded_pdf_for_compression`, `live_async_file`) with appropriate scopes.
  Prefer `pytest.param(..., id="...")` so parametrized IDs stay intelligible.
- **No real network in unit tests:** Hermetic tests must rely solely on
  `httpx.MockTransport`.
- **ID serialization:** Confirm payloads serialize uploaded `PdfRestFile`
  objects as IDs via `_serialize_as_first_file_id` rather than embedding nested
  structures.
- **Timeout propagation:** Every endpoint that accepts `timeout` needs both sync
  and async coverage that inspects `request.extensions["timeout"]`.
- **Multi-file safeguards:** Assert endpoints that accept exactly one
  file/profile reject extra inputs (such as conversions or compression
  profiles). Conversely, endpoints that require multiple sources (such as merge
  operations) should test both valid (≥2) and invalid (\<2) cases.
- **Shared validation suites:** When new payload shapes or validators emerge,
  add/update suites such as `tests/test_graphic_payload_validation.py` so every
  endpoint inheriting the behaviour gains coverage automatically.

## Planning for Future APIs

pdfRest will keep expanding. When implementing a new helper from
`pdfrest_api_reference_guide.html`—whether it resembles existing conversions,
merges, inspections, or something entirely new—follow this playbook:

1. **Capture inputs and constraints.** Translate every documented literal,
   numeric range, dependency, and optional field into payload annotations/tests.
   Cover boundary values (minimum, maximum, first legal values inside the range,
   and at least one outside value).
2. **Map outputs.** Determine whether the endpoint returns files, JSON, or both,
   and assert every returned attribute or warning.
3. **Layer coverage.** For each behaviour, add sync + async unit tests (mocked)
   plus sync + async live tests hitting the real service with both valid and
   intentionally invalid requests.
4. **Reuse patterns.** If the endpoint resembles an existing suite (such as
   conversions, redaction, compression, file uploads, metadata queries), mirror
   the structure and assertions to stay consistent.
5. **Evolve shared tests.** Whenever a new validation rule becomes reusable—such
   as a fresh output-prefix constraint or numeric range validator—extend the
   shared helper modules and suites so future endpoints benefit automatically.

Following these rules ensures new endpoints debut with deterministic unit tests
and fully instrumented live coverage. Treat the existing conversion,
compression, redaction, split/merge, and file suites as templates—if a behaviour
exists today (or will exist tomorrow), there should either be a matching test
pattern already or one added alongside the new API.
