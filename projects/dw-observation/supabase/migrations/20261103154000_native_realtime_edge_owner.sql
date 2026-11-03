-- Native GWC v2 rows are broadcast from the Edge ingestion boundary after commit.
-- Legacy projection writers keep database-broadcast compatibility where available.
CREATE OR REPLACE FUNCTION public.notify_projection_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, realtime
AS $$
BEGIN
  -- Native GWC v2 ingestion owns realtime delivery in the Edge receiver,
  -- after the durable RPC transaction has committed.
  IF NEW.raw_event_id IS NOT NULL THEN
    RETURN NEW;
  END IF;

  -- Historical/legacy projection writers keep database-broadcast compatibility
  -- only where the managed Supabase realtime.send function is installed.
  IF to_regprocedure('realtime.send(jsonb,text,text,boolean)') IS NULL THEN
    RETURN NEW;
  END IF;

  PERFORM realtime.send(
    jsonb_build_object(
      'run_id', NEW.run_id,
      'source_system', NEW.source_system,
      'source_event_id', NEW.source_event_id,
      'sequence', NEW.sequence,
      'projection_ordinal', NEW.projection_ordinal,
      'event_type', NEW.event_type,
      'occurred_at', NEW.occurred_at,
      'gate', NEW.gate,
      'node_id', NEW.node_id,
      'actor', NEW.actor,
      'outcome', NEW.outcome,
      'before', NEW.before,
      'after', NEW.after,
      'evidence_refs', NEW.evidence_refs,
      'authority_ref', NEW.authority_ref,
      'source_digest', NEW.source_digest,
      'read_only_projection', NEW.read_only_projection,
      'raw_event_id', NEW.raw_event_id,
      'runtime_epoch', NEW.runtime_epoch,
      'lifecycle_profile', NEW.lifecycle_profile,
      'runtime_state', NEW.runtime_state,
      'typed_next', NEW.typed_next,
      'source_sha', NEW.source_sha
    ),
    'projection_event',
    'observatory:' || NEW.run_id,
    false
  );
  RETURN NEW;
END;
$$;

ALTER FUNCTION public.notify_projection_event()
  SET search_path = pg_catalog, public, realtime;
