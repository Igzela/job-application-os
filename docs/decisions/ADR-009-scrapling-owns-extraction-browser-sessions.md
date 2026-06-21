# ADR-009: Scrapling Owns Extraction Browser Sessions

## Status

Accepted

## Date

2026-06-21

## Context

ADR-004 required standard Playwright without fingerprint masking. The project
later adopted Scrapling as its extraction runtime, including adaptive parsing,
HTTP fetching, dynamic rendering, and Spider sessions. Keeping a separate
browser policy for extraction created duplicate configuration and prevented
Scrapling's supported stealth session from being used consistently.

## Decision

Scrapling owns browser sessions used for extraction and crawling:

- `Fetcher` handles static HTTP pages.
- `DynamicFetcher` handles JavaScript-rendered pages.
- `StealthyFetcher` and `AsyncStealthySession` are allowed for extraction.
- Spider sessions are registered through `Spider.configure_sessions()`.
- User-controlled CDP remains available for login, manual verification, and
  final live submission.
- Proxy credentials are resolved from an environment variable and never
  persisted in run metadata.
- Automatic Cloudflare/Turnstile solving remains disabled. Login, CAPTCHA,
  security verification, and access-limit pages require human action.

This decision supersedes ADR-004.

## Consequences

- Extraction uses one runtime, configuration model, and diagnostics contract.
- Fingerprint protection is available for extraction without changing the
  human-controlled submission workflow.
- Browser sessions must use the configured Chromium executable.
- Runtime summaries record only whether a proxy was enabled.
- Architecture checks reject automatic challenge-solver enablement.
