"""Optional Scrapling runtime integration.

Parser support remains usable without browser-fetcher extras. Fetching and
crawling capabilities are imported lazily so core Job OS commands still load
when only the base package is installed.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ScraplingCapabilityError(RuntimeError):
    """Raised when an optional Scrapling capability is unavailable."""


def _validate_browser_path() -> str:
    """Return the project's Chromium path, raising if missing.

    Scrapling browser sessions reuse the project Chromium binary.
    """
    from .browser import CHROMIUM_PATH

    if not Path(CHROMIUM_PATH).exists():
        raise ScraplingCapabilityError(
            f"Chromium not found at {CHROMIUM_PATH}. "
            "Install Chromium or update CHROMIUM_PATH in jobos/browser.py. "
            "See docs/BROWSER_SETUP.md for details."
        )
    return CHROMIUM_PATH


@dataclass(frozen=True)
class ScraplingCapabilities:
    parser: bool
    fetchers: bool
    spiders: bool
    stealth: bool


def capabilities() -> ScraplingCapabilities:
    parser = fetchers = spiders = stealth = False
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
    try:
        _load_stealth_fetcher()

        stealth = True
    except (ImportError, ModuleNotFoundError):
        pass
    return ScraplingCapabilities(parser, fetchers, spiders, stealth)


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
    """Fetch one page with Scrapling's HTTP, dynamic, or stealth engine.

    Engines:
        "http"    -- lightweight HTTP with TLS fingerprint simulation
        "dynamic" -- Playwright browser automation
        "stealth" -- Scrapling browser session with fingerprint protection
    """
    if engine == "stealth":
        return _fetch_stealth(url, headless=headless, timeout=timeout, **options)

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
            options["executable_path"] = _validate_browser_path()
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


def _fetch_stealth(
    url: str,
    *,
    headless: bool = True,
    timeout: int = 30,
    **options: Any,
):
    """Fetch with StealthyFetcher while leaving challenges to the user."""
    try:
        StealthyFetcher = _load_stealth_fetcher()
    except (ImportError, ModuleNotFoundError) as exc:
        raise ScraplingCapabilityError(
            "StealthyFetcher is unavailable. Install "
            "`job-application-os[scrapling]` and run `scrapling install`."
        ) from exc

    if "executable_path" not in options:
        options["executable_path"] = _validate_browser_path()

    stealth_defaults = {
        "solve_cloudflare": False,
        "block_webrtc": True,
        "hide_canvas": True,
        "google_search": True,
        "block_ads": True,
    }
    for key, val in stealth_defaults.items():
        options.setdefault(key, val)
    options["solve_cloudflare"] = False

    try:
        return StealthyFetcher.fetch(
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


@contextmanager
def stealth_session(
    *,
    headless: bool = True,
    timeout: int = 60,
    user_data_dir: str | None = None,
    proxy: str | dict | None = None,
    **options: Any,
):
    """Context manager for a StealthySession — multi-page stealth browsing.

    Usage:
        with stealth_session(headless=False) as session:
            page1 = session.fetch("https://example.com")
            page2 = session.fetch("https://example2.com")
    """
    try:
        StealthySession = _load_stealth_session()
    except (ImportError, ModuleNotFoundError) as exc:
        raise ScraplingCapabilityError(
            "StealthySession is unavailable. Install "
            "`job-application-os[scrapling]` and run `scrapling install`."
        ) from exc

    if "executable_path" not in options:
        options["executable_path"] = _validate_browser_path()
    options.pop("headless", None)
    options.pop("timeout", None)

    stealth_defaults = {
        "solve_cloudflare": False,
        "block_webrtc": True,
        "hide_canvas": True,
        "google_search": True,
        "block_ads": True,
    }
    for key, val in stealth_defaults.items():
        options.setdefault(key, val)
    options["solve_cloudflare"] = False

    if user_data_dir:
        options["user_data_dir"] = user_data_dir
    if proxy:
        options["proxy"] = proxy

    with StealthySession(
        headless=headless,
        timeout=timeout * 1000,
        **options,
    ) as session:
        yield session


def _load_fetchers():
    from scrapling.fetchers import DynamicFetcher, Fetcher

    return Fetcher, DynamicFetcher


def _load_stealth_fetcher():
    from scrapling.fetchers import StealthyFetcher

    return StealthyFetcher


def _load_stealth_session():
    from scrapling.fetchers import StealthySession

    return StealthySession
