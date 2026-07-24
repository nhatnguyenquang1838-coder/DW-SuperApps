# Test Plan

## Recipe validation

```bash
python -m unittest tests.test_power_distribution_recipe -v
```

Assert the recipe includes `skills/gwc-g1/SKILL.md`, all verified dependencies, and no forbidden runtime/history/UI content.

## Package build

Use the shared builder to create the package twice from the same GWC SHA. Compare manifest entries, file hashes, and archive hash.

## Standalone smoke test

```bash
./bin/install --target "$TMP_CONSUMER" --host custom
./bin/configure --target "$TMP_CONSUMER" --config config/example.yaml
./bin/doctor --target "$TMP_CONSUMER"
```

Verify:

- GWC skill entrypoint exists.
- All internal references resolve.
- `.gwc` exists and contains no task, gate, decision, envelope, or evidence record.
- No dashboard/frontend asset exists.
- Reinstall is idempotent.

Run the existing GWC validation suite before publishing.
