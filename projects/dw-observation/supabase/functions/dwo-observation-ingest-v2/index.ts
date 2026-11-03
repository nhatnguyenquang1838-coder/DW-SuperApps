import { createClient } from "npm:@supabase/supabase-js@2.45.0";

const DESTINATION_ID = "dwo-observation-v2";
const EVENT_SOURCE = "gwc.node-architect.dwo-observation.v1.0";
const MAX_SKEW_SECONDS = 300;

const enc = new TextEncoder();

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes)).map((v) => v.toString(16).padStart(2, "0")).join("");
}

function bytesFromHex(value: string): Uint8Array {
  if (!/^[0-9a-f]+$/i.test(value) || value.length % 2 !== 0) throw new Error("INVALID_HEX");
  const out = new Uint8Array(value.length / 2);
  for (let i = 0; i < value.length; i += 2) out[i / 2] = Number.parseInt(value.slice(i, i + 2), 16);
  return out;
}

async function sha256(value: string): Promise<string> {
  return "sha256:" + hex(await crypto.subtle.digest("SHA-256", enc.encode(value)));
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return "{" + Object.keys(obj).sort().map((key) => JSON.stringify(key) + ":" + canonicalJson(obj[key])).join(",") + "}";
  }
  throw new Error("CANONICAL_JSON_UNSUPPORTED_VALUE");
}

async function importHmac(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

async function verifyHmac(secret: string, message: string, proof: string): Promise<boolean> {
  if (!proof.startsWith("hmac-sha256:")) return false;
  const key = await importHmac(secret);
  return crypto.subtle.verify("HMAC", key, bytesFromHex(proof.slice("hmac-sha256:".length)), enc.encode(message));
}

async function signHmac(secret: string, message: string): Promise<string> {
  const key = await importHmac(secret);
  return "hmac-sha256:" + hex(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
}

function adminKey(): string {
  const modern = Deno.env.get("SUPABASE_SECRET_KEYS");
  if (modern) {
    const keys = JSON.parse(modern);
    if (keys.default) return keys.default;
  }
  const legacy = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!legacy) throw new Error("ADMIN_KEY_UNAVAILABLE");
  return legacy;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json(405, { error: "METHOD_NOT_ALLOWED" });

  try {
    const sourceId = req.headers.get("x-dwo-source-id") ?? "";
    const keyId = req.headers.get("x-dwo-key-id") ?? "";
    const timestampRaw = req.headers.get("x-dwo-timestamp") ?? "";
    const requestDigest = req.headers.get("x-dwo-request-digest") ?? "";
    const signature = req.headers.get("x-dwo-signature") ?? "";
    const token = req.headers.get("x-dwo-machine-token") ?? "";
    if (!sourceId || !keyId || !timestampRaw || !requestDigest || !signature || !token) {
      return json(401, { error: "AUTHENTICATION_REQUIRED" });
    }

    const timestamp = Number(timestampRaw);
    const now = Math.floor(Date.now() / 1000);
    if (!Number.isFinite(timestamp) || Math.abs(now - timestamp) > MAX_SKEW_SECONDS) {
      return json(401, { error: "REQUEST_EXPIRED" });
    }

    const raw = await req.text();
    if (raw.length > 262144) return json(413, { error: "REQUEST_TOO_LARGE" });
    let body: Record<string, any>;
    try {
      body = JSON.parse(raw);
    } catch {
      return json(400, { error: "INVALID_JSON" });
    }
    const actualDigest = await sha256(canonicalJson(body));
    if (actualDigest !== requestDigest) return json(400, { error: "REQUEST_DIGEST_INVALID" });

    const url = Deno.env.get("SUPABASE_URL");
    if (!url) throw new Error("SUPABASE_URL_UNAVAILABLE");
    const supabase = createClient(url, adminKey(), { auth: { persistSession: false } });

    const tokenHash = await sha256(token);
    const { data: keyRow, error: keyError } = await supabase
      .from("observation_machine_keys")
      .select("key_id,source_id,secret_hash,enabled,expires_at")
      .eq("key_id", keyId)
      .eq("source_id", sourceId)
      .maybeSingle();
    if (keyError) throw keyError;
    if (!keyRow || !keyRow.enabled || keyRow.secret_hash !== tokenHash) {
      return json(401, { error: "MACHINE_KEY_INVALID" });
    }
    if (keyRow.expires_at && Date.parse(keyRow.expires_at) <= Date.now()) {
      return json(401, { error: "MACHINE_KEY_EXPIRED" });
    }

    if (!(await verifyHmac(token, timestampRaw + "\n" + requestDigest, signature))) {
      return json(401, { error: "SIGNATURE_INVALID" });
    }

    const event = body?.event;
    const delivery = body?.delivery;
    if (!event || event.schema_id !== "gwc.observation-event/v2" || event.schema_version !== 2) {
      return json(400, { error: "SCHEMA_UNSUPPORTED" });
    }
    if (event?.source?.system !== "gwc" || !/^[0-9a-f]{40}$/.test(event?.source?.sha ?? "")) {
      return json(400, { error: "SOURCE_BINDING_INVALID" });
    }
    if (delivery?.destination_id !== DESTINATION_ID || !Number.isInteger(delivery?.generation)) {
      return json(400, { error: "DELIVERY_BINDING_INVALID" });
    }
    const eventPayloadDigest = await sha256(canonicalJson(event));
    if (eventPayloadDigest !== delivery?.payload_digest) {
      return json(400, { error: "EVENT_PAYLOAD_DIGEST_INVALID" });
    }

    const { data: receipt, error: ingestError } = await supabase.rpc("ingest_observation_event_v2", {
      p_event: event,
      p_event_payload_digest: delivery.payload_digest,
    });
    if (ingestError) {
      const msg = ingestError.message ?? "INGEST_FAILED";
      const typed = ["SOURCE_BINDING_MISMATCH","SOURCE_SEQUENCE_GAP","EVENT_ID_DIGEST_CONFLICT","SCHEMA_UNSUPPORTED","OBSERVATION_EVENT_INVALID"]
        .find((code) => msg.includes(code)) ?? "INGEST_FAILED";
      return json(typed === "INGEST_FAILED" ? 500 : 409, { error: typed });
    }

    const created = Math.floor(Date.now() / 1000);
    const ack: Record<string, unknown> = {
      destination_id: DESTINATION_ID,
      event_source: EVENT_SOURCE,
      event_id: event.event_id,
      delivery_generation: delivery.generation,
      request_digest: requestDigest,
      payload_digest: delivery.payload_digest,
      created,
      raw_event_id: receipt.raw_event_id,
      projection_ordinal: receipt.projection_ordinal,
      status: receipt.status,
    };
    const message = [
      String(ack.created), String(ack.request_digest), String(ack.payload_digest),
      String(ack.event_id), String(ack.delivery_generation), String(ack.raw_event_id),
      String(ack.projection_ordinal), String(ack.status),
    ].join("\n");
    ack.signature_proof = await signHmac(token, message);
    return json(200, ack);
  } catch (error) {
    console.error("dwo-observation-ingest-v2", error instanceof Error ? error.message : "UNKNOWN");
    return json(500, { error: "INTERNAL_ERROR" });
  }
});
