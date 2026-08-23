# dw-observation

DW Run Observatory — a **read-only, deterministic projection** of DW-SuperApps /
GWC execution state. Source-of-truth binding only; this app never mutates
governance, never parses Slack, and never writes to GWC.

## Scope (M0 / SCRUM-555 / node #71)

- `RunProjectionEvent` v1 — the canonical event record projected by the app.
- Read-only adapters: `TaskControllerAdapter`, `GwcAdapter` (pull only).
- `projector.reduce(events)` — **deterministic reducer** (stable ordering, no
  wall-clock/random dependence beyond explicit event timestamps).
- Golden fixtures + replay tests (reproducible, no network).

## Non-goals (excluded by contract)

- No Slack parsing.
- No governance mutation (no G0..G6, no approval writes, no Jira writes).
- No GWC repo mutation. GWC is bound as **app-owned read-only metadata** to
  `nhatnguyenquang1838-coder/gwc@pre-prod@10deaa4d…` (DurableEvent schema). The
  root `projects/gwc` Power integration pin and `.gitmodules` are owned by the
  Power manifest / compatibility lock and are out of this app's scope.
- No deploy / release / production config / secrets.

## Layout

```
dw_observation/
  events.py        # RunProjectionEvent v1 model + validation
  adapters.py      # TaskControllerAdapter, GwcAdapter (read-only)
  reducer.py       # deterministic reduce(events) -> Projection
  projection.py    # Projection dataclasses
  fixtures.py      # golden fixture loader (local JSON only)
tests/
  test_events.py
  test_reducer.py
  test_adapters.py
  test_fixtures.py
fixtures/
  run_scrum555_m0.json     # golden event stream
  projection_scrum555_m0.json  # golden expected projection
```
