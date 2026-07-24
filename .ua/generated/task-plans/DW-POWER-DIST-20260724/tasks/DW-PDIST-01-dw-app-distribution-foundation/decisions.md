# Decisions

## D1 — Provider-owned packages use one shared contract

- Evidence: DW-SuperApps already treats each Power as independently versioned.
- Alternative: centralize all provider package construction in DW-SuperApps.
- Decision: define the contract and reusable workflow centrally, but keep provider recipes in provider repositories.
- Confidence: high.

## D2 — Release ZIP and `power-dist` share one staging tree

- Reason: prevents content drift between download and submodule modes.
- Decision: publishing must fail if post-build comparisons differ.

## D3 — Gate Control remains disabled

- Evidence: explicit user direction supersedes the earlier approval token for this planning phase.
- Decision: create Task Me specs and Jira projections only; no GWC gate state or approval artifacts.
