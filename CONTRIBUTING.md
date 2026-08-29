# Contributing

Thanks for contributing to `pdfrest`.

## Development setup

1. Install project tooling:

```bash
uv sync --group dev
```

2. (Recommended) install git hooks:

```bash
uv run pre-commit install
```

3. Verify package import/version:

```bash
uv run python -c "import pdfrest; print(pdfrest.__version__)"
```

## Adding or evolving a client API

When asking Codex to add a documented pdfRest endpoint or a compatible parameter
to an existing endpoint, begin the prompt with the repository-local
`$pdfrest-client-api` skill. Include the Jira work item key when one exists. The
PDFCloud-API checkout and its documented OpenAPI operation must be available
before using the skill. Prefer adding the neighboring PDFCloud-API directory to
the Codex project so the skill can read the contract directly. For example:

```text
$pdfrest-client-api PDFCLOUD-6233: Add the documented PDFCloud-API operation
for ...
```

The skill uses the PDFCloud-API OpenAPI specification as the contract; keeps the
sync and async clients aligned; puts wire serialization and validation in
Pydantic payload models; preserves existing caller behavior; and requires
focused unit coverage plus matching live endpoint tests. It also handles the
versioning required for a newly added public API.

## Code quality checks

Run these before opening a PR:

```bash
uv run ruff format .
uv run ruff check .
uv run basedpyright
```

## Tests

Quick local run:

```bash
uv run pytest -n auto --maxschedchunk 2
```

Full interpreter matrix with coverage artifacts (`coverage/py<version>/`):

```bash
uvx nox -s tests
```

Class/function coverage gate for client classes:

```bash
uvx nox -s class-coverage
```

To reuse existing coverage JSON without rerunning tests:

```bash
uvx nox -s class-coverage -- --no-tests
```

## Examples

Run all examples:

```bash
uvx nox -s examples
```

Run one example:

```bash
uv run nox -s run-example -- examples/delete/delete_example.py
```

## Docs preview (optional)

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```
