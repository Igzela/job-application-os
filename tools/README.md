# Tools

CLI commands provided by the `job` entry point (`jobos.cli`).

| Command | Module | Description |
|---------|--------|-------------|
| `job init` | `cli.py` | Create workspace directory structure |
| `job import --file <path>` | `importer.py` | Parse a text/markdown job description into normalized YAML |
| `job score --job <id>` | `scorer.py` | Score resume against job (6 dimensions: fit, evidence, opportunity, strategic, friction, risk) |
| `job predict --job <id>` | `predictor.py` | Produce an immutable prediction with go/no-go decision and funnel probabilities |
| `job pack --job <id>` | `pack_generator.py` | Generate application pack (targeted resume, cover letter, greeting, form answers, checklist) |
| `job dry-run --job <id>` | `dry_run.py` | Fill a local mock HTML form with pack data; never hits the network |
| `job mark-submitted --job <id> --channel <ch>` | `retro.py` | Record that an application was submitted |
| `job retro --job <id>` | `retro.py` | Record outcome data at 3/14/30-day marks |
| `job status` | `status.py` | Regenerate `STATUS.md` from pipeline state |
| `job bump-rubric --new-rubric <path>` | `rubric_manager.py` | Create a candidate rubric and compare against the active one using historical retro data |

## Supporting Modules

| Module | Purpose |
|--------|---------|
| `profile_loader.py` | Merge `profile/*.yaml` and `evidence_bank.md` into a single profile dict |
| `models.py` | Data classes (`Job`, `Prediction`, `ApplicationPack`, etc.) |
| `adapters/local_mock_form/` | Stub HTML form used by `dry-run` |

## Pipeline Order

```
import -> score -> predict -> pack -> dry-run -> mark-submitted -> retro
```

`status` and `bump-rubric` are orthogonal utilities that read pipeline state.
