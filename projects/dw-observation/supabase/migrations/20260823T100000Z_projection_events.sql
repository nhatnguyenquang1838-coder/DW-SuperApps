-- DW-OBS-G6-READINESS-R1 · projection_events canonical ledger
-- Exactly ONE new migration for the approved single projection_events contract.
-- No historical backfill; no client write path.
--
-- Broadcast equivalent:
--   realtime.send(payload, 'projection_event', 'observatory:' || run_id, false)

CREATE TABLE IF NOT EXISTS projection_events (
  event_id           TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
  run_id             TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source_system      TEXT        NOT NULL CHECK (source_system IN ('taskcontroller','gwc','mixed')),
  source_event_id    TEXT        NOT NULL,
  event_type         TEXT        NOT NULL,
  payload            JSONB       NOT NULL DEFAULT '{}'::jsonb,
  projection_ordinal BIGINT      NOT NULL,
  occurred_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_projection_event UNIQUE (run_id, source_system, source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_projection_events_run_ordinal ON projection_events (run_id, projection_ordinal);
CREATE INDEX IF NOT EXISTS idx_projection_events_occurred ON projection_events (occurred_at);

CREATE OR REPLACE FUNCTION notify_projection_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM realtime.send(
    json_build_object(
      'run_id', NEW.run_id,
      'event_id', NEW.event_id,
      'source_system', NEW.source_system,
      'source_event_id', NEW.source_event_id,
      'event_type', NEW.event_type,
      'payload', NEW.payload,
      'projection_ordinal', NEW.projection_ordinal,
      'occurred_at', NEW.occurred_at
    )::text,
    'projection_event',
    'observatory:' || NEW.run_id,
    false
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_projection_events_after_insert AFTER INSERT ON projection_events FOR EACH ROW EXECUTE FUNCTION notify_projection_event();

ALTER TABLE projection_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY projection_events_select_publishable ON projection_events FOR SELECT TO anon, authenticated USING (true);
