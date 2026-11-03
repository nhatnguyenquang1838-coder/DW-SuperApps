-- Correct database-broadcast trigger privilege without widening ingest caller grants.
CREATE OR REPLACE FUNCTION public.notify_projection_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, realtime
AS $
BEGIN
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


ALTER FUNCTION public.notify_projection_event() SET search_path = pg_catalog, public, realtime;
