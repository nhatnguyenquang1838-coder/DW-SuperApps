-- POST-DEPLOY phase for DWO v2 native observation contract.
-- Run ONLY after dwo-observation-ingest-v2 is deployed with the 3-arg RPC call.
-- Phase-A migration 20261103161000 intentionally leaves the safe 2-arg wrapper
-- in place so migration-first and Edge-first rollout orders are both survivable.

SELECT pg_advisory_xact_lock(hashtextextended('dwo:gwc-observation-v2:migration', 0));

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_source_id text, p_event jsonb, p_event_payload_digest text'
  ) THEN
    RAISE EXCEPTION 'POSTDEPLOY_SOURCE_BOUND_RPC_MISSING';
  END IF;
END
$$;

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
    RAISE EXCEPTION 'POSTDEPLOY_LEGACY_RPC_STILL_PRESENT';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_source_id text, p_event jsonb, p_event_payload_digest text'
      AND p.prosecdef=false
  ) THEN
    RAISE EXCEPTION 'POSTDEPLOY_SOURCE_BOUND_RPC_INVALID';
  END IF;
END
$$;
