# BMAD Method External Power

This wrapper turns an exact BMAD-METHOD commit into a DW Power package without modifying the upstream repository.

## Included

- BMAD core skills
- BMM lifecycle skills
- Shared runtime scripts
- Official BMAD installer
- Portable DW bootstrap, configuration, and consumer contract

## Excluded

- Documentation website
- Dashboard/UI
- Evals and repository tests
- Generated web bundles
- Generated project tasks, plans, and runtime data

## Build model

The GitHub workflow checks out BMAD at an exact ref, overlays `overlay/distribution`, runs the DW deterministic package builder, verifies the manifest, smoke-installs the package, and performs a bootstrap preflight.

The package is published from DW-SuperApps because BMAD remains an external independently versioned source.

## Publication

A validated push to `main` publishes an immutable release for the exact BMAD source SHA and synchronizes the same staging tree to `power-dist-bmad`. Pull requests and feature branches build and upload validation artifacts without publishing releases.
