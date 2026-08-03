# GWC Governance Routing

Routing guidance for GWC (Governance, delivery control, approval boundaries,
validation, repository lifecycle) work on the `gwc` target project. GWC enforces
a single source of truth: the validated Power package in DW-SuperApps, not the
`projects/gwc` submodule. Reproduce all governance rules from the cited files at
execution time; do not rely on copies embedded elsewhere.

## The gwc submodule is NOT the authority

`projects/gwc` is a git submodule of DW-SuperApps, but the Power distribution
manifest declares the submodule a **compatibility fallback**. The authoritative,
validated package is `.dw/powers/gwc/`.

- `manifests/powers/gwc.yaml` (DW-SuperApps): `distribution.providerState.note`
  = "submodule remains a compatibility fallback".
- `.dw/powers/gwc/MANIFEST.json`: `kind: PowerPackageManifest`, pins `sourceSha`
  + `version`, and records a **sha256 for every governed file** under `files[]`.

**Boot invariant:** read governance from `.dw/powers/gwc/core/...` (validated
package). Verify a file's sha256 against MANIFEST when integrity matters. Treat
`projects/gwc/<file>` as a fallback to diff, never as authority. If the submodule
HEAD or a file sha256 diverges from the manifest, report it as a drift signal.

## SOT resolution order (start at DW-SuperApps, not the submodule)

1. **`workspace.yaml`** (DW-SuperApps) — enabled Powers, the `gwc` binding
   (`id: gwc`, `path: projects/gwc`, `source: nhatnguyenquang1838-coder/gwc`).
2. **`AGENTS.md`** (DW-SuperApps root) — discovery order, native Power activation,
   onboarding lifecycle, safety.
3. **`manifests/powers/gwc.yaml`** (DW-SuperApps) — Power distribution manifest:
   `version`, `spec.path`, `distribution.providerState.sourceCommit`, the
   "submodule = fallback" note.
4. **`.dw/powers/gwc/MANIFEST.json`** + validated dist evidence — installed package
   integrity (sha256 per file), `sourceSha`, `version`.
5. **`.dw/powers/gwc/AGENTS.md`** + `skills/gwc-g0/SKILL.md`, `skills/gwc-g1/SKILL.md`
   — canonical Power entrypoints.
6. **`projects/gwc/project-profile.yaml`** — repo, default branch, write_enabled,
   identity_status, connector.
7. **Governance contracts (from the validated package `.dw/powers/gwc/core/`):**
   - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md` — gate sequence, required artifacts,
     *separate exact approval per write-capable gate* (G2/G3/G4/G5/G6), "proactively
     generate the next gate's approval at prior gate exit".
   - `core/E2E_DRAFT_PR_DELIVERY_RULE.md` — G0→G4 lifecycle, Draft-PR stop, G5
     status-vs-deploy, mandatory post-G5 work-tracking projection (comment +
     legal transition + readback), JIRA_UPDATE_BLOCKED handling.
   - `core/GATE_APPROVAL_BEHAVIOR_RESCUE_v1.0.md` — exact approval command format
     `APPROVE <GATE> <approval_id> <scope_hash_16> <expires_at_utc>`; G4 requires a
     separate envelope bound to exact PR/repo/base/head/sha/method/expiry.
   - `core/workflows/GWC_FASTLANE_BOOTSTRAP_WORKFLOW_v0.1.md` — FastLane mode
     (conversation-local G0/G1, FastLane envelope, stops at Draft PR; not merge
     authority; sunset after REVAMP_UPGRADE_GWC).
8. **Issue body** (Jira MCP) for task-specific envelope fields / TDD plan.

## Delivery sequence (rules reproduced from the files above)

- Boot: resolve SOT (steps 1–7), then G0 read-only, G1 (FastLane conv-local).
- G2 FastLane envelope; require exact `APPROVE G2 …` before branch/commit.
- Own delivery: branch → impl → tests green → Draft PR (G3).
- **Proactively generate the G4 envelope + present the exact `APPROVE G4 …` line**
  at G3 exit (do not wait to be asked). G4 is a SEPARATE approval; never merge on
  a G2 token.
- On exact G4 token: verify approval_id + scope_hash_16 + head SHA + not-expired,
  mark PR ready, merge (squash), record `g4/merge-approval.yaml`.
- G5: no manual deploy in scope → read-only status verify (CI green), no G5
  envelope. Manual deploy/release → require separate G5 envelope.
- **Jira projection (post-G5, mandatory):** audit comment + legal status
  transition + readback. Jira is PROJECTION ONLY — never authoritative for gate
  decisions (see `core/integrations/GITHUB_G5_G6_JIRA_PROJECTION_CONTRACT_v0.1.md`).
- Provider unavailable / transition rejected → record JIRA_UPDATE_BLOCKED
  (provider, key, intended transition, error); never backdate/invent.

## Operational notes (not governance)

- Parallel-agent collision: if a target file mutates mid-task by another process,
  halt and surface it; do not silently verify/claim another agent's bytes.
- Branch drift vs envelope base_sha: classify SAFE_CONTINUE (unrelated changed
  files, authority/risk unchanged) vs BLOCK (semantic overlap) per the contracts.
- Jira MCP OAuth token (`~/.hermes/mcp-tokens/jira.json`) can expire mid-session →
  refresh via `hermes mcp test jira`, then re-read fresh. Jira tool mechanics are
  external to this routing file.
