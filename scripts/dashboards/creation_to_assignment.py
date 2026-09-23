"""Dashboard 1: Creation to Assignment Report.

Reproduces the formulas in docs/excel_process_notes/01-creation-to-assignment.md
against the merged master dataset, and writes the monthly + weekly count and
percentage grids to KV as processed/creation-to-assignment JSON.
"""

import io
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import date_utils  # noqa: E402
import kv_store  # noqa: E402

MASTER_PREFIX = "master:tickets"
PROCESSED_PREFIX = "processed:creation-to-assignment"

# Local aliases into the shared column-name module (see columns.py).
CREATED_COL = col.CREATED_TIME
PARTNER_COL = col.PARTNER_NAME
INWARD_COL = col.INWARD_PAYMENT_GROUP_ASSIGNMENT
SPARE_COL = col.SPARE_GROUP_ASSIGNMENT
REFUND_COL = col.REFUND_GROUP_ASSIGNMENT
REPLACEMENT_COL = col.REPLACEMENT_GROUP_ASSIGNMENT
SP_COL = col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP

BUCKETS = ["0", "1", "2", "3", "4-5", "6-7", "7+"]
WEEKS = ["WK 1", "WK 2", "WK 3", "WK 4", "WK 5"]

# (display row label, bucket column, partner filter or None)
ROWS = [
    ("CREATION TO INWARD TAT", "_inward_bucket", None),
    ("SP TO SPARE TAT — PARTNER (YES)", "_spare_bucket", "YES"),
    ("CREATION TO SPARE TAT — PARTNER (NO)", "_spare_bucket", "NO"),
    ("CREATION TO REFUND TAT", "_refund_bucket", None),
    ("CREATION TO REPLACEMENT TAT", "_replacement_bucket", None),
    ("CREATION TO SP TAT", "_sp_bucket", None),
]


def ageing_days(end_series, start_series):
    # Both args must already be parsed datetime Series -- main() picks
    # the right date_utils parser per column before calling this, since
    # some columns are pre-cleaned (ISO) and some still aren't (see the
    # column comments in main()).
    days = (end_series - start_series).dt.days
    return days.where(end_series.notna() & start_series.notna())


def bucket_label(days):
    if pd.isna(days) or days < 0:
        return None
    if days == 0:
        return "0"
    if days == 1:
        return "1"
    if days == 2:
        return "2"
    if days == 3:
        return "3"
    if days <= 5:
        return "4-5"
    if days <= 7:
        return "6-7"
    return "7+"


def week_bucket(day_of_month):
    # Naive day-of-month grouping (1-7 -> WK1, etc). An earlier version of
    # this tried to be clever and replicate Excel's WEEKNUM(DAY(...)) via
    # its actual date-epoch algorithm, which gave 1-6 -> WK1 instead --
    # that was wrong. Checked directly against the live sheet (every real
    # ticket with day-of-month 7 shows WK1, every one with day 14 shows
    # WK2), which confirms the naive scheme is what's actually in use.
    if day_of_month <= 7:
        return "WK 1"
    if day_of_month <= 14:
        return "WK 2"
    if day_of_month <= 21:
        return "WK 3"
    if day_of_month <= 28:
        return "WK 4"
    return "WK 5"


def month_sort_key(month_label):
    return datetime.strptime(month_label, "%b'%y")


def empty_bucket_counts():
    return {b: 0 for b in BUCKETS}


def to_percentages(counts):
    total = sum(counts.values())
    if total == 0:
        return {b: 0.0 for b in BUCKETS}
    return {b: round(counts[b] / total * 100, 1) for b in BUCKETS}


def grid_for(df):
    """Count + percentage grid (row -> bucket -> value) for one period's rows."""
    counts_by_row = {}
    for row_label, bucket_col, partner_filter in ROWS:
        rows = df if partner_filter is None else df[df["_partner_yn"] == partner_filter]
        counts = empty_bucket_counts()
        for bucket, n in rows[bucket_col].value_counts().items():
            if bucket in counts:
                counts[bucket] = int(n)
        counts_by_row[row_label] = counts

    return {
        "counts": counts_by_row,
        "percentages": {row: to_percentages(counts) for row, counts in counts_by_row.items()},
    }


def main():
    master_text = kv_store.read_chunked(MASTER_PREFIX)
    if master_text is None:
        raise RuntimeError("No master dataset found in KV -- run process_upload.py first")

    # keep_default_na=False: see the comment in process_upload.py -- don't
    # let pandas silently treat literal "NA" text as a missing value.
    df = pd.read_csv(io.StringIO(master_text), low_memory=False, keep_default_na=False)

    # Created time, Refund/Replacement Group Assignment, and Service
    # Partner Assigned Date Stamp are all cleaned by preprocess_raw.py
    # before they ever reach the master dataset -- parsed there with the
    # right per-column strategy and written back as unambiguous ISO
    # date-only strings, so parse_native_timestamp (no dayfirst) is safe
    # and sufficient for them here.
    created = date_utils.parse_native_timestamp(df[CREATED_COL])
    sp_assigned = date_utils.parse_native_timestamp(df[SP_COL])
    refund_assigned = date_utils.parse_native_timestamp(df[REFUND_COL])
    replacement_assigned = date_utils.parse_native_timestamp(df[REPLACEMENT_COL])

    # Inward Payment Group Assignment and Spare Group Assignment are NOT
    # covered by preprocess_raw.py's cleanup rules, so they still arrive
    # as raw, inconsistently-formatted DD-MM-YYYY text and need the
    # defensive element-wise parser.
    inward_assigned = date_utils.parse_ddmmyyyy(df[INWARD_COL])
    spare_assigned = date_utils.parse_ddmmyyyy(df[SPARE_COL])

    partner_yn = np.where(df[PARTNER_COL].fillna("").astype(str).str.strip() == "", "NO", "YES")
    spare_base = pd.Series(np.where(partner_yn == "YES", sp_assigned, created), index=df.index)

    df["_partner_yn"] = partner_yn
    df["_created_month"] = created.dt.strftime("%b'%y")
    df["_created_week"] = created.dt.day.map(week_bucket)
    df["_inward_bucket"] = ageing_days(inward_assigned, created).map(bucket_label)
    df["_spare_bucket"] = ageing_days(spare_assigned, spare_base).map(bucket_label)
    df["_refund_bucket"] = ageing_days(refund_assigned, created).map(bucket_label)
    df["_replacement_bucket"] = ageing_days(replacement_assigned, created).map(bucket_label)
    df["_sp_bucket"] = ageing_days(sp_assigned, created).map(bucket_label)

    months = sorted(df["_created_month"].dropna().unique(), key=month_sort_key)

    monthly = {}
    weekly = {}
    for month in months:
        month_df = df[df["_created_month"] == month]
        monthly[month] = grid_for(month_df)

        weekly[month] = {
            week: grid_for(month_df[month_df["_created_week"] == week]) for week in WEEKS
        }

    output = {
        "rows": [row_label for row_label, _, _ in ROWS],
        "buckets": BUCKETS,
        "weeks": WEEKS,
        "months": months,
        "monthly": monthly,
        "weekly": weekly,
    }

    kv_store.write_chunked(PROCESSED_PREFIX, json.dumps(output))
    print(f"Wrote {len(months)} months to KV under '{PROCESSED_PREFIX}'")


if __name__ == "__main__":
    main()
