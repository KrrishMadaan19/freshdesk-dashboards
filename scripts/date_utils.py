"""Shared date-parsing helpers.

Three real incidents in this project, each a different way date parsing
went silently wrong -- see the "Validation against real production data"
section of docs/excel_process_notes/01-creation-to-assignment.md for the
full story of each:

1. Applying dayfirst=True to a genuinely ISO (YYYY-MM-DD) column swaps
   month/day whenever both are <=12, regardless of which token is the
   year (e.g. "2026-01-08" -> "2026-08-01").
2. pandas' vectorized to_datetime(series, dayfirst=True) infers ONE
   format for an entire column and silently NaTs individually-valid
   values that don't match it (e.g. a bare "DD-MM-YYYY" value dropped in
   a column that's mostly "DD-MM-YYYY HH:MM:SS").
3. Freshdesk's raw export format for the SAME column (e.g. Created time)
   has been observed as both "YYYY-MM-DD HH:MM:SS" (ISO) in one export
   and "DD/MM/YY" (day-first, no time, 2-digit year) in another. Do NOT
   assume a fixed format by column name -- detect it from the actual
   data on every new upload (see parse_any_date below).
"""

import re

import pandas as pd


def parse_ddmmyyyy(series):
    # Element-wise, not pd.to_datetime(series, dayfirst=True) directly --
    # see incident 2 above.
    parsed = series.map(lambda v: pd.to_datetime(v, dayfirst=True, errors="coerce") if pd.notna(v) else pd.NaT)
    # .map() doesn't reliably produce datetime64 dtype on its own --
    # coerce it explicitly so .dt accessors work for callers.
    return pd.to_datetime(parsed)


def parse_native_timestamp(series):
    # No dayfirst -- see incident 1 above. Safe ONLY for genuinely
    # year-first (ISO) data -- which the cleaned master dataset always
    # is (preprocess_raw.py writes every date column back as YYYY-MM-DD),
    # but a fresh raw upload is NOT guaranteed to be; use parse_any_date
    # for that instead.
    #
    # format="ISO8601" rather than letting pandas infer: without it,
    # to_datetime picks ONE format from the first value and NaTs every
    # value that doesn't match it -- incident 2, in its ISO form. A column
    # holding both "2026-01-08 10:30:00" and "2026-01-08" silently lost
    # every date-only value. ISO8601 accepts any valid ISO variant
    # per-element and costs nothing (marginally faster than inference on
    # 177k rows), so there's no reason not to be strict here.
    return pd.to_datetime(series, errors="coerce", format="ISO8601")


def _is_year_first(sample):
    """True if the first token of these date strings is a 4-digit year
    (YYYY-MM-DD / YYYY/MM/DD -- unambiguous order). False (day-first
    assumed) if there's no such evidence, since that's been the more
    common raw-export convention seen in practice."""
    for value in sample:
        if not isinstance(value, str) or not value.strip():
            continue
        first_token = re.split(r"[-/ ]", value.strip())[0]
        return len(first_token) == 4 and first_token.isdigit()
    return False


def parse_any_date(series):
    """For raw, not-yet-cleaned upload data, where the format is not
    known in advance -- see incident 3 above. Detects year-first vs.
    day-first from a sample of the actual values, then parses the whole
    column accordingly (day-first goes through parse_ddmmyyyy's
    element-wise handling, since day-first exports have also shown
    inconsistent sub-formats).

    The sample skips BLANKS, not just nulls. Reading the first 20 rows
    outright was silently wrong on sparse columns: the dataset holds blanks
    as "" (keep_default_na=False, deliberately -- see process_upload.py), so
    dropna() keeps them, and a column whose first 20 rows happen to be empty
    produced no evidence at all and fell through to day-first. On a column
    that was actually ISO that is incident 1 -- "2026-01-08" read as
    2026-08-01. Caught on `Pickup Initiated Date` and `Escalation Group
    Assignment`, both sparse enough to start with 20 blanks.
    """
    text = series.dropna().astype(str).str.strip()
    sample = text[text != ""].head(20).tolist()
    if _is_year_first(sample):
        return parse_native_timestamp(series)
    return parse_ddmmyyyy(series)
