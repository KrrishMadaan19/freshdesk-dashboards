// KV values are capped at 25MB, so the uploaded (gzip-compressed) body is
// split into byte-aligned chunks -- pure slicing, no decompression or CSV
// parsing here. That work happens in scripts/process_upload.py instead,
// where Actions' generous CPU/time budget makes it a non-issue; a Worker's
// per-request CPU limit is not a safe place to gunzip + line-split a
// multi-hundred-MB export.
const CHUNK_LIMIT_BYTES = 20 * 1024 * 1024;

async function writeChunkedBytes(kv, prefix, arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const chunks = [];
  for (let offset = 0; offset < bytes.length; offset += CHUNK_LIMIT_BYTES) {
    chunks.push(bytes.slice(offset, offset + CHUNK_LIMIT_BYTES));
  }
  if (chunks.length === 0) chunks.push(new Uint8Array(0));

  await Promise.all(chunks.map((chunk, i) => kv.put(`${prefix}:chunk:${i}`, chunk)));
  await kv.put(`${prefix}:manifest`, JSON.stringify({ chunks: chunks.length, encoding: "gzip" }));
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function onRequestPost({ request, env }) {
  if (!request.body) {
    return json({ error: "No request body." }, 400);
  }

  const date = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const prefix = `raw:${date}`;

  await writeChunkedBytes(env.TICKETS_KV, prefix, await request.arrayBuffer());

  const dispatchResponse = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "freshdesk-dashboards-upload",
      },
      body: JSON.stringify({
        event_type: "raw-upload",
        client_payload: { prefix, date },
      }),
    }
  );

  if (!dispatchResponse.ok) {
    const detail = await dispatchResponse.text();
    return json(
      { error: `Uploaded (${prefix}) but failed to trigger processing: ${detail}` },
      502
    );
  }

  return json({ ok: true, key: prefix });
}
