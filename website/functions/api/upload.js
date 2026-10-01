// KV values are capped at 25MB and a single Cloudflare request body at ~100MB,
// so a large export arrives as several POSTs, one KV value each. No
// decompression or parsing happens here -- that work belongs in
// scripts/process_upload.py, where Actions' CPU/time budget makes it a
// non-issue; a Worker's per-request limit is not a safe place to gunzip and
// parse a multi-hundred-MB export.

// Uploads may be CSV or Excel. The processing script sniffs the bytes to
// decide how to parse, but the extension still travels with the file because
// .xlsx and .xlsb are both ZIP containers and can't be told apart by magic
// number alone.
const ALLOWED_FORMATS = ["csv", "xlsx", "xls", "xlsb"];

// xlsx and xlsb are ZIP containers, so the upload page sends them as-is rather
// than gzipping them pointlessly. The processing script sniffs the gzip magic
// number rather than trusting what we record here.
const ALREADY_COMPRESSED = ["xlsx", "xlsb"];

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Chunks live under the upload's own id, and the manifest -- which names that
// id -- is only written once the final chunk lands. So an upload that dies
// halfway leaves orphans that nothing reads, instead of overwriting half of
// yesterday's chunks and leaving the old manifest pointing at a mix of two
// files. That failure would be near-undetectable in a CSV.
function chunkKey(date, uploadId, index) {
  return `raw:${date}:${uploadId}:chunk:${index}`;
}

async function deleteSupersededChunks(kv, date, currentUploadId) {
  const existing = await kv.get(`raw:${date}:manifest`);
  if (!existing) return;
  try {
    const manifest = JSON.parse(existing);
    if (!manifest.uploadId || manifest.uploadId === currentUploadId) return;
    const stale = [];
    for (let i = 0; i < manifest.chunks; i++) {
      stale.push(kv.delete(chunkKey(date, manifest.uploadId, i)));
    }
    await Promise.all(stale);
  } catch {
    // A manifest we can't parse is one we can't clean up from; the new upload
    // writes its own and the orphans are simply never read.
  }
}

export async function onRequestPost({ request, env }) {
  if (!request.body) {
    return json({ error: "No request body." }, 400);
  }

  const format = (request.headers.get("X-File-Format") || "csv").toLowerCase();
  if (!ALLOWED_FORMATS.includes(format)) {
    return json({ error: `Unsupported file format: ${format}` }, 400);
  }

  const uploadId = request.headers.get("X-Upload-Id");
  const index = Number(request.headers.get("X-Chunk-Index"));
  const total = Number(request.headers.get("X-Chunk-Total"));

  if (!uploadId || !/^[A-Za-z0-9_-]{1,64}$/.test(uploadId)) {
    return json({ error: "Missing or malformed X-Upload-Id." }, 400);
  }
  if (!Number.isInteger(index) || !Number.isInteger(total) || total < 1 ||
      index < 0 || index >= total) {
    return json({ error: "Missing or malformed chunk index/total." }, 400);
  }

  const date = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const prefix = `raw:${date}`;

  if (index === 0) {
    await deleteSupersededChunks(env.TICKETS_KV, date, uploadId);
  }

  await env.TICKETS_KV.put(
    chunkKey(date, uploadId, index),
    new Uint8Array(await request.arrayBuffer())
  );

  // Every chunk but the last is just stored; nothing downstream can see this
  // upload until the manifest names it.
  if (index < total - 1) {
    return json({ ok: true, received: index + 1, of: total });
  }

  await env.TICKETS_KV.put(
    `${prefix}:manifest`,
    JSON.stringify({
      chunks: total,
      encoding: ALREADY_COMPRESSED.includes(format) ? "none" : "gzip",
      format,
      uploadId,
    })
  );

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

  return json({ ok: true, key: prefix, chunks: total });
}
