# Test Plan

```bash
python -m unittest tests.test_power_distribution_recipe -v
bash scripts/validate.sh
```

Build twice from the same SHA and compare manifests and archive hashes.

Smoke-install into a clean directory and verify:

- `implementation-task-architect/SKILL.md` exists.
- Every listed reference resolves.
- `.task-me` is empty.
- `.ua/generated/task-plans` does not exist.
- No `task.yaml`, implementation plan, dashboard, Vercel file, Jira metadata, branch metadata, or PR metadata was generated.
- Reinstall is idempotent and unmanaged files are preserved.
- `doctor` returns success.
