# Impact Analysis

## Direct impact

- Adds a new controlled source repository or fork under the user's GitHub account.
- Introduces exact upstream locking, drift detection, and package publishing.
- Changes the future DW-SuperApps UA source from an external development repository to a controlled distribution source.

## Risks

- Fork divergence from upstream.
- License/notice omission when curating files.
- Missing helper scripts or agents referenced by the `understand` skill.
- Accidental inclusion of dashboard, web, extension, screenshots, or historical planning content.
- Scheduled automation silently moving the consumer source pin.

## Controls

- `SOURCE.lock.json` with repository, branch, and exact SHA.
- Drift check creates evidence and validates a candidate package before moving the lock.
- No automatic consumer pin update.
- Include required license and notices.
- Explicit allowlists and reference-closure tests.
