# ClaimGraph Schemas

`claimgraph-contract.schema.json` is the canonical JSON Schema draft 2020-12 contract for ClaimGraph artifacts. The schema root validates an `ArtifactEnvelope`; the envelope `body` is one of the domain contracts in `$defs`.

## Contracts

- `ArtifactEnvelope`: reproducible wrapper for every persisted artifact. It records `artifact_id`, `artifact_type`, `schema_version`, `created_at`, `producer`, `input_hash`, and the typed `body`.
- `ResearchRun`: top-level research execution snapshot containing `Task`, `Source`, `Evidence`, `Claim`, `ClaimEvidenceRelation`, and optional `Report` objects.
- `Task`: reproducible unit of work. It records input hash, model, prompt version, schema version, attempt count, status, timestamps, and stable error details when failed.
- `Source`: source metadata and content hash. Full source text is intentionally outside this contract.
- `Evidence`: short quote, summary, metric, table, or observation extracted from a `Source`. It references `source_id` and keeps a content hash plus within-source locator when available.
- `Claim`: atomic claim text with status and confidence. Supported, refuted, mixed, or reviewed status must be explained through relations.
- `ClaimEvidenceRelation`: typed edge from `Claim` to `Evidence`; relation type is `supports`, `refutes`, `qualifies`, or `mentions`.
- `Report`: ordered report container referencing `ReportStatement` entries.
- `ReportStatement`: report sentence or paragraph tied to a `Claim`.

## Status Enums

- `ResearchRunStatus`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `TaskStatus`: `queued`, `running`, `retrying`, `succeeded`, `failed`, `cancelled`
- `ClaimStatus`: `unsupported`, `supported`, `refuted`, `mixed`, `needs_review`
- `ReportStatus`: `draft`, `ready`, `published`, `failed`

## Minimum Invariants

The schema enforces these invariants:

- Every artifact is wrapped in an `ArtifactEnvelope`.
- `artifact_type` must match the concrete `body` definition.
- IDs use stable prefixes such as `rr_`, `task_`, `src_`, `ev_`, `clm_`, `rel_`, `rpt_`, and `stmt_`.
- Hashes use `sha256:<64 lowercase hex characters>`.
- Timestamps use JSON Schema `date-time` format.
- Terminal failed runs and tasks include a stable `error`.
- Completed or failed research runs include `completed_at`.
- Succeeded, failed, and cancelled tasks include `finished_at`.
- Report statements always reference a `claim_id`.
- Evidence always references a `source_id`; claim evidence relations always reference both `claim_id` and `evidence_id`.

Runtime code must additionally enforce graph invariants that JSON Schema cannot reliably prove by itself:

- All referenced IDs exist in the same `ResearchRun` or database snapshot.
- A `supported`, `refuted`, or `mixed` claim has at least one matching `ClaimEvidenceRelation`.
- `unsupported` claims are not hidden and are not treated as `supported`.
- Report statements reference claims from the same research run.
- State transitions follow the application transition table; the schema validates state names, not transition history.

## Fixtures

- `fixtures/valid-research-run.json`: valid research run envelope with one task, source, evidence item, claim, relation, and report.
- `fixtures/invalid-claim-status.json`: invalid claim envelope because `body.status` is `proven`, which is not in `ClaimStatus`.

## Validation

JSON parsing:

```sh
python3 -m json.tool packages/schemas/claimgraph-contract.schema.json >/dev/null
python3 -m json.tool packages/schemas/fixtures/valid-research-run.json >/dev/null
python3 -m json.tool packages/schemas/fixtures/invalid-claim-status.json >/dev/null
```

Schema validation with `jsonschema`:

```sh
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

base = Path("packages/schemas")
schema = json.loads((base / "claimgraph-contract.schema.json").read_text())
validator = Draft202012Validator(schema, format_checker=FormatChecker())

valid = json.loads((base / "fixtures/valid-research-run.json").read_text())
validator.validate(valid)

invalid = json.loads((base / "fixtures/invalid-claim-status.json").read_text())
errors = sorted(validator.iter_errors(invalid), key=lambda error: list(error.path))
assert errors, "invalid fixture unexpectedly passed validation"
print("valid fixture passed; invalid fixture failed as expected")
PY
```

If Python `jsonschema` is not installed in the local environment, run the JSON parsing commands above and report schema validation as a verification gap.
