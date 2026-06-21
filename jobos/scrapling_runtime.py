"""Optional Scrapling runtime integration.

Parser support remains usable without browser-fetcher extras. Fetching and
crawling capabilities are imported lazily so core Job OS commands still load
when only the base package is installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ScraplingCapabilityError(RuntimeError):
    """Raised when an optional Scrapling capability is unavailable."""


@dataclass(frozen=True)
class ScraplingCapabilities:
    parser: bool
    fetchers: bool
    spiders: bool


def capabilities() -> ScraplingCapabilities:
    parser = fetchers = spiders = False
    try:
        from scrapling.parser import Selector  # noqa: F401

        parser = True
    except ImportError:
        pass
    try:
        from scrapling.fetchers import DynamicFetcher, Fetcher  # noqa: F401

        fetchers = True
    except (ImportError, ModuleNotFoundError):
        pass
    try:
        from scrapling.spiders import Spider  # noqa: F401

        spiders = True
    except (ImportError, ModuleNotFoundError):
        pass
    return ScraplingCapabilities(parser, fetchers, spiders)


def create_selector(
    html: str,
    *,
    url: str,
    adaptive: bool,
    storage_file: str | Path,
):
    """Create a Selector backed by the configured adaptive SQLite store."""
    try:
        from scrapling.core.storage import SQLiteStorageSystem
        from scrapling.parser import Selector
    except ImportError as exc:
        raise ScraplingCapabilityError(
            "Scrapling parser is unavailable. Install `job-application-os[scrapling]`."
        ) from exc

    store_path = Path(storage_file).expanduser()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    return Selector(
        html,
        url=url,
        adaptive=adaptive,
        storage=SQLiteStorageSystem,
        storage_args={"storage_file": str(store_path)},
    )


def fetch_page(
    url: str,
    *,
    engine: str = "http",
    headless: bool = True,
    timeout: int = 30,
    adaptive: bool = True,
    **options: Any,
):
    """Fetch one page with Scrapling's HTTP or standard dynamic engine."""
    try:
        Fetcher, DynamicFetcher = _load_fetchers()
    except (ImportError, ModuleNotFoundError) as exc:
        raise ScraplingCapabilityError(
            "Scrapling fetchers are unavailable. Install "
            "`job-application-os[scrapling]` and run `scrapling install`."
        ) from exc

    if engine == "http":
        Fetcher.adaptive = adaptive
        return Fetcher.get(url, timeout=timeout, **options)
    if engine == "dynamic":
        DynamicFetcher.adaptive = adaptive
        if "executable_path" not in options:
            from .browser import CHROMIUM_PATH

            if Path(CHROMIUM_PATH).exists():
                options["executable_path"] = CHROMIUM_PATH
        try:
            return DynamicFetcher.fetch(
                url,
                headless=headless,
                timeout=timeout * 1000,
                **options,
            )
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                raise ScraplingCapabilityError(
                    "Scrapling browser runtime is missing. Run `scrapling install`."
                ) from exc
            raise
    raise ValueError(f"Unknown Scrapling engine: {engine}")


def _load_fetchers():
    from scrapling.fetchers import DynamicFetcher, Fetcher

    return Fetcher, DynamicFetcher
