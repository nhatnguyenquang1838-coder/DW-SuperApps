# DW SUPER Power Dist Onboarding Prompt

```text
Onboard DW SUPER Power Dist for the current target project and host environment.

Treat DW-SuperApps as the distribution and host-control workspace. Treat the selected product project as the owner of runtime and project configuration only.

Read:
1. AGENTS.md
2. workspace.yaml
3. docs/runbooks/POWER_DIST_ONBOARDING.md
4. docs/PORTABLE_MULTI_HOST_ROUTER.md
5. target-project instructions and selected Power manifests

Execute:
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT

Requirements:
- Install packages under workspace `distribution.storeRoot`, default `DW-SuperApps/.dw/powers/<power-id>/`.
- Read offline ZIPs from `DW-SuperApps/.dw/inbox/powers/<power-id>/`.
- Keep `--target` as the project runtime target.
- Use `--store-root` only for tests or explicit external workspace layouts.
- Write runtime and configuration only under declared project roots such as `.gwc`, `.ua`, `.task-me`, `.bmad`, `_bmad`, and `_bmad-output`.
- Generate host adapters only in DW-SuperApps.
- Resolve installed package entrypoints before source submodules.
- Never create `<project>/.dw/powers` or Power host-skill payloads in the project.
- Detect existing `<project>/.dw/powers/<power-id>` as LEGACY_TARGET_INSTALL and preserve it.
- Split BMAD ownership: package and host skills in DW-SuperApps; project configuration/output in the target project.
- Validate package integrity, binding, runtime, configuration, host routing, dedupe, legacy preservation, and one real invocation.
- Do not claim READY when any required layer is incomplete.

Use:
./bin/dw power install <power-id> --source auto --target projects/<project-id>
./bin/dw host install all --mode wrapper

Return workspace store and target runtime paths separately, all changed paths, evidence, legacy warnings, rollback/uninstall behavior, and READY/PARTIAL/BLOCKED/FAILED status.
```
