-- Cover DWO native read-model foreign keys and primary query paths.
CREATE INDEX IF NOT EXISTS idx_run_gates_run_id
  ON public.run_gates (run_id);

CREATE INDEX IF NOT EXISTS idx_run_nodes_run_id
  ON public.run_nodes (run_id);

CREATE INDEX IF NOT EXISTS idx_run_nodes_gate_id
  ON public.run_nodes (gate_id)
  WHERE gate_id IS NOT NULL;
