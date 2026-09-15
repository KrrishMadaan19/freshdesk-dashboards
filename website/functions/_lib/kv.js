// Leading underscore excludes this directory from Pages Functions routing.
export async function readChunked(kv, prefix) {
  const manifestRaw = await kv.get(`${prefix}:manifest`);
  if (manifestRaw === null) return null;
  const { chunks } = JSON.parse(manifestRaw);
  const parts = await Promise.all(
    Array.from({ length: chunks }, (_, i) => kv.get(`${prefix}:chunk:${i}`))
  );
  return parts.join("\n");
}
