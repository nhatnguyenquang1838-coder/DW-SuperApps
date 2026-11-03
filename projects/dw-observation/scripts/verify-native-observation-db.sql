-- DWO v2 native observation DB verification.
-- Expected result: one row with status=PASS plus diagnostic result sets.

DO $$
DECLARE
  v_count int;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='observation_source_bindings'
      AND column_name='sha_policy'
  ) THEN RAISE EXCEPTION 'VERIFY_SHA_POLICY_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='observation_events_raw'
      AND column_name='accepted_source_id'
  ) THEN RAISE EXCEPTION 'VERIFY_ACCEPTED_SOURCE_ID_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_source_id text, p_event jsonb, p_event_payload_digest text'
      AND p.prosecdef = false
  ) THEN RAISE EXCEPTION 'VERIFY_FINAL_RPC_INVALID'; END IF;

  IF EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_event jsonb, p_event_payload_digest text'
  ) THEN RAISE EXCEPTION 'VERIFY_LEGACY_RPC_PRESENT'; END IF;

  SELECT count(*) INTO v_count
  FROM public.observation_events_raw r
  WHERE NOT EXISTS (
    SELECT 1 FROM public.projection_events p WHERE p.raw_event_id=r.id
  );
  IF v_count <> 0 THEN RAISE EXCEPTION 'VERIFY_RAW_PROJECTION_GAP:%',v_count; END IF;

  SELECT count(*) INTO v_count
  FROM public.observation_events_raw r
  WHERE r.gate IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM public.run_gates g
      WHERE g.run_id=r.run_id AND g.gate_id=r.run_id||'::'||r.gate
    );
  IF v_count <> 0 THEN RAISE EXCEPTION 'VERIFY_GATE_GAP:%',v_count; END IF;

  SELECT count(*) INTO v_count
  FROM public.observation_events_raw r
  WHERE r.node_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM public.run_nodes n
      WHERE n.run_id=r.run_id AND n.node_id=r.run_id||'::node::'||r.node_id
    );
  IF v_count <> 0 THEN RAISE EXCEPTION 'VERIFY_NODE_GAP:%',v_count; END IF;

  SELECT count(*) INTO v_count
  FROM (
    SELECT r.source_system,r.run_id,max(r.source_sequence) max_seq,c.last_sequence,c.gap_state
    FROM public.observation_events_raw r
    JOIN public.observation_ingest_cursors c
      ON c.source_system=r.source_system AND c.run_id=r.run_id
    GROUP BY r.source_system,r.run_id,c.last_sequence,c.gap_state
    HAVING max(r.source_sequence) <> c.last_sequence
  ) x;
  IF v_count <> 0 THEN RAISE EXCEPTION 'VERIFY_CURSOR_HIGH_WATER_GAP:%',v_count; END IF;

  IF EXISTS (
    SELECT 1 FROM public.observation_source_bindings
    WHERE source_id='gwc-main'
      AND (sha_policy <> 'ANY_SIGNED' OR source_sha IS NOT NULL OR NOT enabled)
  ) THEN RAISE EXCEPTION 'VERIFY_GWC_MAIN_BINDING_INVALID'; END IF;

  IF has_function_privilege('anon','public.ingest_observation_event_v2(text,jsonb,text)','EXECUTE')
     OR has_function_privilege('authenticated','public.ingest_observation_event_v2(text,jsonb,text)','EXECUTE') THEN
    RAISE EXCEPTION 'VERIFY_BROWSER_RPC_EXECUTE_PRESENT';
  END IF;

  IF has_table_privilege('anon','public.observation_events_raw','SELECT')
     OR has_table_privilege('authenticated','public.observation_events_raw','SELECT')
     OR has_table_privilege('anon','public.observation_machine_keys','SELECT')
     OR has_table_privilege('authenticated','public.observation_machine_keys','SELECT') THEN
    RAISE EXCEPTION 'VERIFY_SERVER_ONLY_TABLE_EXPOSURE';
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.observation_source_bindings
    WHERE (sha_policy='EXACT' AND source_sha IS NULL)
       OR (sha_policy='ANY_SIGNED' AND source_sha IS NOT NULL)
  ) THEN
    RAISE EXCEPTION 'VERIFY_SOURCE_POLICY_INCONSISTENT';
  END IF;
END
$$;

SELECT 'PASS' AS status,
       (SELECT count(*) FROM public.observation_events_raw) AS raw_events,
       (SELECT count(*) FROM public.projection_events WHERE raw_event_id IS NOT NULL) AS native_projections,
       (SELECT count(*) FROM public.run_gates WHERE boundary='GWC_UNIVERSAL_V2') AS native_gates,
       (SELECT count(*) FROM public.run_nodes WHERE boundary='OBSERVED_RUNTIME') AS native_nodes,
       (SELECT count(*) FROM public.observation_ingest_cursors WHERE gap_state='GAP') AS gap_cursors;

SELECT source_id,source_system,source_repository,source_schema,sha_policy,source_sha,enabled
FROM public.observation_source_bindings
ORDER BY source_id;

SELECT r.id,r.run_id,r.source_event_id,r.source_sequence,r.accepted_source_id,
       r.gate,r.runtime_state,r.node_id,r.projection_status,
       p.projection_ordinal
FROM public.observation_events_raw r
JOIN public.projection_events p ON p.raw_event_id=r.id
ORDER BY r.run_id,r.source_sequence;
