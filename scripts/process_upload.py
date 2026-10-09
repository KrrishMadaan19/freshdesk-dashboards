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
import time

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


def dispatched_upload():
    """The upload this run was triggered for, from the repository_dispatch
    payload -- or None when there isn't one (a manual workflow_dispatch).

    Trusting the payload over re-deriving "the latest upload" is the whole
    point. On 2026-10-09 a run started 20 seconds BEFORE the upload that
    triggered it finished writing its manifest, read the previous upload's
    manifest instead, rebuilt every dashboard from the older file and reported
    success. The site served stale data with nothing to indicate it. KV reads
    being eventually consistent can produce the same result even when the
    write lands first, so no amount of re-reading fixes this -- the identity
    has to come from the trigger.
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        return None
    with open(event_path, encoding="utf-8") as handle:
        payload = (json.load(handle) or {}).get("client_payload") or {}
    prefix = payload.get("prefix")
    if not prefix:
        return None
    # Older uploads (before this field existed) dispatched a prefix with no
    # uploadId; those fall back to reading the manifest, as they always did.
    return {
        "prefix": prefix,
        "uploadId": payload.get("uploadId"),
        "chunks": payload.get("chunks"),
        "format": payload.get("format"),
    }


# Excel files are ZIP (xlsx/xlsb) or OLE2 (xls) containers. Sniffing the bytes
# is more trustworthy than the extension the browser reported, but it can't
# separate xlsx from xlsb -- both are ZIPs -- so the declared format breaks
# that tie.
ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
GZIP_MAGIC = b"\x1f\x8b"

EXCEL_ENGINES = {"xlsx": "openpyxl", "xlsb": "pyxlsb", "xls": "xlrd"}

# A chunk written seconds ago can still read as absent -- KV is eventually
# consistent. Wait rather than making someone re-upload a file that is
# already there, but bound the wait so a genuinely incomplete upload fails.
CHUNK_WAIT_ATTEMPTS = 6
CHUNK_WAIT_SECONDS = 15


def read_raw_upload(prefix, dispatched=None):
    """Returns (bytes, declared_format). The upload Function writes the export
    as gzip-compressed, byte-aligned chunks (decompressing megabytes on a
    Worker's per-request CPU budget isn't safe), so unpack that here.

    `dispatched` is the upload identity carried by the triggering event. When
    present it WINS over the manifest, because the manifest in KV may already
    describe a newer upload, or may still describe an older one that hasn't
    been superseded yet -- see dispatched_upload().
    """
    upload_id = chunk_count = declared_format = None
    if dispatched and dispatched.get("uploadId") and dispatched.get("chunks"):
        upload_id = dispatched["uploadId"]
        chunk_count = int(dispatched["chunks"])
        declared_format = dispatched.get("format")
        print(f"Using the upload named by the trigger: uploadId={upload_id}, "
              f"{chunk_count} chunk(s)")
    else:
        manifest = json.loads(kv_store.get(f"{prefix}:manifest"))
        # Chunks live under the upload's own id so a half-finished upload can't
        # be mistaken for a complete one (see the comment in upload.js).
        # Uploads from before chunked upload existed have no uploadId and sit
        # directly under the date prefix.
        upload_id = manifest.get("uploadId")
        chunk_count = manifest["chunks"]
        declared_format = manifest.get("format")
        print(f"No upload named by the trigger; falling back to the manifest: "
              f"uploadId={upload_id}, {chunk_count} chunk(s)")

    chunk_prefix = f"{prefix}:{upload_id}" if upload_id else prefix

    # KV is eventually consistent, so a chunk written moments ago can still
    # read as absent. Wait for it rather than telling the user to re-upload a
    # 120MB file that is already there -- but give up eventually, because a
    # genuinely incomplete upload must fail loudly rather than be processed
    # with a hole in it.
    for attempt in range(1, CHUNK_WAIT_ATTEMPTS + 1):
        parts = [kv_store.get_bytes(f"{chunk_prefix}:chunk:{i}") for i in range(chunk_count)]
        missing = [i for i, p in enumerate(parts) if p is None]
        if not missing:
            break
        if attempt == CHUNK_WAIT_ATTEMPTS:
            raise RuntimeError(
                f"Upload {prefix} ({upload_id}) is incomplete -- chunk(s) {missing} "
                f"still missing after {CHUNK_WAIT_ATTEMPTS} attempts. Re-upload the file."
            )
        print(f"chunk(s) {missing} not readable yet (KV is eventually consistent); "
              f"retry {attempt}/{CHUNK_WAIT_ATTEMPTS - 1} in {CHUNK_WAIT_SECONDS}s")
        time.sleep(CHUNK_WAIT_SECONDS)
    raw_bytes = b"".join(parts)
    # Sniff the gzip magic number rather than trusting the manifest: xlsx/xlsb
    # are uploaded uncompressed (they're already ZIPs), and older uploads
    # predate the encoding field being meaningful.
    if raw_bytes.startswith(GZIP_MAGIC):
        raw_bytes = gzip.decompress(raw_bytes)
    # Uploads predating multi-format support carry no "format" key.
    return raw_bytes, (declared_format or "csv").lower()


def parse_upload(raw_bytes, declared_format):
    """CSV or Excel -> DataFrame.

    keep_default_na=False on the CSV path: pandas otherwise silently reads
    literal "NA" text (a real, meaningful placeholder in some Freshdesk
    columns, e.g. "Purchased On") as a missing value, destroying the
    distinction between "field says NA" and "field is genuinely blank" before
    any of our own code sees it. The Excel readers don't take that argument,
    so blanks are normalised back to "" afterwards to keep both paths
    producing the same thing.
    """
    looks_like_excel = raw_bytes.startswith(ZIP_MAGIC) or raw_bytes.startswith(OLE2_MAGIC)

    if not looks_like_excel:
        if declared_format != "csv":
            print(f"WARNING: upload declared '{declared_format}' but the bytes aren't "
                  f"an Excel container -- reading as CSV")
        return pd.read_csv(
            io.StringIO(raw_bytes.decode("utf-8-sig")), low_memory=False, keep_default_na=False
        )

    if raw_bytes.startswith(OLE2_MAGIC):
        engine_format = "xls"
    else:
        # ZIP container: xlsx unless the upload said xlsb.
        engine_format = "xlsb" if declared_format == "xlsb" else "xlsx"

    engine = EXCEL_ENGINES[engine_format]
    print(f"Reading upload as Excel ({engine_format}, engine={engine}) -- "
          f"this is much slower than CSV on a large export")
    try:
        # keep_default_na=False for the same reason as the CSV path -- without
        # it the Excel readers turn literal "NA" text into a missing value.
        # Verified: "Purchased On" came back as "" instead of "NA" until this
        # was passed.
        df = pd.read_excel(
            io.BytesIO(raw_bytes), engine=engine, dtype=object, keep_default_na=False
        )
    except ImportError as exc:
        raise RuntimeError(
            f"Reading .{engine_format} needs the '{engine}' package. "
            f"Add it to scripts/requirements.txt."
        ) from exc

    # Match the CSV path: genuinely-blank cells become "", not NaN, so
    # downstream is_blank()/notna() checks behave identically either way.
    return df.where(df.notna(), "")


def main():
    dispatched = dispatched_upload()
    raw_prefix = dispatched["prefix"] if dispatched else latest_raw_prefix()
    print(f"Reading raw upload: {raw_prefix}"
          f"{'' if dispatched else '  (latest in KV -- no trigger payload)'}")
    raw_bytes, declared_format = read_raw_upload(raw_prefix, dispatched)
    new_df = parse_upload(raw_bytes, declared_format)
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
