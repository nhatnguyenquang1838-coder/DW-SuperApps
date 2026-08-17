# Implementation plan

**Fresh implementation session required.** Use TDD and exact-base drift readback before modifying source.

## Step 1
Introduce a focused materialization contract model that binds repository, exact base/ref/SHA, authoritative runtime/schema/manifest refs, selected scope, evidence identity, and a deterministic digest.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 2
Introduce a bounded transitive-effect graph model with trigger, determinism, affected repo/environment, mutation capability, required authority and expected readback for each reachable child effect.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 3
Add a pre-dispatch validator that fails closed on missing/stale materialization, unauthorized deterministic child effects, cross-repo authority borrowing, or ambiguous execution evidence identity.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 4
Bind the validated preflight receipt/digest into DispatchEnvelope/continuation state without turning it into new authority.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 5
Add a fresh-session handoff record that binds repo lane, task/issue, spec PR/head, Task-Me package, GG revision, scope/non-goals/dependencies and next required authority.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Step 6
Cover missing materialization, deterministic release child, safe read-only child, cross-repo child, PR-head-vs-merge-SHA confusion, drift/replay and recovery in focused tests.

Validation checkpoint: run the narrowest relevant RED/GREEN tests and inspect the complete diff before proceeding.

## Delivery boundary
Implementation commits belong to a fresh G2-authorized implementation branch/session, not this spec-only branch. G3/G4/G5/G6 remain separate authority boundaries.
