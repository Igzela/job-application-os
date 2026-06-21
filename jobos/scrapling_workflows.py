"""User-facing Scrapling fetch and crawl workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from .scrapling_runtime import ScraplingCapabilityError, fetch_page


@dataclass(frozen=True)
class FetchArtifact:
    url: str
    status: int
    engine: str
    html_path: str
    metadata_path: str


def fetch_to_workspace(
    state_dir: str | Path,
    url: str,
    *,
    engine: str = "http",
    headless: bool = True,
) -> FetchArtifact:
    """Fetch one URL and persist replayable HTML plus metadata."""
    response = fetch_page(url, engine=engine, headless=headless)
    output_dir = Path(state_dir) / "scrapling_runs" / "fetch"
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _url_slug(url)
    html_path = output_dir / f"{slug}.html"
    metadata_path = output_dir / f"{slug}.json"
    html = response.html_content if hasattr(response, "html_content") else str(response)
    status = int(getattr(response, "status", 0) or 0)
    html_path.write_text(html, encoding="utf-8")
    artifact = FetchArtifact(
        url=str(getattr(response, "url", url) or url),
        status=status,
        engine=engine,
        html_path=str(html_path),
        metadata_path=str(metadata_path),
    )
    metadata_path.write_text(
        json.dumps(asdict(artifact), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact


def crawl_to_workspace(
    state_dir: str | Path,
    start_url: str,
    *,
    max_pages: int = 50,
    concurrency: int = 3,
    download_delay: float = 1.0,
) -> dict:
    """Run a same-domain, robots-aware Scrapling spider."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if download_delay < 0:
        raise ValueError("download_delay must be non-negative")
    try:
        from scrapling.spiders import Response, Spider
    except (ImportError, ModuleNotFoundError) as exc:
        raise ScraplingCapabilityError(
            "Scrapling spiders are unavailable. Install "
            "`job-application-os[scrapling]`."
        ) from exc

    host = urlparse(start_url).hostname or ""
    output_dir = Path(state_dir) / "scrapling_runs" / "crawl" / _url_slug(start_url)
    output_dir.mkdir(parents=True, exist_ok=True)
    crawl_concurrency = concurrency
    crawl_delay = download_delay

    class WorkspaceSpider(Spider):
        name = "jobos_workspace_crawl"
        start_urls = [start_url]
        allowed_domains = {host}
        robots_txt_obey = True
        concurrent_requests = crawl_concurrency
        concurrent_requests_per_domain = crawl_concurrency
        download_delay = crawl_delay

        async def parse(self, response: Response):
            if self.stats.requests_count > max_pages:
                return
            yield {
                "url": str(response.url),
                "title": response.css("title::text").get(""),
                "text": response.get_all_text(ignore_tags=("script", "style")),
            }
            if self.stats.requests_count >= max_pages:
                return
            for link in response.css("a::attr(href)").getall():
                yield response.follow(link, callback=self.parse)

    result = WorkspaceSpider(crawldir=str(output_dir / "checkpoint")).start()
    items_path = output_dir / "items.jsonl"
    result.items.to_jsonl(str(items_path))
    summary = {
        "start_url": start_url,
        "completed": bool(result.completed),
        "items": len(result.items),
        "items_path": str(items_path),
        "stats": asdict(result.stats),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def _url_slug(url: str) -> str:
    parsed = urlparse(url)
    value = f"{parsed.netloc}{parsed.path}".strip("/") or "page"
    return "".join(char if char.isalnum() else "-" for char in value).strip("-")[:100]
