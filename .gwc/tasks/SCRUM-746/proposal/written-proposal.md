# SCRUM-746: Pre-plan Materialization — Intent/G0-G1 Context → GovernedExecution

## 1. Problem Statement

The TaskController controlplane (WP5 S2-S3) provides bounded control intents
(PAUSE, RESUME, CANCEL, REPLAN) over the runtime store via CAS-guarded
state mutations. However, the **pre-plan materialization** path — transforming
Intent/G0-G1 context into a **GovernedExecution** envelope — lacks canonical,
auditable artifacts in the repository.

The Intent/G0-G1 context currently lives in conversation memory and scattered
design notes (notably the W4 `GovernedExecutionBlueprint→RuntimePlan` compiler
on the `runtimeplan/w4` branch, commit `10a87897`). This context has not been
materialized as schema-valid, scope-hashed, GWC-gated evidence that a downstream
TaskController can consume as a `GovernedExecutionBlueprint` for `RuntimePlan`
compilation.

## 2. Desired Outcome

Produce the complete G0 → G1 → G2 artifact chain under
`.gwc/tasks/SCRUM-746/`:

- **G0**: Context snapshot — repository identity, base SHA, sources, constraints.
- **G1**: Intake brief, preflight report, options, decision record — all
  schema-valid and traceable to the same task/repository/base SHA.
- **G2**: Execution envelope with a deterministic `scope_hash` computed from
  `scope_inputs.json` via sha256 over canonical sorted-key JSON, declaring
  bounded `authorized_actions` and explicit `excluded_actions`.

This closes the gap between controller intent and executable governance by
providing the canonical evidence a downstream W4 compiler requires.

## 3. Scope

### In Scope

- Materialize G0 context snapshot for SCRUM-746.
- Materialize G1 intake brief, preflight report, options, and decision record.
- Materialize G2 execution envelope with scope hash + authorized/excluded actions.
- Bind the envelope to current main HEAD (`eb6d611b`).
- Generate proposal artifacts (this document, change-plan, overview, detailed
  diagram, artifact hashes, approval envelope) per `LOCAL_AGENT_RULE.md`.
- No repository source mutation outside `.gwc/tasks/SCRUM-746/`.

### Non-Goals

- Create a Git branch, worktree, commit, or push (G2 gate not active).
- Modify `taskcontroller/` source files.
- Merge, deploy, or production-data operations.
- Grant G4_MERGE, G5_DEPLOY, or G6_PRODUCTION_DATA authority.
- Activate runtime fan-out or cross-review.

## 4. Constraints

- No repository mutation outside `.gwc/tasks/SCRUM-746/`.
- GWC repo remains read-only during this gate.
- TaskController modules must remain framework-neutral (no Slack/Hermes/GWC
  imports in WP0-WP5 core).
- `LOCAL_AGENT_RULE.md` §2 applies: proposal artifacts only in an isolated
  session directory; no repository writes before exact G2 approval.

## 5. Risks

| ID | Description | Impact | Mitigation |
|----|-------------|--------|------------|
| RISK-1 | Scope hash drift if G0/G1 context inputs change | High | Compute scope hash from canonical sorted-key JSON; regenerate on any input change |
| RISK-2 | Artifacts may not schema-validate | Medium | Validate against documented G0/G1/G2 structure |
| RISK-3 | Envelope may over-grant authority | High | Explicitly exclude merge/deploy/production actions; authorize only create_task_artifacts, write_docs, record_gate_evidence |

## 6. Acceptance Criteria

1. G0 context snapshot is schema-valid (schema_version, artifact_type,
   repository identity, base SHA, sources, status=READY, no blockers).
2. G1 intake/preflight/options/decision are present, schema-valid, and
   traceable to the same task/repository/base SHA.
3. G1 preflight report outcome is PASS with all checks passing.
4. G2 execution envelope has a deterministic scope_hash from
   scope_inputs.json.
5. G2 execution envelope explicitly excludes merge, deploy, production data,
   credential rotation, protected-branch write, force-push, and GWC repo
   mutation.
6. Proposal artifacts (written-proposal, change-plan, overview.mmd,
   detailed.svg/png, artifact-hashes.txt, approval-envelope.yaml) are
   generated per LOCAL_AGENT_RULE.md.
