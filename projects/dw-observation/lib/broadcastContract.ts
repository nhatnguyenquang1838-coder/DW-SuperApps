// M2 — repository-only Broadcast producer contract (DW Run Observatory).
//
// This module is the CANONICAL contract for how a producer (the dw_observation
// Python side / server, or the SQL realtime.send producer) publishes a live
// projection event over Supabase Realtime Broadcast. It is READ-ONLY contract
// code: it performs NO publish and holds no credentials. The browser
// subscriber (lib/supabaseRealtime.ts + LiveProjectionClient.receiveLive) MUST
// agree on the same topic + event name + payload shape, or the live frames
// will be silently dropped.
//
// Two distinct shapes exist and MUST NOT be conflated (R4.1 clarification):
//
//   1) ProducerPayload  — the RAW object handed as the FIRST argument to
//      Supabase's realtime.send(...). This is the canonical ProjectionEvent
//      (row columns), with source identity at the TOP level.
//
//   2) BroadcastEnvelope — the FRAME Supabase DELIVERS to subscribers. Supabase
//      wraps realtime.send(payload, event, topic, is_private) into:
//        { type: 'broadcast', event: <event>, payload: <ProducerPayload> }
//      so the subscriber receives `payload` == the ProducerPayload (the raw
//      ProjectionEvent). The subscriber must therefore read
//      frame.payload (NOT frame.payload.payload).
//
// Topic / event naming (canonical):
//   topic   = `${topicPrefix}:${runId}`   (e.g. "observatory:R-123")
//   event   = "projection_event"          (FIXED event name, DISTINCT from topic)
//   callback payload = <ProducerPayload>  (RAW ProjectionEvent, top-level identity)
// The subscriber subscribes to `topic` and binds
// `channel.on("broadcast", { event: "projection_event" }, ...)`, so producer
// and subscriber MUST use the same topic and the same fixed event name.

export interface ProducerProjectionEvent {
  run_id: string;
  source_system: string;
  source_event_id: string;
  sequence?: number;
  occurred_at?: string;
  [key: string]: unknown;
}

// The raw object passed as the first argument to realtime.send(...) — what the
// subscriber ultimately receives as the delivered frame's `payload`.
export type ProducerPayload = ProducerProjectionEvent;

// The frame Supabase DELIVERS to subscribers: the ProducerPayload wrapped by
// Supabase's Broadcast machinery. `payload` is the raw ProjectionEvent.
export interface BroadcastEnvelope {
  type: "broadcast";
  event: string; // == "projection_event" (fixed), distinct from topic
  topic?: string; // == "observatory:<run_id>" (channel topic), informational
  payload: ProducerPayload; // RAW ProjectionEvent (top-level source identity)
}

// Build the canonical Broadcast topic for a run (seq=16 protocol correction):
//   topic = "observatory:<run_id>"   (NOT the event name)
export function producerTopic(topicPrefix: string, runId: string): string {
  return `${topicPrefix}:${runId}`;
}

// Canonical Broadcast event name (FIXED, distinct from the topic).
export const PRODUCER_EVENT = "projection_event";

// Wrap a projection event in the canonical Broadcast ENVELOPE the subscriber
// expects. NOTE: this returns the delivered-frame shape (BroadcastEnvelope),
// not the realtime.send() first argument. The actual realtime.send() call uses
// the raw ProducerPayload (toBroadcastPayload). Protocol (seq=16 / R4.1):
//   { type: "broadcast", event: "projection_event", payload: <ProjectionEvent> }
// topic is "observatory:<run_id>" (set on channel.subscribe, not in envelope).
export function toBroadcastEnvelope(
  topicPrefix: string,
  event: ProducerProjectionEvent
): BroadcastEnvelope {
  const topic = producerTopic(topicPrefix, event.run_id);
  return { type: "broadcast", event: PRODUCER_EVENT, topic, payload: event };
}

// Extract the raw ProducerPayload from a delivered BroadcastEnvelope. This is
// the inverse of toBroadcastEnvelope and is what the subscriber feeds to
// receiveLive — the ProjectionEvent at frame.payload (NOT frame.payload.payload).
export function fromBroadcastEnvelope(
  env: BroadcastEnvelope
): ProducerProjectionEvent {
  return env.payload;
}

// Contract assertion: the producer envelope's event MUST equal PRODUCER_EVENT,
// topic MUST equal observatory:<run_id>, and payload MUST carry source identity.
// Used by local contract validation tests; never throws in production happy path.
export function isValidProducerEnvelope(
  env: BroadcastEnvelope,
  topicPrefix: string
): boolean {
  if (typeof env?.event !== "string" || !env?.payload) return false;
  const expectedTopic = producerTopic(topicPrefix, env.payload.run_id);
  return (
    env.event === PRODUCER_EVENT &&
    env.topic === expectedTopic &&
    !!env.payload.source_system &&
    !!env.payload.source_event_id
  );
}
