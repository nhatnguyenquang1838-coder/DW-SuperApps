-- Remove zero-downtime compatibility RPC after Edge Function v2 is deployed.
SELECT pg_advisory_xact_lock(hashtextextended('dwo:gwc-observation-v2:migration', 0));

REVOKE ALL ON FUNCTION public.ingest_observation_event_v2(jsonb,text)
  FROM PUBLIC, anon, authenticated, service_role;
DROP FUNCTION IF EXISTS public.ingest_observation_event_v2(jsonb,text);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_event jsonb, p_event_payload_digest text'
  ) THEN
    RAISE EXCEPTION 'VERIFY_LEGACY_RPC_STILL_PRESENT';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_source_id text, p_event jsonb, p_event_payload_digest text'
  ) THEN
    RAISE EXCEPTION 'VERIFY_SOURCE_BOUND_RPC_MISSING';
  END IF;
END
$$;
