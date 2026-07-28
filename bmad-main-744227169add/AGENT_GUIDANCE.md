# DW Power Agent Activation Contract

This is static distribution guidance generated when the package was built. It is not a task prompt, not a shell command, and not authority to perform external writes.

## Package identity

- Power: `bmad`
- Package version: `main-744227169add`
- Source: `nhatnguyenquang1838-coder/bmad@744227169addadb50d8b946777939a73207970f3` (`main`)
- Target-owned runtime root: `.bmad/`

## Required activation behavior

1. Read the workspace `AGENTS.md` and `workspace.yaml`.
2. Resolve exactly one target system and read its local instructions.
3. Read this contract, `POWER.yaml`, `SOURCE.json`, and `MANIFEST.json`.
4. Select the applicable skill entrypoint from the declared list below.
5. Apply that skill directly to the user's request in the current conversation.

A native alias selects a skill; it is not something to execute in a terminal. Do not create a prompt-export command, ask the user to copy a generated prompt, or merely describe the Power instead of applying it.

When multiple entrypoints exist, load only the entrypoint whose scope matches the current task. A non-`SKILL.md` entrypoint is a supporting executable or module and must not be run unless the selected skill explicitly requires it and current authority permits execution.

## Declared package entrypoints

- `distribution/skills/bmad/SKILL.md`

## Ownership and safety

- Power package files remain in the DW-SuperApps workspace store.
- Runtime state and project configuration remain under the selected target's `.bmad/`.
- Do not create a target-local `.dw/powers` installation.
- Installation, configuration, sanity, doctor, history, rollback, and uninstall are lifecycle operations; none of them grants merge, deployment, release, credential, migration, production-data, or approval authority.
