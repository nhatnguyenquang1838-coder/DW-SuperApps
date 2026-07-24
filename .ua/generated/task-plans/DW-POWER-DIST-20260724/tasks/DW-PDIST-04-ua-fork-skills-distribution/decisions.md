# Decisions

## D1 — Use a controlled fork or wrapper

The upstream is read-only. Distribution automation and releases therefore belong in a user-controlled repository.

## D2 — Exact upstream lock

Scheduled checks detect drift, but the lock moves only after a candidate package validates. DW-SuperApps pins remain a later Task 05 decision.

## D3 — Headless skill only

Dashboard, web UI, extension, screenshots, and historical plans/specs are outside scope even when present upstream.

## D4 — No upstream modification

No branch, issue, workflow, release, or commit is created in `Egonex-AI/Understand-Anything`.
