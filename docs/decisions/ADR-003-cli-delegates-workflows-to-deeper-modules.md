# ADR-003: CLI Delegates Workflows To Deeper Modules

## Status

Accepted

## Date

2026-06-17

## Context

`jobos/cli.py` currently registers commands, parses arguments, reads and writes state, loads files, executes business workflows, handles errors, and renders user output.

That makes the CLI a shallow Module: its Interface exposes every command detail, while its Implementation duplicates workflow knowledge that TUI, REPL, loop, tests, and future agents also need.

The roadmap calls for CLI to become a shell over deeper Modules.

## Decision

CLI should delegate workflow behavior to deeper Modules and keep only command-specific concerns:

- Argument parsing.
- Exit codes.
- Human-readable output.
- Translating command-line flags into workflow options.

Business behavior should move behind public Interfaces on Modules such as Workspace State, Pipeline, Application Pack, Submission, BOSS Adapter, and other domain Modules.

Migration should be incremental. Existing `_cmd_*` handlers can remain while their internals are replaced with calls to deeper Interfaces.

## Alternatives Considered

### Keep CLI as the workflow owner

- Pros: Simple call path for command execution.
- Cons: Prevents reuse by TUI/REPL/tests and keeps state/file rules scattered.
- Rejected: This is the current friction point.

### Rewrite the CLI framework

- Pros: Could improve command organization.
- Cons: Does not address workflow locality by itself.
- Rejected: The problem is Module depth, not argparse.

### Move all commands into one new orchestration Module

- Pros: Quickly reduces `cli.py` size.
- Cons: Risks creating another shallow Module with the same responsibilities.
- Rejected: Workflows should move to the Modules that own their facts and invariants.

## Consequences

- New workflow behavior should not be implemented directly in CLI handlers.
- Tests should prefer deeper Module Interfaces when those Interfaces exist.
- CLI tests should focus on argument handling, output shape, and exit behavior.
- The final CLI should be visibly thinner, but migration can proceed one command family at a time.
