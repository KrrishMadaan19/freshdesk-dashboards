"""Dashboard 5: Overall Cancelled Tickets Report.

Reproduces the formulas in docs/excel_process_notes/05-overall-cancelled.md
against the master dataset, and writes the monthly / weekly / daily count
grids to KV as processed:overall-cancelled.

Everything here keys off `Resolved time` -- `Created time` is never used by
this dashboard (unlike Dashboard 1).
"""

import io
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import date_utils  # noqa: E402
import kv_store  # noqa: E402

MASTER_PREFIX = "master:tickets"
PROCESSED_PREFIX = "processed:overall-cancelled"

RESOLVED_COL = col.RESOLVED_TIME
RESOLUTION_TYPE_COL = col.RESOLUTION_TYPE

# Label used where Resolution Type is blank -- mirrors the workbook's
# `resolution type2` helper column, which maps "" to this string.
NOT_SELECTED = "Resolution type not selected"

# The workbook's RAW sheet is pre-filtered to these cancellation types plus
# blanks. Deliberately an ALLOW-list, not a deny-list: a new cancellation
# type added in Freshdesk would otherwise sail through the filter, match no
# row, and vanish silently from both the grid and the totals. As an
# allow-list it simply doesn't appear, which is visible.
#
# The odd spacing is real and matches the export byte-for-byte -- "Spam/ Junk"
# has a space after the slash, "Request Cancelled -Service denial..." has none
# after the dash. Do not tidy these.
CANCELLED_TYPES = [
    "Auto Closed",
    "Forwarded to relevant team",
    "Request Cancelled - Customer did not approve charges",
    "Request Cancelled - Customer did not provide a visit appointment",
    "Request Cancelled - Customer did not respond",
    "Request Cancelled - Customer did not share the required details",
    "Request Cancelled - Other brand product",
    "Request Cancelled - Product working fine",
    "Request Cancelled - Self-Resolved",
    "Request Cancelled -Service denial/local repair suggested",
    "Spam/ Junk",
    "FD automation issue",
    "Test",
]

# Display order, matching the sheet's rows 3-17. The sheet's "Blanks" row is
# omitted: it is provably dead (the helper column never emits that string) and
# reads as "there are no blank resolution types" when in fact there are tens of
# thousands -- they sit in NOT_SELECTED.
ROWS = [
    "Auto Closed",
    "Forwarded to relevant team",
    "Request Cancelled - Customer did not approve charges",
    "Request Cancelled - Customer did not provide a visit appointment",
    "Request Cancelled - Customer did not respond",
    "Request Cancelled - Customer did not share the required details",
    "Request Cancelled - Other brand product",
    "Request Cancelled - Product working fine",
    "Request Cancelled - Self-Resolved",
    "Request Cancelled -Service denial/local repair suggested",
    NOT_SELECTED,
    "Spam/ Junk",
    "FD automation issue",
    "Test",
]

# BUG 2 in the source workbook: every Grand Total row is =SUM(B3:B15), which
# stops short of rows 16-17. Reproduced at the user's request (2026-09-24) so
# the website and the workbook agree cell-for-cell. See the doc for the full
# story -- unlike the workbook's other total bug, this one is deterministic
# ("exclude these two named categories") and so carries forward cleanly.
EXCLUDED_FROM_TOTAL = ["FD automation issue", "Test"]

WEEKS = ["WK 1", "WK 2", "WK 3", "WK 4", "WK 5"]
DAYS = [f"{d}{'th' if d in (11, 12, 13) else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')}"
        for d in range(1, 32)]


def week_bucket(day_of_month):
    """Same day-of-month bucketing as Dashboard 1 -- the source workbooks use
    the identical WEEKNUM(DAY(...)) trick, verified empirically here across
    all 87,972 rows of the cancelled workbook with zero exceptions."""
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
    from datetime import datetime
    return datetime.strptime(month_label, "%b'%y")


def counts_for(df, column, labels):
    """Count rows per category for each label, as one grid."""
    grid = {}
    for row_label in ROWS:
        row_df = df[df["_category"] == row_label]
        per_label = row_df[column].value_counts()
        grid[row_label] = {label: int(per_label.get(label, 0)) for label in labels}

    # Grand Total row, reproducing the workbook's short SUM range.
    grid["Grand Total"] = {
        label: sum(grid[r][label] for r in ROWS if r not in EXCLUDED_FROM_TOTAL)
        for label in labels
    }
    return grid


def main():
    master_text = kv_store.read_chunked(MASTER_PREFIX)
    if master_text is None:
        raise RuntimeError("No master dataset found in KV -- run process_upload.py first")

    df = pd.read_csv(io.StringIO(master_text), low_memory=False, keep_default_na=False)

    for required in (RESOLVED_COL, RESOLUTION_TYPE_COL):
        if required not in df.columns:
            raise RuntimeError(
                f"Master dataset is missing required column '{required}'. "
                f"Columns found: {sorted(df.columns.tolist())}"
            )

    # Resolved time is cleaned by preprocess_raw.py into ISO date-only text
    # before it reaches the master dataset, so no dayfirst juggling here.
    resolved = date_utils.parse_native_timestamp(df[RESOLVED_COL])

    # Blank Resolution Type becomes its own category, mirroring the workbook's
    # `resolution type2` helper. Matching is case-insensitive because COUNTIFS
    # is, and the sheet's own labels disagree in case with the helper's output.
    raw_type = df[RESOLUTION_TYPE_COL].fillna("").astype(str).str.strip()
    allowed = {t.casefold(): t for t in CANCELLED_TYPES}
    category = raw_type.map(lambda v: NOT_SELECTED if v == "" else allowed.get(v.casefold()))

    df = df.assign(_resolved=resolved, _category=category)

    # Drop anything outside the allow-list. Rows with no usable Resolved time
    # are counted and surfaced on the page rather than vanishing silently --
    # every view buckets by resolved month/week/day, so a ticket without that
    # date genuinely has nowhere to sit in the grid.
    in_scope = df[df["_category"].notna()]
    excluded_no_date = int(in_scope["_resolved"].isna().sum())
    df = in_scope[in_scope["_resolved"].notna()]
    print(f"Cancelled-type rows: {len(in_scope)}  "
          f"(with a Resolved time: {len(df)}, without: {excluded_no_date})")

    # No day-1 cutoff: the dashboard shows every ticket in the upload,
    # including ones resolved today (user's call, 2026-09-24 -- "use all the
    # data"). The most recent day is therefore partial until that day ends.
    latest = df["_resolved"].max()

    df = df.assign(
        _month=df["_resolved"].dt.strftime("%b'%y"),
        _week=df["_resolved"].dt.day.map(week_bucket),
        _day=df["_resolved"].dt.day.map(lambda d: DAYS[d - 1]),
    )

    months = sorted(df["_month"].unique(), key=month_sort_key)
    print(f"Months found: {months}")

    overall = counts_for(df, "_month", months)
    weekly = {m: counts_for(df[df["_month"] == m], "_week", WEEKS) for m in months}
    daily = {m: counts_for(df[df["_month"] == m], "_day", DAYS) for m in months}

    output = {
        "rows": ROWS + ["Grand Total"],
        "months": months,
        "weeks": WEEKS,
        "days": DAYS,
        "overall": overall,
        "weekly": weekly,
        "daily": daily,
        "excludedFromTotal": EXCLUDED_FROM_TOTAL,
        "latestResolved": latest.date().isoformat() if pd.notna(latest) else None,
        "excludedNoDate": excluded_no_date,
    }

    kv_store.write_chunked(PROCESSED_PREFIX, json.dumps(output))
    print(f"Wrote {len(months)} months to KV under '{PROCESSED_PREFIX}'")


if __name__ == "__main__":
    main()
