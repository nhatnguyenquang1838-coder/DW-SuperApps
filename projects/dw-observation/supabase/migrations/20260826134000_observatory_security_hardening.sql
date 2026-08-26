-- G2 security hardening migration (seq=73 COMMAND)
-- Scope: enable RLS on the 8 observatory runtime tables, create SELECT-only
-- publishable-read policies for runs / run_gates / run_nodes, and harden the
-- existing public.notify_projection_event() function by pinning a fixed
-- search_path WITHOUT replacing its body or changing realtime.send semantics.
--
-- Authoritative contract (seq=73 required_work GREEN step):
--   - Enable RLS on exactly: runs, run_events, run_gates, run_nodes,
--     run_artifacts, run_checkpoints, run_edges, run_sources
--   - SELECT-only policies TO anon, authenticated USING (true) for
--     runs, run_gates, run_nodes ONLY
--   - NO INSERT/UPDATE/DELETE policy and NO client policy at all for
--     run_events, run_artifacts, run_checkpoints, run_edges, run_sources
--   - ALTER FUNCTION public.notify_projection_event() SET search_path to a
--     fixed safe path; body is preserved, realtime.send semantics unchanged.

-- 1) Enable row level security on the 8 runtime tables.
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_gates ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_sources ENABLE ROW LEVEL SECURITY;

-- 2) SELECT-only publishable read policies for the three reader-facing tables.
CREATE POLICY runs_select_publishable
  ON runs
  FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY run_gates_select_publishable
  ON run_gates
  FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY run_nodes_select_publishable
  ON run_nodes
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- 3) Harden the existing broadcast function: pin a fixed, safe search_path.
--    This ALTERs only configuration; it does NOT replace the function body and
--    does NOT alter the realtime.send(...) broadcast semantics.
ALTER FUNCTION public.notify_projection_event() SET search_path = pg_catalog, public;
