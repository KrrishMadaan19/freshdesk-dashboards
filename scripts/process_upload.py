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


# Excel files are ZIP (xlsx/xlsb) or OLE2 (xls) containers. Sniffing the bytes
# is more trustworthy than the extension the browser reported, but it can't
# separate xlsx from xlsb -- both are ZIPs -- so the declared format breaks
# that tie.
ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

EXCEL_ENGINES = {"xlsx": "openpyxl", "xlsb": "pyxlsb", "xls": "xlrd"}


def read_raw_upload(prefix):
    """Returns (bytes, declared_format). The upload Function writes the export
    as gzip-compressed, byte-aligned chunks (decompressing megabytes on a
    Worker's per-request CPU budget isn't safe), so unpack that here."""
    manifest = json.loads(kv_store.get(f"{prefix}:manifest"))
    raw_bytes = kv_store.read_chunked_bytes(prefix)
    if manifest.get("encoding") == "gzip":
        raw_bytes = gzip.decompress(raw_bytes)
    # Uploads predating multi-format support carry no "format" key.
    return raw_bytes, (manifest.get("format") or "csv").lower()


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
    raw_prefix = latest_raw_prefix()
    print(f"Reading raw upload: {raw_prefix}")
    raw_bytes, declared_format = read_raw_upload(raw_prefix)
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
