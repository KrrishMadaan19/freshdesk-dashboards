"""Triggered by the upload page's repository_dispatch event.

Downloads the most recent raw export from Workers KV, cleans it, and makes
it THE dataset -- the latest upload fully replaces whatever was there
before.

Why replace instead of upsert-by-Ticket-ID (which is what this did until
2026-09-24): TAT columns like `Spare Group Assignment` and `Service
Partner Assigned Date Stamp` get filled in days AFTER a ticket is
created. Under the old merge, a partial/daily export only updated the
ticket IDs it contained, so a ticket created Sep 3 whose spare was
assigned Sep 20 kept its stale (blank) assignment date forever, and its
TAT silently stayed wrong. Merging made the dataset a mix of snapshots
taken at different times, which is unfixable from inside the pipeline.

Replace makes the dashboards a pure function of one file: whatever you
last uploaded is exactly what they show. The tradeoff is that each upload
must be a FULL export covering every ticket you want reported on -- a
day-only export means the dashboards show that day only. That matches how
the source Excel workbook is maintained ("replace the existing data with
the newly prepared data").
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

# Every column here is looked up BY NAME, never by position, so adding,
# removing or reordering other columns in the Freshdesk export can't
# shift anything underneath us. These two are the only ones the pipeline
# itself can't work without -- everything else is per-dashboard and each
# dashboard script reports its own missing columns.
REQUIRED_COLUMNS = [col.TICKET_ID, col.CREATED_TIME]


def validate_columns(df):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Uploaded file is missing required column(s): {missing}. "
            f"Columns found: {sorted(df.columns.tolist())}"
        )


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
    validate_columns(new_df)

    print(f"Applying cleanup rules to {len(new_df)} rows")
    new_df = preprocess_raw.process(new_df)

    # Only de-duplicate WITHIN this file -- a single export can legitimately
    # repeat a ticket id; the last occurrence is the freshest.
    before = len(new_df)
    new_df = new_df.drop_duplicates(subset=TICKET_ID_COLUMN, keep="last")
    if len(new_df) != before:
        print(f"Dropped {before - len(new_df)} duplicate {TICKET_ID_COLUMN} row(s) within the upload")

    kv_store.write_chunked(MASTER_PREFIX, new_df.to_csv(index=False))
    print(f"Wrote {len(new_df)} rows to KV under '{MASTER_PREFIX}' (replaced previous dataset)")


if __name__ == "__main__":
    main()
