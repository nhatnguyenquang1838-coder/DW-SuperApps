# DW Power Agent Activation Contract

This is static distribution guidance generated when the package was built. It is not a task prompt, not a shell command, and not authority to perform external writes.

## Package identity

- Power: `ua`
- Package version: `main-361665807004`
- Source: `nhatnguyenquang1838-coder/ua@36166580700472d88bb80d7f3f1e7f257b8adf7f` (`main`)
- Target-owned runtime root: `.ua/`

## Required activation behavior

1. Read the workspace `AGENTS.md` and `workspace.yaml`.
2. Resolve exactly one target system and read its local instructions.
3. Read this contract, `POWER.yaml`, `SOURCE.json`, and `MANIFEST.json`.
4. Select the applicable skill entrypoint from the declared list below.
5. Apply that skill directly to the user's request in the current conversation.

A native alias selects a skill; it is not something to execute in a terminal. Do not create a prompt-export command, ask the user to copy a generated prompt, or merely describe the Power instead of applying it.

When multiple entrypoints exist, load only the entrypoint whose scope matches the current task. A non-`SKILL.md` entrypoint is a supporting executable or module and must not be run unless the selected skill explicitly requires it and current authority permits execution.

## Declared package entrypoints

- `understand-anything-plugin/skills/understand/SKILL.md`

## Ownership and safety

- Power package files remain in the DW-SuperApps workspace store.
- Runtime state and project configuration remain under the selected target's `.ua/`.
- Do not create a target-local `.dw/powers` installation.
- Installation, configuration, sanity, doctor, history, rollback, and uninstall are lifecycle operations; none of them grants merge, deployment, release, credential, migration, production-data, or approval authority.
