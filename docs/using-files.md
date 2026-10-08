# Using files

This guide covers the file lifecycle in the SDK: creating files on pdfRest,
retrieving file metadata/content, streaming downloads, and deleting files.

File operations are exposed from
[`PdfRestClient.files`](api-reference.md#pdfrest.PdfRestClient.files) and
[`AsyncPdfRestClient.files`](api-reference.md#pdfrest.AsyncPdfRestClient.files),
which implement
[`PdfRestFilesClient`](api-reference.md#pdfrest.PdfRestFilesClient) and
[`AsyncPdfRestFilesClient`](api-reference.md#pdfrest.AsyncPdfRestFilesClient).

## Core file types

- [`PdfRestFile`](api-reference.md#pdfrest.models.PdfRestFile): metadata for a
  server-side file (`id`, `name`, `url`, `type`, `size`, and more).
- [`PdfRestFileID`](api-reference.md#pdfrest.models.PdfRestFileID): typed file
  identifier accepted by file lookup and endpoint methods.

All file creation methods return
`list[`[`PdfRestFile`](api-reference.md#pdfrest.models.PdfRestFile)`]`, which is
designed to flow directly into endpoint helpers.

## Async usage

Use [`AsyncPdfRestClient`](api-reference.md#pdfrest.AsyncPdfRestClient) when:

- Your app already uses `asyncio` (FastAPI, async workers, async CLIs).
- You need higher throughput across many concurrent uploads/downloads.
- You want non-blocking network I/O while other tasks run.

The async files API mirrors sync methods with `await`, and the stream behavior
is documented on
[`AsyncPdfRestFilesClient.stream`](api-reference.md#pdfrest.AsyncPdfRestFilesClient.stream).

```python
from pdfrest import AsyncPdfRestClient


async def process_pdf() -> None:
    async with AsyncPdfRestClient() as client:
        uploaded = await client.files.create_from_paths(["./input.pdf"])
        result = await client.extract_pdf_text(uploaded, full_text="document")
        await client.files.write_bytes(uploaded[0], "./copy-of-input.pdf")
```

## Create files on pdfRest

### 1) Upload in-memory/file-like content with `files.create(...)`

Use this when you already have open file handles, bytes, or HTTPX-style
multipart tuples.

=== "Sync"
    ```python
    from pathlib import Path
    from pdfrest import PdfRestClient

    with PdfRestClient() as client, Path("input.pdf").open("rb") as fh:
        uploaded = client.files.create([("input.pdf", fh, "application/pdf")])
    ```

=== "Async"
    ```python
    from pathlib import Path
    from pdfrest import AsyncPdfRestClient


    async def upload() -> None:
        async with AsyncPdfRestClient() as client, Path("input.pdf").open("rb") as fh:
            uploaded = await client.files.create([("input.pdf", fh, "application/pdf")])
    ```

HTTPX references:

- [Sending Multipart File Uploads](https://www.python-httpx.org/quickstart/#sending-multipart-file-uploads)
- [API: `files=` parameter shapes](https://www.python-httpx.org/api/)

### 2) Upload from local paths with `files.create_from_paths(...)`

Best default for local files. Each entry can be:

- `path`
- `(path, content_type)`
- `(path, content_type, headers)`

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(
            [
                "./input.pdf",
                ("./profile.json", "application/json"),
            ]
        )
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def upload_from_paths() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(
                [
                    "./input.pdf",
                    ("./profile.json", "application/json"),
                ]
            )
    ```

### 3) Upload from remote URLs with `files.create_from_urls(...)`

Use this when pdfRest should fetch files from `http`/`https` URLs.

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_urls(["https://example.com/document.pdf"])
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def upload_from_urls() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_urls(
                ["https://example.com/document.pdf"]
            )
    ```

## Retrieve files from pdfRest

### If you already have a file ID

Yes. If you already have an ID (for example from direct pdfRest API usage), the
SDK way to get a [`PdfRestFile`](api-reference.md#pdfrest.models.PdfRestFile)
is to call `files.get(id)`.

Use `files.get(id)` when:

- You need the full metadata object (`name`, `url`, `type`, `size`, etc.).
- You want a typed [`PdfRestFile`](api-reference.md#pdfrest.models.PdfRestFile)
  to pass into endpoint helpers.

You can also pass a file ID string directly to file-content helpers such as
`read_bytes`, `read_text`, `read_json`, `write_bytes`, and `stream` when you do
not need metadata first.

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    existing_id = "1de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39"

    with PdfRestClient() as client:
        # Hydrate metadata into PdfRestFile
        file_meta = client.files.get(existing_id)

        # Or use the ID directly for content retrieval
        raw = client.files.read_bytes(existing_id)
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient

    existing_id = "1de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39"


    async def work_with_existing_id() -> None:
        async with AsyncPdfRestClient() as client:
            # Hydrate metadata into PdfRestFile
            file_meta = await client.files.get(existing_id)

            # Or use the ID directly for content retrieval
            raw = await client.files.read_bytes(existing_id)
    ```

### Get metadata by ID with `files.get(...)`

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        file_meta = client.files.get("1de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39")
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def fetch_metadata() -> None:
        async with AsyncPdfRestClient() as client:
            file_meta = await client.files.get("1de305d2-b6a0-4b5d-9a55-4e4e6d8c2d39")
    ```

### Choose a content retrieval method

`file_ref` can be either a [`PdfRestFile`](api-reference.md#pdfrest.models.PdfRestFile)
or a file ID string for all methods below.

- `files.read_bytes(file_ref)`:
  best when you need raw binary in memory (hashing, passing to other APIs,
  custom parsers).
- `files.read_text(file_ref, encoding=...)`:
  best when the file is textual and you want decoded `str` content.
- `files.read_json(file_ref)`:
  best when the file contains JSON and you want parsed Python objects.
- `files.write_bytes(file_ref, destination)`:
  best when you want a local file saved to disk without handling chunks.
- `files.stream(file_ref)`:
  best for large files or progressive processing to avoid loading the whole
  file into memory.

### `files.read_bytes(...)`

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])
        raw = client.files.read_bytes(uploaded[0])
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def read_as_bytes() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])
            raw = await client.files.read_bytes(uploaded[0])
    ```

### `files.read_text(...)`

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./notes.txt"])
        text = client.files.read_text(uploaded[0], encoding="utf-8")
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def read_as_text() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./notes.txt"])
            text = await client.files.read_text(uploaded[0], encoding="utf-8")
    ```

### `files.read_json(...)`

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./metadata.json"])
        payload = client.files.read_json(uploaded[0])
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def read_as_json() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./metadata.json"])
            payload = await client.files.read_json(uploaded[0])
    ```

### `files.write_bytes(...)`

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])
        saved_path = client.files.write_bytes(uploaded[0], "./downloaded.pdf")
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def write_to_disk() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])
            saved_path = await client.files.write_bytes(uploaded[0], "./downloaded.pdf")
    ```

### `files.stream(...)`

Use this when files are large or you need chunk/line-level processing.

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])
        with client.files.stream(uploaded[0]) as stream:
            for chunk in stream.iter_bytes():
                # process chunk
                pass
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def stream_download() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])
            async with await client.files.stream(uploaded[0]) as stream:
                async for chunk in stream.iter_bytes():
                    # process chunk
                    pass
    ```

Both stream wrappers also expose text/line/raw iterators:

- sync: `iter_text`, `iter_lines`, `iter_raw`
- async: `iter_text`, `iter_lines`, `iter_raw`

### Choosing a stream iterator

- `iter_bytes(...)`: default choice for binary data when you want chunked,
  decoded-bytes reads.
- `iter_text(...)`: use when the response is textual and you want decoded string
  chunks instead of bytes.
- `iter_lines()`: use for line-oriented formats (logs, NDJSON, CSV-like text)
  where processing per line is easiest.
- `iter_raw(...)`: use for the lowest-level byte access without higher-level
  decoding conveniences.

#### `iter_bytes(...)` example

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])
        with client.files.stream(uploaded[0]) as stream:
            for chunk in stream.iter_bytes(chunk_size=65536):
                # process binary chunk
                pass
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def stream_bytes() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])
            async with await client.files.stream(uploaded[0]) as stream:
                async for chunk in stream.iter_bytes(chunk_size=65536):
                    # process binary chunk
                    pass
    ```

#### `iter_text(...)` example

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./notes.txt"])
        with client.files.stream(uploaded[0]) as stream:
            for text_chunk in stream.iter_text():
                # process decoded text chunk
                pass
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def stream_text() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./notes.txt"])
            async with await client.files.stream(uploaded[0]) as stream:
                async for text_chunk in stream.iter_text():
                    # process decoded text chunk
                    pass
    ```

#### `iter_lines()` example

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./events.ndjson"])
        with client.files.stream(uploaded[0]) as stream:
            for line in stream.iter_lines():
                # process one logical line at a time
                pass
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def stream_lines() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./events.ndjson"])
            async with await client.files.stream(uploaded[0]) as stream:
                async for line in stream.iter_lines():
                    # process one logical line at a time
                    pass
    ```

#### `iter_raw(...)` example

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])
        with client.files.stream(uploaded[0]) as stream:
            for raw_chunk in stream.iter_raw(chunk_size=65536):
                # lowest-level raw chunks
                pass
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def stream_raw() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])
            async with await client.files.stream(uploaded[0]) as stream:
                async for raw_chunk in stream.iter_raw(chunk_size=65536):
                    # lowest-level raw chunks
                    pass
    ```

HTTPX reference:

- [Streaming Responses](https://www.python-httpx.org/quickstart/#streaming-responses)

## Chaining: upload output directly into endpoint calls

The SDK consistently models file inputs as one-or-many, so the list returned by
upload calls can be passed directly into many endpoint helpers.

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])

        # Direct chain: list[PdfRestFile] -> endpoint
        images = client.convert_to_png(uploaded, resolution=144)

        # Single-file endpoints also accept one-or-many file inputs in this SDK.
        text = client.extract_pdf_text(uploaded, full_text="document")
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def chain_calls() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])

            images = await client.convert_to_png(uploaded, resolution=144)
            text = await client.extract_pdf_text(uploaded, full_text="document")
    ```

This avoids manual ID extraction and keeps call sites typed as
[`PdfRestFile`](api-reference.md#pdfrest.models.PdfRestFile) objects.

## Delete files

Delete uploaded files when you no longer need them:

=== "Sync"
    ```python
    from pdfrest import PdfRestClient

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf"])
        client.files.delete(uploaded)
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient


    async def delete_files() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf"])
            await client.files.delete(uploaded)
    ```

`delete(...)` accepts one file or a sequence of files.

### Handling delete failures (`PdfRestErrorGroup`)

When one or more file deletions fail, `delete(...)` raises
[`PdfRestErrorGroup`](api-reference.md#pdfrest.PdfRestErrorGroup). The group
contains one
[`PdfRestDeleteError`](api-reference.md#pdfrest.PdfRestDeleteError) per file
that failed, so you can report each file-level failure precisely.

=== "Sync"
    ```python
    from pdfrest import PdfRestClient, PdfRestDeleteError, PdfRestErrorGroup

    with PdfRestClient() as client:
        uploaded = client.files.create_from_paths(["./input.pdf", "./second.pdf"])
        try:
            client.files.delete(uploaded)
        except PdfRestErrorGroup as exc:
            for err in exc.exceptions:
                if isinstance(err, PdfRestDeleteError):
                    print(f"Delete failed for file_id={err.file_id}: {err.detail}")
                else:
                    print(f"Unexpected delete error: {err}")
            raise
    ```

=== "Async"
    ```python
    from pdfrest import AsyncPdfRestClient, PdfRestDeleteError, PdfRestErrorGroup


    async def delete_with_error_handling() -> None:
        async with AsyncPdfRestClient() as client:
            uploaded = await client.files.create_from_paths(["./input.pdf", "./second.pdf"])
            try:
                await client.files.delete(uploaded)
            except PdfRestErrorGroup as exc:
                for err in exc.exceptions:
                    if isinstance(err, PdfRestDeleteError):
                        print(f"Delete failed for file_id={err.file_id}: {err.detail}")
                    else:
                        print(f"Unexpected delete error: {err}")
                raise
    ```
