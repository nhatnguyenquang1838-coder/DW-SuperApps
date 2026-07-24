# Test Plan

## Contract

```bash
python -m unittest tests.test_power_distribution_contract -v
```

Cover missing required fields, unknown contract versions, invalid include patterns, runtime roots outside the consumer boundary, and conflicting output destinations.

## Builder

```bash
python -m unittest tests.test_power_dist_builder -v
```

Cover deterministic rebuild, allowlist-only copying, exclude precedence, symlink escape, path traversal, duplicate target, forbidden filename, secret pattern, populated runtime-data directory, and manifest mismatch.

## Runtime

```bash
python -m unittest tests.test_power_runtime_installer -v
```

Cover fresh install, repeated install, managed upgrade, unmanaged overwrite refusal, corrupt checksum, invalid contract, uninstall preserving runtime data, and explicit destructive cleanup.

## Regression

```bash
python -m unittest discover -s tests -p "test_*.py"
python scripts/dw_cli.py validate
python scripts/dw_cli.py host install all
python scripts/dw_cli.py host status all
```
