"""BOSS-optimized StealthyFetcher wrapper.

Provides a convenience layer over Scrapling's StealthyFetcher with defaults
tailored for Chinese job sites (zh-CN locale, Asia/Shanghai timezone,
Google referer, anti-detection enabled).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from .scrapling_runtime import stealth_session


def fetch_boss_page(
    url: str,
    *,
    stealth: bool = True,
    headless: bool = True,
    timeout: int = 60,
    proxy: str | dict | None = None,
    page_action: Any = None,
    wait_selector: str | None = None,
    **kwargs: Any,
):
    """Fetch a BOSS Zhipin page with optimal stealth settings.

    Args:
        url: Target URL
        stealth: Use StealthyFetcher (True) or DynamicFetcher (False)
        headless: Run browser in headless mode
        timeout: Page timeout in seconds
        proxy: Proxy string or dict with server/username/password
        page_action: Playwright Page callback for automation
        wait_selector: CSS selector to wait for before returning
        **kwargs: Additional StealthyFetcher options

    Returns:
        Scrapling Response object with .css(), .xpath(), etc.
    """
    from .config import load_config, resolve_proxy_url
    from .scrapling_runtime import fetch_page

    config = load_config()
    options: dict[str, Any] = {
        **config.get("stealth", {}),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }
    options.pop("headless", None)
    options.pop("timeout", None)
    options["solve_cloudflare"] = False
    resolved_proxy = proxy or resolve_proxy_url(config)
    if resolved_proxy:
        options["proxy"] = resolved_proxy
    if page_action:
        options["page_action"] = page_action
    if wait_selector:
        options["wait_selector"] = wait_selector
    options.update(kwargs)

    engine = "stealth" if stealth else "dynamic"
    return fetch_page(
        url,
        engine=engine,
        headless=headless,
        timeout=timeout,
        **options,
    )


@contextmanager
def boss_stealth_session(
    *,
    headless: bool = True,
    timeout: int | None = None,
    user_data_dir: str | None = None,
    proxy: str | dict | None = None,
    **kwargs: Any,
):
    """Context manager for multi-page BOSS stealth browsing.

    Usage:
        with boss_stealth_session(headless=False) as session:
            page1 = session.fetch("https://www.zhipin.com/web/geek/chat")
            page2 = session.fetch("https://www.zhipin.com/web/geek/job")
    """
    from .config import load_config, resolve_proxy_url

    config = load_config()
    options: dict[str, Any] = {
        **config.get("stealth", {}),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }
    configured_timeout = options.pop("timeout", 60)
    options.pop("headless", None)
    options["solve_cloudflare"] = False
    options.update(kwargs)

    with stealth_session(
        headless=headless,
        timeout=timeout if timeout is not None else configured_timeout,
        user_data_dir=user_data_dir,
        proxy=proxy or resolve_proxy_url(config),
        **options,
    ) as session:
        yield session
