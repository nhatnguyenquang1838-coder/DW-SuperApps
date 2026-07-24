# Implementation Plan

1. Create or approve `nhatnguyenquang1838-coder/ua-power` as a fork or wrapper repository.
2. Initialize `SOURCE.lock.json` with upstream `Egonex-AI/Understand-Anything`, branch `main`, and exact baseline SHA `6ae71878beb50226a1e4b7e2f52ac6468c86f74b`.
3. Add a read-only upstream-check script that reports drift without changing the lock.
4. Inventory the `understand` skill and verify every referenced agent, helper script, dependency file, license, and notice.
5. Create the explicit package recipe and forbidden-content rules.
6. Add manual and scheduled sync workflow: detect, stage, validate, publish, then update the source lock only after success.
7. Generate immutable release assets and `power-dist` from the same staging tree.
8. Smoke install into an empty application and verify the package has no dashboard or extension behavior.
9. Record controlled repository commit, upstream SHA, release version, and distribution commit for Task 05.
