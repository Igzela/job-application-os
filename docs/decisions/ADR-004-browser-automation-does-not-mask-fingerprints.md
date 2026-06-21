# ADR-004: Browser Automation Does Not Mask Fingerprints

## Status

Superseded by ADR-009

## Date

2026-06-20

## Context

The code combined explicit live-mode safety controls with Patchright,
automation-flag masking, randomized browser identity, geolocation spoofing,
and simulated typing. That contradicted the documented rule against scraping
or security-verification evasion.

## Decision

Use standard Playwright. Live automation may use a user-controlled CDP session
or an isolated standalone profile, but it must not mask automation flags or
spoof browser identity. Keep explicit live mode, operating hours, daily
limits, duplicate checks, evidence validation, and diagnostics.

## Consequences

- Browser behavior is easier to audit and test.
- Login, verification, and access limits remain hard stops.
- Timing is deterministic operational pacing, not detection avoidance.
