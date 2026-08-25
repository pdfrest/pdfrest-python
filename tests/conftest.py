from __future__ import annotations

import os
from itertools import pairwise
from pathlib import Path

import httpx
import pytest

LIVE_BASE_URL_CANDIDATES: tuple[str, ...] = (
    "http://localhost:3000",
    "https://apidev.pdfrest.com",
    "https://api.pdfrest.com",
)


def _is_live_test_path(path: Path) -> bool:
    """Return True when the collected item lives under tests/live."""
    lowered_parts = [part.lower() for part in path.parts]
    return any(
        first == "tests" and second == "live"
        for first, second in pairwise(lowered_parts)
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark all live tests so CI can include/exclude them efficiently."""
    for item in items:
        item_path = getattr(item, "path", Path(str(item.fspath)))
        if _is_live_test_path(item_path) or item.name.startswith("test_live_"):
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def pdfrest_api_key() -> str:
    key = os.getenv("PDFREST_API_KEY")
    if not key:
        pytest.fail("PDFREST_API_KEY is not configured.")
    return key


@pytest.fixture(scope="session")
def pdfrest_live_base_url(pdfrest_api_key: str) -> str:
    headers = {"Authorization": f"Bearer {pdfrest_api_key}"}
    timeout = httpx.Timeout(2.0)
    configured_base_url = os.getenv("PDFREST_LIVE_BASE_URL")
    base_url_candidates = (
        (configured_base_url, *LIVE_BASE_URL_CANDIDATES)
        if configured_base_url
        else LIVE_BASE_URL_CANDIDATES
    )
    for base_url in base_url_candidates:
        try:
            with httpx.Client(base_url=base_url, timeout=timeout) as client:
                response = client.get("/up", headers=headers)
        except httpx.HTTPError:
            continue
        if response.is_success:
            return base_url
    pytest.fail("No reachable pdfRest API instance for live tests.")
