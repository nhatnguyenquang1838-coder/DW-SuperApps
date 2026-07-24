# BMAD Power for DW SuperApps

The BMAD external Power wrapper packages an exact BMAD-METHOD source commit as a deterministic, skills-only DW distribution.

## Source

- Repository: `nhatnguyenquang1838-coder/BMAD-METHOD`
- Pinned analysis commit: `bb45db4aa4496c69239f9c0629c290fd1b072fc9`
- Observed BMAD version: `6.10.0`

## Distribution boundaries

Included:

- Core BMAD skills
- BMM lifecycle skills
- Shared scripts
- Official installer and host renderer
- DW bootstrap/config/contract overlay

Excluded:

- Website and documentation site
- Dashboard or UI
- Evals and repository tests
- Generated web bundles
- Project tasks, plans, and runtime data

## Build

Use `.github/workflows/publish-bmad-power.yml`.

The workflow builds:

```text
bmad-main-<source-sha>.zip
bmad-main-<source-sha>.zip.sha256
```

A manual run can validate without publishing. Scheduled or explicitly authorized runs publish the immutable release and synchronize `power-dist-bmad`.

## Consumer flow

```bash
dw power install bmad --source release --version main-<source-sha> --target /path/to/project
python /path/to/project/.dw/powers/bmad/distribution/lib/bootstrap_bmad.py \
  --target /path/to/project \
  --host codex
```

Then invoke the installed `bmad-help` skill to route into the correct lifecycle phase.

The manifest makes BMAD discoverable to the DW Power package runtime. It is not added to the legacy workspace submodule list, because release mode is authoritative for this external wrapper.

The wrapper does not grant repository, Jira, Slack, deployment, approval, or GWC gate authority.
