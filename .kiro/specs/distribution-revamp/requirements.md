# Requirements

## Requirement 1: Tag/download-only distribution

**User Story:** As a DW SUPER maintainer, I want offline packages to be published from tags or release downloads, so that source branches do not contain generated ZIP artifacts.

### Acceptance Criteria

1. WHEN a release is built, THE release builder SHALL write generated ZIPs only under the configured release output directory.
2. WHEN a PR is opened, THE repository SHALL contain source, specs, schemas, tests and workflows but not generated release ZIPs.
3. WHEN an offline operator installs a release, THE operator SHALL use downloaded artifacts plus evidence files.

## Requirement 2: Release evidence

**User Story:** As an offline operator, I want every artifact to include verifiable evidence, so that I can install without network access.

### Acceptance Criteria

1. WHEN a release is built, THE builder SHALL emit `MANIFEST.json`, `SOURCE_LOCK.json`, `SHA256SUMS.txt` and `VALIDATION_REPORT.json`.
2. WHEN an installer verifies a release, THE installer SHALL reject missing evidence.
3. WHEN checksums differ, THE installer SHALL stop before mutation.

## Requirement 3: Runtime preservation

**User Story:** As a Super App owner, I want package installation to preserve runtime data, so that updates do not destroy `.ua`, `.task-me`, `.bmad` or application source.

### Acceptance Criteria

1. WHEN a release is installed, THE installer SHALL write package payloads under workspace `.dw/powers`.
2. WHEN runtime roots exist, THE installer SHALL preserve `.gwc`, `.ua`, `.task-me` and `.bmad`.
3. WHEN an installed component already exists, THE installer SHALL require explicit `--force` before replacement.

## Requirement 4: Branch conversion

**User Story:** As a maintainer, I want the legacy Kiro offline branch to become evidence, not authority, so that future delivery is reproducible.

### Acceptance Criteria

1. WHEN comparing `kiro-offline-distribution`, THE implementation SHALL document that it contains ZIP/checksum delivery output only.
2. WHEN future releases are needed, THE workflow SHALL build assets from source and publish them from a tag or manual release workflow.
