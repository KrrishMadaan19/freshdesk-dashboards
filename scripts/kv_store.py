"""Shared Cloudflare Workers KV client for chunked text values.

A single KV value is capped at 25MB, so any dataset that might exceed that
(raw exports, the master dataset, processed dashboard JSON) is split into
line-aligned chunks under `<prefix>:chunk:<i>` plus a `<prefix>:manifest`
key recording the chunk count.
"""

import json
import os

import requests

CHUNK_LIMIT_BYTES = 20 * 1024 * 1024  # stay safely under KV's 25MB per-value cap

ACCOUNT_ID = os.environ["CLOUDFLARE_ACCOUNT_ID"]
API_TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
NAMESPACE_ID = os.environ["CF_KV_NAMESPACE_ID"]
BASE_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
    f"/storage/kv/namespaces/{NAMESPACE_ID}"
)
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


def list_keys(prefix):
    keys = []
    cursor = None
    while True:
        params = {"prefix": prefix}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(f"{BASE_URL}/keys", headers=HEADERS, params=params)
        response.raise_for_status()
        payload = response.json()
        keys.extend(k["name"] for k in payload["result"])
        cursor = payload["result_info"].get("cursor")
        if not cursor:
            break
    return keys


def get(key):
    response = requests.get(f"{BASE_URL}/values/{key}", headers=HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def get_bytes(key):
    response = requests.get(f"{BASE_URL}/values/{key}", headers=HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def put(key, value):
    response = requests.put(f"{BASE_URL}/values/{key}", headers=HEADERS, data=value.encode("utf-8"))
    response.raise_for_status()


def put_bytes(key, data):
    response = requests.put(f"{BASE_URL}/values/{key}", headers=HEADERS, data=data)
    response.raise_for_status()


def delete(key):
    response = requests.delete(f"{BASE_URL}/values/{key}", headers=HEADERS)
    response.raise_for_status()


def read_chunked(prefix):
    manifest = get(f"{prefix}:manifest")
    if manifest is None:
        return None
    chunk_count = json.loads(manifest)["chunks"]
    parts = [get(f"{prefix}:chunk:{i}") for i in range(chunk_count)]
    return "\n".join(parts)


def read_chunked_bytes(prefix):
    """Reassembles byte-aligned chunks (as written by the upload Function)."""
    manifest = get(f"{prefix}:manifest")
    if manifest is None:
        return None
    chunk_count = json.loads(manifest)["chunks"]
    parts = [get_bytes(f"{prefix}:chunk:{i}") for i in range(chunk_count)]
    return b"".join(parts)


def write_chunked(prefix, text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    chunks = []
    current = []
    current_size = 0
    for line in lines:
        line_size = len((line + "\n").encode("utf-8"))
        if current and current_size + line_size > CHUNK_LIMIT_BYTES:
            chunks.append("\n".join(current))
            current = []
            current_size = 0
        current.append(line)
        current_size += line_size
    if current:
        chunks.append("\n".join(current))

    for i, chunk in enumerate(chunks):
        put(f"{prefix}:chunk:{i}", chunk)

    # Drop chunks left over from a previous, larger write of this prefix.
    for key in list_keys(f"{prefix}:chunk:"):
        index = int(key.rsplit(":", 1)[1])
        if index >= len(chunks):
            delete(key)

    put(f"{prefix}:manifest", json.dumps({"chunks": len(chunks)}))
