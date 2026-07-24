# Implementation Plan

1. Collect exact completion evidence from SCRUM-90 through SCRUM-93: repository, branch, commit, workflow version, contract version, release assets, checksum, manifest, and `power-dist` commit.
2. Reject or reconcile any provider using a different incompatible contract/workflow version.
3. Extend `manifests/powers/gwc.yaml`, `task-me.yaml`, and `ua.yaml` with release and submodule distribution sources while preserving capabilities, permissions, entrypoints, and runtime roots.
4. Implement DW consumer commands for install, configure, doctor, history, upgrade, rollback, and uninstall.
5. Keep current source-submodule commands available and make migration mode explicit.
6. Install all three packages into clean fixture applications on supported operating systems and hosts.
7. Validate checksum, manifest, provenance, entrypoint closure, authority contracts, and runtime-root ownership.
8. Compare each release ZIP with its `power-dist` tree after normalization.
9. Run hygiene scans across all touched repositories and the final DW branch.
10. Produce the final compatibility matrix, known limitations, rollback instructions, and readiness evidence without creating gate artifacts.
