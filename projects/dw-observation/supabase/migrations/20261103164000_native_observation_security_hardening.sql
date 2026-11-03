-- Final security/constraint convergence for fresh and upgraded environments.

ALTER TABLE public.observation_source_bindings
  DROP CONSTRAINT IF EXISTS observation_source_bindings_sha_policy_check;

ALTER TABLE public.observation_source_bindings
  ADD CONSTRAINT observation_source_bindings_sha_policy_check
  CHECK (
    (sha_policy = 'EXACT'
      AND source_sha IS NOT NULL
      AND source_sha ~ '^[0-9a-f]{40}$')
    OR
    (sha_policy = 'ANY_SIGNED'
      AND source_sha IS NULL)
  );

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid='public.observation_events_raw'::regclass
      AND conname='observation_events_raw_accepted_source_id_check'
  ) THEN
    ALTER TABLE public.observation_events_raw
      ADD CONSTRAINT observation_events_raw_accepted_source_id_check
      CHECK (accepted_source_id IS NULL OR btrim(accepted_source_id) <> '');
  END IF;
END
$$;

ALTER TABLE public.observation_source_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observation_machine_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observation_events_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observation_ingest_cursors ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.observation_source_bindings FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.observation_machine_keys FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.observation_events_raw FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.observation_ingest_cursors FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.observation_source_bindings TO service_role;
GRANT SELECT ON public.observation_machine_keys TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.observation_events_raw TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.observation_ingest_cursors TO service_role;

DO $$
BEGIN
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
