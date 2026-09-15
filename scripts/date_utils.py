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
    return pd.to_datetime(series, errors="coerce")


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
    inconsistent sub-formats)."""
    sample = series.dropna().head(20).tolist()
    if _is_year_first(sample):
        return parse_native_timestamp(series)
    return parse_ddmmyyyy(series)
