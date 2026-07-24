# Impact Analysis

## Direct impact

- Updates DW-SuperApps manifests and CLI to consume release ZIPs or `power-dist` branches.
- Reconciles independently implemented provider recipes/workflows against one contract version.
- Establishes compatibility, upgrade, rollback, and hygiene evidence.

## Integration risks

- Provider tasks may pin different shared workflow commits or contract versions.
- File naming, archive layout, runtime roots, and checksum conventions may drift.
- Cross-repository commits cannot literally share one Git branch, so integration must record exact provider SHAs while maintaining the same logical branch name.
- Legacy DW submodule behavior could regress.
- Temporary task output, package staging, generated adapters, or runtime data could be committed accidentally.

## Controls

- Build a compatibility matrix from exact provider commit/release SHAs.
- Rebuild all packages in a clean environment.
- Compare release assets to `power-dist` content.
- Run existing DW tests plus new consumer tests.
- Run repository hygiene and secret scans before declaring readiness.
