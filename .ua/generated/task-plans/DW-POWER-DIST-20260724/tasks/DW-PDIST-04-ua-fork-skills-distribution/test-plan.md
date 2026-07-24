# Test Plan

## Upstream lock

Test unchanged upstream, changed upstream, invalid SHA, unavailable upstream, candidate package failure, and successful validated lock update.

## Package

Build twice from the same upstream SHA and compare manifest and archive hashes. Assert the package includes the `understand` skill, all verified helpers, minimal dependency metadata, license, and notices.

## Forbidden content

Assert no dashboard, web application, VS Code extension, marketing asset, screenshot, historical planning/spec folder, or populated `.ua` runtime data exists.

## Smoke install

```bash
./bin/install --target "$TMP_CONSUMER" --host custom
./bin/configure --target "$TMP_CONSUMER" --config config/example.yaml
./bin/doctor --target "$TMP_CONSUMER"
```

Verify `.ua` is empty, no dashboard command is exposed, no server starts, and no network call occurs during installation.
