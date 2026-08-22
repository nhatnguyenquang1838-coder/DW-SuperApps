// M2 — repository-only Broadcast producer contract (DW Run Observatory).
//
// This module is the CANONICAL contract for how a producer (the dw_observation
// Python side / server) publishes a live projection event over Supabase
// Realtime Broadcast. It is READ-ONLY contract code: it performs NO publish and
// holds no credentials. The browser subscriber (lib/supabaseRealtime.ts +
// LiveProjectionClient.receiveLive) MUST agree on the same topic + event name
// + envelope shape, or the live frames will be silently dropped.
//
// Envelope (real Supabase Broadcast shape):
//   { event: string, payload: ProjectionEvent }
// where `event` is the topic-shaped event name and `payload` is the canonical
// RunProjectionEvent v1 object produced by dw_observation/events.py.
//
// Topic / event naming:
//   topic   = `${topicPrefix}:${runId}`   (e.g. "observatory:R-123")
//   event   = topic                        (Broadcast event == the channel topic)
// The subscriber subscribes to `topic` and binds `channel.on("broadcast",
// { event: topic }, ...)`, so producer and subscriber MUST use the same value.

export interface ProducerProjectionEvent {
  run_id: string;
  source_system: string;
  source_event_id: string;
  sequence?: number;
  occurred_at?: string;
  [key: string]: unknown;
}

export interface BroadcastEnvelope {
  type: "broadcast";
  event: string; // == "projection_event" (fixed), distinct from topic
  topic: string; // == "observatory:<run_id>" (channel topic)
  payload: ProducerProjectionEvent;
}

// Build the canonical Broadcast topic for a run (seq=16 protocol correction):
//   topic = "observatory:<run_id>"   (NOT the event name)
export function producerTopic(topicPrefix: string, runId: string): string {
  return `${topicPrefix}:${runId}`;
}

// Canonical Broadcast event name (FIXED, distinct from the topic).
export const PRODUCER_EVENT = "projection_event";

// Wrap a projection event in the canonical Broadcast envelope the subscriber
// expects (F9 normalization target). Protocol (seq=16):
//   { type: "broadcast", event: "projection_event", payload: <ProjectionEvent> }
// topic is "observatory:<run_id>" (set on channel.subscribe, not in envelope).
export function toBroadcastEnvelope(
  topicPrefix: string,
  event: ProducerProjectionEvent
): BroadcastEnvelope {
  const topic = producerTopic(topicPrefix, event.run_id);
  return { type: "broadcast", event: PRODUCER_EVENT, topic, payload: event };
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
