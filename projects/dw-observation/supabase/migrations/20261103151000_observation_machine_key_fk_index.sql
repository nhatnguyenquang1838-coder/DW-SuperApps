-- Performance guard for the GWC v2 observation machine-key binding.
CREATE INDEX IF NOT EXISTS idx_observation_machine_keys_source_id
  ON observation_machine_keys (source_id);
