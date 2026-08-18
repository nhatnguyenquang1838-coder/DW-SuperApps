# Implementation plan

**Fresh implementation session required.** Use TDD and exact-base drift readback before modifying source. SCRUM-553 consumes the normative capability/effect semantics owned by SCRUM-554; it MUST NOT create a parallel policy vocabulary.

## Step 1 — Materialized execution contract
Introduce a focused materialization contract model that binds repository, exact base/ref/SHA, authoritative runtime/schema/manifest refs, selected scope, evidence identity, and a deterministic digest. Missing or stale identity blocks dispatch.

Validation checkpoint: RED/GREEN tests for missing/stale materialization and exact-base drift; inspect the complete diff.

## Step 2 — Transitive-effect observation model
Materialize a bounded effect graph with trigger, predicate/condition evidence, determinism, affected repo/environment, capability, required authority and expected readback for each child effect. **GWC (SCRUM-554) owns the capability and closure semantics.** TaskController records/consumes them; it does not reinterpret gate labels into a second authority model.

Conditional-edge handling consumed from GWC:
- predicate proven `false` -> child may be excluded, with predicate evidence bound to the parent action identity;
- predicate `true` -> child is reachable and participates in authority closure;
- predicate `unknown` -> any mutating, cross-repo, release, destructive or production-capable child is treated as potentially reachable and must be independently authorized for its worst-case capability or dispatch is blocked;
- unresolved read-only/compute children may remain non-escalating but are still recorded.

Validation checkpoint: cover true/false/unknown predicates and cross-repo effects.

## Step 3 — Pre-dispatch fail-closed validator
Add a pre-dispatch validator that fails closed on missing/stale materialization, missing/drifted GWC effect-policy identity, unauthorized deterministic or potentially reachable conditional mutations, cross-repo authority borrowing, or ambiguous execution evidence identity.

Validation checkpoint: ensure an authorized direct action plus an unauthorized child cannot reach adapter dispatch.

## Step 4 — Receipt and continuation binding
Bind the validated materialization/effect receipt and policy digest into `DispatchEnvelope`/continuation state without turning the receipt into authority. Recovery/replay must preserve the same execution identity; drift invalidates stale evidence.

Validation checkpoint: replay equivalence, semantic drift conflict, continuation recovery, PR-head-vs-merge-SHA evidence separation.

## Step 5 — Fresh-session handoff identity
Emit a bounded handoff record that binds repo lane, Jira/GitHub issue, spec PR number, exact spec head, Task-Me package identity, GG identity, dependencies, non-goals and next required authority.

The handoff identity MUST contain:
- `spec_pr` + exact `spec_head_sha`;
- `task_me_package_sha256`, computed over sorted `(relative_path, sha256(file_bytes))` entries for the canonical Task-Me task package, excluding the handoff record itself;
- GG document revision, `Version: 2026-08-18`, `Edition: LLM-Semantic 2.3`, section name, and SHA-256 of the exact normalized UTF-8 Section 1A text at handoff time;
- exact normative SCRUM-554 capability/effect contract version/digest consumed by implementation.

Validation checkpoint: any mismatch in spec head/package/GG/GWC-policy identity blocks implementation bootstrap.

## Step 6 — Regression coverage
Cover missing materialization, deterministic release child, conditional mutating child (`true`/`false`/`unknown`), safe read-only child, cross-repo child, historical successful automation reused as authority, PR-head-vs-merge-SHA confusion, drift/replay and recovery.

Validation checkpoint: narrow tests first, then full TaskController suite and complete diff review.

## Delivery boundary
Implementation commits belong to a fresh G2-authorized implementation branch/session, not this spec-only branch. G3/G4/G5/G6 remain separate authority boundaries.
