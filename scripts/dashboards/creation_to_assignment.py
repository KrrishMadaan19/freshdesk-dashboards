"""Dashboard 1: Creation to Assignment Report.

Reproduces the formulas in docs/excel_process_notes/01-creation-to-assignment.md
against the merged master dataset, and writes the monthly + weekly count and
percentage grids to KV as processed/creation-to-assignment JSON.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import dashboard_lib as lib  # noqa: E402
import date_utils  # noqa: E402

MASTER_PREFIX = lib.MASTER_PREFIX
PROCESSED_PREFIX = "processed:creation-to-assignment"

# Local aliases into the shared column-name module (see columns.py).
CREATED_COL = col.CREATED_TIME
PARTNER_COL = col.PARTNER_NAME
INWARD_COL = col.INWARD_PAYMENT_GROUP_ASSIGNMENT
SPARE_COL = col.SPARE_GROUP_ASSIGNMENT
REFUND_COL = col.REFUND_GROUP_ASSIGNMENT
REPLACEMENT_COL = col.REPLACEMENT_GROUP_ASSIGNMENT
SP_COL = col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP

BUCKETS = lib.TAT_BUCKETS
WEEKS = lib.WEEKS

# (display row label, bucket column, partner filter or None)
ROWS = [
    ("CREATION TO INWARD TAT", "_inward_bucket", None),
    ("SP TO SPARE TAT — PARTNER (YES)", "_spare_bucket", "YES"),
    ("CREATION TO SPARE TAT — PARTNER (NO)", "_spare_bucket", "NO"),
    ("CREATION TO REFUND TAT", "_refund_bucket", None),
    ("CREATION TO REPLACEMENT TAT", "_replacement_bucket", None),
    ("CREATION TO SP TAT", "_sp_bucket", None),
]


# Re-exported so validation scripts and anything else importing this module
# keep working against one definition.
required_column = lib.required_column
optional_date_column = lib.optional_date_column
ageing_days = lib.ageing_days
bucket_label = lib.tat_bucket_label
week_bucket = lib.week_bucket
month_sort_key = lib.month_sort_key


def grid_for(df):
    """Count + percentage grid (row -> bucket -> value) for one period's rows."""
    counts_by_row = {}
    for row_label, bucket_col, partner_filter in ROWS:
        rows = df if partner_filter is None else df[df["_partner_yn"] == partner_filter]
        counts_by_row[row_label] = lib.count_by(rows, bucket_col, BUCKETS)

    return {
        "counts": counts_by_row,
        "percentages": {
            row: lib.percentages_of(counts, BUCKETS) for row, counts in counts_by_row.items()
        },
    }


def main():
    df = lib.load_master()

    # Created time, Refund/Replacement Group Assignment, and Service
    # Partner Assigned Date Stamp are all cleaned by preprocess_raw.py
    # before they ever reach the master dataset -- parsed there with the
    # right per-column strategy and written back as unambiguous ISO
    # date-only strings, so parse_native_timestamp (no dayfirst) is safe
    # and sufficient for them here.
    created = date_utils.parse_native_timestamp(required_column(df, CREATED_COL))
    sp_assigned = date_utils.parse_native_timestamp(optional_date_column(df, SP_COL))
    refund_assigned = date_utils.parse_native_timestamp(optional_date_column(df, REFUND_COL))
    replacement_assigned = date_utils.parse_native_timestamp(optional_date_column(df, REPLACEMENT_COL))

    # Inward Payment Group Assignment and Spare Group Assignment are NOT
    # covered by preprocess_raw.py's cleanup rules, so they still arrive
    # as raw, inconsistently-formatted DD-MM-YYYY text and need the
    # defensive element-wise parser.
    inward_assigned = date_utils.parse_ddmmyyyy(optional_date_column(df, INWARD_COL))
    spare_assigned = date_utils.parse_ddmmyyyy(optional_date_column(df, SPARE_COL))

    partner_col = df[PARTNER_COL] if PARTNER_COL in df.columns else pd.Series("", index=df.index)
    partner_yn = np.where(partner_col.fillna("").astype(str).str.strip() == "", "NO", "YES")
    spare_base = pd.Series(np.where(partner_yn == "YES", sp_assigned, created), index=df.index)

    df["_partner_yn"] = partner_yn
    df["_created_month"] = lib.month_label(created)
    df["_created_week"] = created.dt.day.map(lib.week_bucket)
    df["_inward_bucket"] = ageing_days(inward_assigned, created).map(bucket_label)
    df["_spare_bucket"] = ageing_days(spare_assigned, spare_base).map(bucket_label)
    df["_refund_bucket"] = ageing_days(refund_assigned, created).map(bucket_label)
    df["_replacement_bucket"] = ageing_days(replacement_assigned, created).map(bucket_label)
    df["_sp_bucket"] = ageing_days(sp_assigned, created).map(bucket_label)

    months = lib.sorted_months(df["_created_month"])

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

    lib.write_processed(PROCESSED_PREFIX, output)
    print(f"({len(months)} months)")


if __name__ == "__main__":
    main()
