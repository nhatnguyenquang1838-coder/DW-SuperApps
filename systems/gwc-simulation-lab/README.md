# GWC Simulation Lab

Deterministic test project for exercising the GWC 81-node catalog and 14 materialized canonical scenarios with 100 task seeds.

## What it tests

- all 81 runtime node IDs are visited;
- all 14 materialized scenarios are exercised;
- the 116 declared-scenario invariant is retained as source metadata;
- six required failure cases are injected;
- human boundaries are crossed only by a synthetic mock-human envelope;
- every synthetic envelope is non-authoritative and cannot be used outside simulation.

## Run

```bash
python systems/gwc-simulation-lab/tools/simulate.py --strict
python -m unittest -v tests.test_gwc_simulation_lab
```

Reports are written to `systems/gwc-simulation-lab/.simulation/latest/`.

## Mock-human safety

The mock agent produces `APPROVE_SIMULATION`, never a real GWC approval command. Every envelope contains:

```json
{
  "simulation_only": true,
  "real_authority": false,
  "external_side_effects_allowed": false,
  "executable_outside_simulation": false
}
```

This lets automation test human-boundary handling without bypassing governance.
