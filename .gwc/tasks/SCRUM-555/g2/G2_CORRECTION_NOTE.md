# G2 Correction Record — DW-OBS-G6-READINESS-R1

## Prior (structurally wrong) commit: f225928
- `G2(SCRUM-555): DW-OBS-G6-READINESS-R1 execution envelope`
- Flaw 1: `scope_hash` was computed by hashing the rendered YAML and writing
  the hash back into the same YAML — circular/ambiguous basis.
- Flaw 2: report omitted `expires_at`; exact G2 approval must bind current
  unexpired envelope.
- Flaw 3: `LOCAL_AGENT_RULE.md` proposal artifacts (written-proposal,
  change-plan, Mermaid/SVG/PNG + hashes) were not materialized.

This commit is **preserved as evidence** (not deleted). This record documents the
supersession.

## Corrected in this commit
- Canonical scope hash computed from `scope_inputs.json` (approved paths,
  actions, exclusions, exact base, risk, expiry), deterministic & auditable:
  `sha256:ff0af39b1f6f6077bd5633d7de7905cf0546c5241d43eaf7dab4dbd8b62f89b8`
  (generator: `g2/gen_scope_hash.py`). NOT a hash of the envelope.
- `execution-envelope.yaml` now carries `expires_at: '2026-08-24T14:30:00Z'`
  and `scope_hash_basis` documenting the real input source.
- Full G0 context-snapshot + G1 intake/preflight/options/decision artifacts added,
  each schema-valid; `validate_g01.py --gate G2_EXECUTION` => PASS.
- Proposal artifacts per `LOCAL_AGENT_RULE.md`: written-proposal.md,
  change-plan.yaml, overview.mmd, detailed.svg, detailed.png (REAL derived via
  macOS `qlmanage` offline renderer; 34371 bytes, 640x640 RGBA), artifact-hashes.txt.
  No placeholder/fabricated PNG or hash.

## Validator
`PYTHONPATH=tools python3 tools/validate_g01.py --root projects/gwc --workspace .gwc/tasks/SCRUM-555 --gate G2_EXECUTION` => **PASS** (exit 0).

## Approval command (binds current unexpired envelope)
```
APPROVE G2-SCRUM-555-OBS-G6-READINESS-R1 ff0af39b1f6f6077
```
