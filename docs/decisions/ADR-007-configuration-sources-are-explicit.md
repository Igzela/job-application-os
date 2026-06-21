# ADR-007: Configuration Sources Are Explicit

## Status

Accepted

## Date

2026-06-20

## Context

Configuration and the LLM provider separately parsed `.env`, mutated
`os.environ`, and silently read Claude Code credentials. Tests could therefore
depend on operator machine state.

## Decision

Configuration precedence is:

1. Explicit function or CLI configuration.
2. Process environment.
3. `~/.jobos/.env`.
4. `~/.jobos/config.yaml`.
5. Deterministic mock fallback.

Parsing `.env` must not mutate process environment. Claude Code configuration
is read only when `use_claude_config=True` is explicitly supplied.

## Consequences

- Tests and commands are reproducible.
- Credential provenance is visible.
- Real providers remain available without changing dry-run defaults.
