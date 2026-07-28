# HEARTBEAT.md - Quiet workspace maintenance

Run these checks only during a scheduled heartbeat. Stay silent when everything
is healthy; report only actionable drift or failures.

## DW skill and package-store checks

- Confirm the canonical store exists at `.dw/powers/`.
- Confirm the enabled Power directories exist: `gwc`, `ua`, `task-me`, and `bmad`.
- Confirm each installed Power has `MANIFEST.json`, `POWER.yaml`, and `VERSION`.
- Confirm the selected system bindings remain under `.dw/bindings/`.
- Prefer the installed package entrypoints under `.dw/powers/<power-id>/`; do not
  fall back to `projects/` unless the package is missing or a compatibility
  fallback is explicitly required.
- Do not rebuild, reinstall, modify runtime configuration, or send external
  messages from a heartbeat.

If a check fails, report the exact path and a concise repair recommendation.
