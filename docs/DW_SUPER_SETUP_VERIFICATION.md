# DW SuperApps Setup Verification

Task: `SCRUM-134`  
Parent: `SCRUM-94`

## Verified execution

- Workflow run: `30120434434`
- Validated head: `17e9e833746e91eb6eedd7a10a6d02cef8414138`
- Job: `setup`
- Result: `completed / success`
- Artifact: `scrum-134-setup-30120434434`
- Artifact digest: `sha256:a58c7996d476e998944daa17a5b9daf90d80a447248d02902da385bb779972e0`
- Canonical evidence: `manifests/evidence/SCRUM-134/setup-evidence.json`

The following flows passed on an Ubuntu GitHub-hosted runner with Python 3.12:

1. Install the managed `dw` launcher using `--shell none`.
2. Initialize and inspect the reviewed Power submodules.
3. Install and verify Kiro wrapper adapters.
4. Install and verify Codex wrapper adapters.
5. Validate the workspace registry and manifests.
6. Generate GWC, UA, and Task Me prompts for `rental-home`.

## Vercel separation

Task Me Vercel deployment was not executed. The selected follow-up strategy is to gate preview and production deploy jobs behind:

```yaml
if: vars.VERCEL_DEPLOY_ENABLED == 'true'
```

When enabled, the Task Me repository must separately provide:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

No credential, secret, release, `power-dist` publication, deployment, runtime reload, or protected-main operation was performed during setup verification.
