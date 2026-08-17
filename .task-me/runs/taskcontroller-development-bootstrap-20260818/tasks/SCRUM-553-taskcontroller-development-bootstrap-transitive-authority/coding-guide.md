# Coding guide

## Existing patterns to preserve
- Keep `dispatch.py` focused on dispatch invariants; prefer a focused preflight/materialization module rather than embedding workflow discovery policy directly in the transport path.
- Preserve immutable/digest-based dataclass patterns in `taskcontroller/execution/types.py`.
- Preserve continuation CAS/readback discipline in `taskcontroller/interaction/continuation.py`.
- Authority remains external; `APPROVE`/`MERGE` UI intent must not become authority.

## Forbidden shortcuts
- No invented semantic remapping.
- No implicit authority inheritance from a prior gate or successful historical workflow.
- No cross-repository authority borrowing.
- No treating absence of observable workflow evidence as PASS.
