# ADR-001: Live BOSS Mode Is Explicit And Diagnosed

## Status

Accepted

## Date

2026-06-17

## Context

Job Application OS began as a local-first and dry-run oriented workflow. The current codebase now also contains explicit live BOSS paths:

- `job boss-import` imports BOSS listings through a CDP adapter.
- `job submit --confirm` and `job auto-submit --confirm` can interact with BOSS pages.
- `job start` runs the live BOSS pipeline through a logged-in browser session.

The old architecture text still described live platform interaction as future or impossible. That contradicted the current README, workflow documentation, and code.

Live browser behavior is high-risk because it can send messages, be affected by platform page changes, and create duplicate contact attempts if retries are not diagnosed carefully.

## Decision

Live BOSS mode is an explicit, diagnosed, conservative workflow. It is allowed only through commands that make live behavior visible to the caller. Dry-run remains the default for offline and loop workflows.

Live BOSS behavior must preserve these constraints:

- Connect to a user-controlled logged-in browser session through CDP, or an explicitly isolated standalone browser.
- Do not bypass login, verification, CAPTCHA, or access-limit states.
- Persist duplicate/contact state before repeat sends can occur.
- Persist daily-limit state for live sending.
- Validate or rewrite greetings before sending.
- Capture screenshots, page state, extractor, recovery hints, and success signals for submit attempts.
- Treat success as proven only from strong signals such as sent state, already-contacted state, greeting echo, or expected company chat context.

## Alternatives Considered

### Remove live BOSS functionality

- Pros: Lowest platform-risk posture and simpler architecture.
- Cons: Contradicts current implemented behavior and the product direction documented in README/WORKFLOW.
- Rejected: The current product already supports explicit live BOSS mode.

### Keep live BOSS behavior but leave it undocumented

- Pros: No immediate code changes.
- Cons: Future maintainers and agents will reintroduce contradictory assumptions and may weaken safety constraints accidentally.
- Rejected: The contradiction already caused architecture drift.

### Make live submission part of the default loop

- Pros: Fewer separate commands for users who want automation.
- Cons: Weakens the local-first safety model and increases blast radius from page-shape or validation errors.
- Rejected: Live behavior must stay explicit.

## Consequences

- `ARCHITECTURE.md` must describe explicit live BOSS mode instead of saying live platform interaction does not exist.
- Future refactoring should put BOSS browser actions behind a BOSS Adapter Interface.
- Submit diagnostics are part of the live-mode contract, not optional logging.
- Tests should continue to make dry-run behavior easy to verify without browser or credentials.
