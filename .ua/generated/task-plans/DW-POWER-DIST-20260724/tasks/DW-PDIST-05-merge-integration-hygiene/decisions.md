# Decisions

## D1 — “One branch” means one logical branch name and one final DW integration branch

Git branches are repository-local. Provider tasks may use the same branch name in their repositories, while Task 05 records exact provider SHAs and consolidates the consumer integration in DW-SuperApps.

## D2 — Preserve legacy mode

Release ZIP becomes the recommended consumption strategy only after validation. Existing source-submodule commands remain available during migration.

## D3 — No protected-main merge

Task 05 merges task outputs into `feat/dw-power-distribution-v1` only. Later review and Gate Control require a new explicit instruction.

## D4 — Hygiene is blocking

Any forbidden content, secret, dangling reference, incompatible contract, package mismatch, or unrecorded source SHA blocks readiness.
