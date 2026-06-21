# ADR-008: Scrapling Is The Shared Extraction Runtime

## Status

Accepted

## Date

2026-06-21

## Context

Job OS used Scrapling only as an optional CSS parser. It did not use adaptive
element storage, fetchers, or the spider framework, so selector maintenance and
generic crawl workflows remained duplicated.

## Decision

Use Scrapling 0.4.x as the shared extraction runtime:

- SQLite-backed adaptive element storage for BOSS selectors.
- HTTP and standard dynamic-browser fetch workflows.
- Same-domain Spider crawls with robots.txt enforcement, bounded concurrency,
  download delay, checkpoints, and JSONL output.
- Lazy capability imports so core local workflows still work without optional
  fetcher dependencies.
- BeautifulSoup remains the parser fallback for BOSS fixtures and degraded
  environments.

Security verification, login requirements, and access limits remain explicit
page states and hard stops. Job OS does not automatically solve verification
challenges.

## Consequences

- BOSS selectors can recover from compatible DOM changes using stored element
  fingerprints.
- Fetched HTML is replayable and crawl output is auditable.
- Full functionality requires `job-application-os[scrapling]` and Scrapling's
  browser installation step.
- `scrapling_runs/` and the adaptive SQLite database are runtime artifacts and
  are not committed.
