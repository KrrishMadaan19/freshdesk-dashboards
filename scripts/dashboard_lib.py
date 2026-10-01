"""Shared mechanics for dashboard transform scripts.

Everything in here was duplicated across dashboard scripts first and extracted
once a second copy appeared -- deliberately, so the shapes are proven rather
than guessed. Each dashboard still owns its own business rules (which columns,
which filters, which source-workbook quirks to reproduce); this module only
owns the parts that must behave identically everywhere.

The date helpers in particular are the ones worth centralising: three separate
real bugs in this project came from date handling drifting between code paths
(see docs/excel_process_notes/01-creation-to-assignment.md). One definition
means one place to fix.
"""

import io
import json
from datetime import datetime

import pandas as pd

import kv_store

MASTER_PREFIX = "master:tickets"

# Day-of-month bucketing, NOT calendar weeks. Both source workbooks use
# ="WK "&WEEKNUM(DAY(...)), which buckets purely by day-of-month regardless of
# which weekday the month starts on. Verified empirically against both
# workbooks -- every ticket with day 7 reads WK 1, every one with day 14 reads
# WK 2, with zero exceptions across 87,972 and 177,276 rows respectively.
WEEKS = ["WK 1", "WK 2", "WK 3", "WK 4", "WK 5"]

# TAT ageing buckets, as string labels (they're grid column headings, not
# numbers).
TAT_BUCKETS = ["0", "1", "2", "3", "4-5", "6-7", "7+"]


def day_ordinal(day):
    """1 -> '1st', 2 -> '2nd', 11 -> '11th'. Matches the DAYS helper column in
    the Overall Cancelled workbook, whose values are used as column labels."""
    if day in (11, 12, 13):
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


DAY_ORDINALS = [day_ordinal(d) for d in range(1, 32)]


def week_bucket(day_of_month):
    """An earlier version of this tried to replicate Excel's WEEKNUM against
    its date epoch and produced 1-6 -> WK1, which was wrong. Checked directly
    against the live sheets once real multi-day data existed. Theoretical
    derivation lost to empirical observation -- when in doubt, check the data.
    """
    if day_of_month <= 7:
        return "WK 1"
    if day_of_month <= 14:
        return "WK 2"
    if day_of_month <= 21:
        return "WK 3"
    if day_of_month <= 28:
        return "WK 4"
    return "WK 5"


def month_label(series):
    """Datetime series -> "Jan'26" labels, matching TEXT(x,"mmm'yy")."""
    return series.dt.strftime("%b'%y")


def month_sort_key(label):
    """Sorts "Jan'26" labels chronologically rather than alphabetically."""
    return datetime.strptime(label, "%b'%y")


def sorted_months(series):
    return sorted(series.dropna().unique(), key=month_sort_key)


def required_column(df, name):
    """Columns are addressed BY NAME, never by position -- the export's column
    order and count both change over time. A column the whole report is keyed
    on going missing is unrecoverable, so say so loudly rather than producing a
    plausible-looking but wrong grid."""
    if name not in df.columns:
        raise RuntimeError(
            f"Uploaded data is missing required column '{name}'. "
            f"Columns found: {sorted(df.columns.tolist())}"
        )
    return df[name]


def optional_date_column(df, name):
    """A date column simply absent from this export. Its dependent row ends up
    empty (every value NaT -> no bucket) instead of crashing the rest of the
    report, which is still perfectly computable."""
    if name not in df.columns:
        print(f"WARNING: column '{name}' not present -- its row will be empty")
        return pd.Series(pd.NaT, index=df.index)
    return df[name]


def ageing_days(end_series, start_series):
    """Whole days between two already-parsed datetime series. Callers pick the
    right parser per column before calling -- some columns arrive pre-cleaned
    as ISO, others still need the defensive day-first parser."""
    days = (end_series - start_series).dt.days
    return days.where(end_series.notna() & start_series.notna())


def tat_bucket_label(days):
    """Ageing in days -> TAT bucket. Negative ageing is excluded rather than
    bucketed, matching the source workbooks' IF(x<0,"",...)."""
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


def category_matcher(allowed, blank_label=None):
    """Builds a mapper from raw cell text to a canonical category label.

    Matching is case-insensitive because Excel's COUNTIFS is, and the source
    workbooks' own row labels disagree in case with the helper columns they
    match against -- naive equality silently returned zero for the single
    largest row in Overall Cancelled.

    Values outside `allowed` map to None so the caller can drop them; this is
    deliberately an allow-list, so a new category appearing in Freshdesk shows
    up as absent rather than vanishing into a total.
    """
    lookup = {value.casefold(): value for value in allowed}

    def match(value):
        text = "" if pd.isna(value) else str(value).strip()
        if text == "":
            return blank_label
        return lookup.get(text.casefold())

    return match


def count_by(df, column, labels):
    """Count rows per label for one column, always returning every label."""
    counts = dict.fromkeys(labels, 0)
    if len(df):
        for label, n in df[column].value_counts().items():
            if label in counts:
                counts[label] = int(n)
    return counts


def percentages_of(counts, labels):
    """Each label's share of the row total, to one decimal place."""
    total = sum(counts.values())
    if total == 0:
        return dict.fromkeys(labels, 0.0)
    return {label: round(counts[label] / total * 100, 1) for label in labels}


def load_master():
    """The cleaned dataset written by process_upload.py.

    keep_default_na=False: pandas otherwise reads literal "NA" text -- a real,
    meaningful value in some Freshdesk columns -- as missing, destroying the
    distinction between "field says NA" and "field is blank" before any of our
    own code sees it.
    """
    text = kv_store.read_chunked(MASTER_PREFIX)
    if text is None:
        raise RuntimeError("No master dataset found in KV -- run process_upload.py first")
    return pd.read_csv(io.StringIO(text), low_memory=False, keep_default_na=False)


def write_processed(prefix, output):
    kv_store.write_chunked(prefix, json.dumps(output))
    print(f"Wrote dashboard data to KV under '{prefix}'")
