# Scripts

Repository helper scripts are written to work from any current directory. Each script resolves the repository root from its own location.

## `validate-schemas`

Checks that `packages/schemas` contains JSON schema files and `tests/eval` contains JSON fixture files, then parses every `*.json` file in both directories with Python's standard JSON parser.

Current behavior on an empty schema/fixture scaffold is an explicit failure. This keeps contract validation from passing silently before schemas and fixtures exist.

```sh
scripts/validate-schemas
```

## `test-contracts`

Runs `tests/integration/test_contracts.py` with `pytest` when that file exists.

If the integration contract test file has not been added yet, the script prints a readiness message and exits successfully so CI or local setup can include the runner before the test suite exists.

```sh
scripts/test-contracts
```
