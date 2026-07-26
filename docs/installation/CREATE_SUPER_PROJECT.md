# Create a Super Project

## Prerequisites

- Git
- Python 3
- Bash or a shell capable of running the provided launcher
- One existing DW-SuperApps checkout to export the governed runtime

## Create

```bash
cd /path/to/DW-SuperApps
dw workspace init ../delivery-super \
  --id delivery-super \
  --name "Delivery Super"
```

The target must be empty unless `--in-place` is supplied. Existing `workspace.yaml` and existing managed runtime paths are never overwritten.

## Install the command

```bash
cd ../delivery-super
bash bin/dw install --shell auto
source ~/.zshrc
```

## Verify the empty workspace

```bash
dw project list
dw power list
dw validate
dw doctor all --offline
```

An empty registry is valid. Readiness for a real workload requires at least one registered system and the required installed Powers.
