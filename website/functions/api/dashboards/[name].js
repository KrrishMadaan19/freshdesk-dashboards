import { readChunked } from "../../_lib/kv.js";

export async function onRequestGet({ env, params }) {
  const prefix = `processed:${params.name}`;
  const text = await readChunked(env.TICKETS_KV, prefix);

  if (text === null) {
    return new Response(JSON.stringify({ error: "No processed data yet for this dashboard." }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(text, {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
