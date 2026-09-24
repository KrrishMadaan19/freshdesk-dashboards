"""Shared Cloudflare Workers KV client for chunked text values.

A single KV value is capped at 25MB, so any dataset that might exceed that
(raw exports, the master dataset, processed dashboard JSON) is split into
line-aligned chunks under `<prefix>:chunk:<i>` plus a `<prefix>:manifest`
key recording the chunk count.
"""

import json
import os
import time

import requests

# Cloudflare's KV REST API intermittently returns 504 on multi-MB values --
# observed repeatedly on both reads and writes of the master dataset, at
# 20MB chunks. Smaller chunks are individually far more reliable; the extra
# requests are cheap next to a failed pipeline run.
CHUNK_LIMIT_BYTES = 8 * 1024 * 1024  # well under KV's 25MB per-value cap

MAX_ATTEMPTS = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT_SECONDS = 180

ACCOUNT_ID = os.environ["CLOUDFLARE_ACCOUNT_ID"]
API_TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
NAMESPACE_ID = os.environ["CF_KV_NAMESPACE_ID"]
BASE_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
    f"/storage/kv/namespaces/{NAMESPACE_ID}"
)
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


def _request(method, url, **kwargs):
    """Every KV call goes through here so a transient gateway error can't
    fail an unattended pipeline run. Retries 429/5xx and connection errors
    with exponential backoff; anything else (including 404) is returned to
    the caller untouched."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if response.status_code not in RETRY_STATUSES:
                return response
            last_error = requests.HTTPError(
                f"{response.status_code} from KV API", response=response
            )
        if attempt < MAX_ATTEMPTS:
            delay = 2**attempt
            print(f"KV {method} {url.rsplit('/', 1)[-1]} failed ({last_error}); "
                  f"retry {attempt}/{MAX_ATTEMPTS - 1} in {delay}s")
            time.sleep(delay)
    raise last_error


def list_keys(prefix):
    keys = []
    cursor = None
    while True:
        params = {"prefix": prefix}
        if cursor:
            params["cursor"] = cursor
        response = _request("GET", f"{BASE_URL}/keys", headers=HEADERS, params=params)
        response.raise_for_status()
        payload = response.json()
        keys.extend(k["name"] for k in payload["result"])
        cursor = payload["result_info"].get("cursor")
        if not cursor:
            break
    return keys


def get(key):
    response = _request("GET", f"{BASE_URL}/values/{key}", headers=HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def get_bytes(key):
    response = _request("GET", f"{BASE_URL}/values/{key}", headers=HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def put(key, value):
    response = _request("PUT", f"{BASE_URL}/values/{key}", headers=HEADERS, data=value.encode("utf-8"))
    response.raise_for_status()


def put_bytes(key, data):
    response = _request("PUT", f"{BASE_URL}/values/{key}", headers=HEADERS, data=data)
    response.raise_for_status()


def delete(key):
    response = _request("DELETE", f"{BASE_URL}/values/{key}", headers=HEADERS)
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
