# Test Plan

## Provider package matrix

For GWC, Task Me, and UA:

- Download exact release asset.
- Verify SHA-256 and manifest.
- Compare normalized contents with exact `power-dist` commit.
- Install into a clean application.
- Configure a minimal consumer contract.
- Run `doctor`.
- Upgrade from a prior fixture version.
- Roll back and confirm runtime data is preserved.

## DW regression

```bash
python -m unittest discover -s tests -p "test_*.py"
python scripts/dw_cli.py validate
python scripts/dw_cli.py host install all
python scripts/dw_cli.py host status all
python scripts/dw_cli.py power status all
```

## Hygiene

Fail on secrets, forbidden paths, populated runtime roots, dashboards/UI bundles, generated implementation tasks/plans in packages, duplicate manifests, temporary files, stale staging archives, dangling references, incompatible contract versions, or unrecorded provider SHAs.

## Final result

The branch may be marked `READY_FOR_GOVERNED_REVIEW`; it must not transition any GWC gate automatically.
