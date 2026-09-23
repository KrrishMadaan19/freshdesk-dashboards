"""Triggered by the upload page's repository_dispatch event.

Downloads the most recent raw export from Workers KV and upserts it into
the master dataset (matched by Ticket ID).
"""

import gzip
import io
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import columns as col  # noqa: E402
import kv_store  # noqa: E402
import preprocess_raw  # noqa: E402

TICKET_ID_COLUMN = col.TICKET_ID
MASTER_PREFIX = "master:tickets"


def latest_raw_prefix():
    manifests = [k for k in kv_store.list_keys("raw:") if k.endswith(":manifest")]
    if not manifests:
        raise RuntimeError("No raw uploads found in KV under prefix 'raw:'")
    latest = max(manifests)  # "raw:YYYY-MM-DD:manifest" sorts chronologically
    return latest[: -len(":manifest")]


def read_raw_upload(prefix):
    """The upload Function writes the raw export as gzip-compressed,
    byte-aligned chunks (decompressing megabytes of CSV on a Worker's
    per-request CPU budget isn't safe), so unpack that here instead."""
    manifest = json.loads(kv_store.get(f"{prefix}:manifest"))
    raw_bytes = kv_store.read_chunked_bytes(prefix)
    if manifest.get("encoding") == "gzip":
        return gzip.decompress(raw_bytes).decode("utf-8")
    return raw_bytes.decode("utf-8")


def main():
    raw_prefix = latest_raw_prefix()
    print(f"Reading raw upload: {raw_prefix}")
    # keep_default_na=False: pandas otherwise silently reads literal "NA"
    # text (a real, meaningful placeholder value in some Freshdesk
    # columns, e.g. "Purchased On") as a missing value -- destroying the
    # distinction between "field says NA" and "field is genuinely blank"
    # before any of our own code ever sees it.
    new_df = pd.read_csv(io.StringIO(read_raw_upload(raw_prefix)), low_memory=False, keep_default_na=False)

    print(f"Applying cleanup rules to {len(new_df)} rows")
    new_df = preprocess_raw.process(new_df)

    master_text = kv_store.read_chunked(MASTER_PREFIX)
    master_df = (
        pd.read_csv(io.StringIO(master_text), low_memory=False, keep_default_na=False)
        if master_text
        else pd.DataFrame()
    )
    print(f"Existing master dataset: {len(master_df)} rows")

    merged_df = pd.concat([master_df, new_df], ignore_index=True)
    merged_df = merged_df.drop_duplicates(subset=TICKET_ID_COLUMN, keep="last")
    print(f"Merged dataset: {len(merged_df)} rows (added/updated {len(new_df)} from {raw_prefix})")

    kv_store.write_chunked(MASTER_PREFIX, merged_df.to_csv(index=False))
    print(f"Wrote master dataset back to KV under '{MASTER_PREFIX}'")


if __name__ == "__main__":
    main()
