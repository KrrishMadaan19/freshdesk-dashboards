"""Freshdesk raw export -> dashboard-ready cleanup.

Runs automatically on every new upload (called from process_upload.py)
instead of the previous manual Colab step. Ported from
dashboard_automation.py, with two changes:

- Dates are written back as unambiguous ISO strings ("YYYY-MM-DD"), not
  dd/mm/yyyy -- the original's Power Query target no longer applies once
  this runs server-side, and ISO output lets every downstream dashboard
  script parse every date column the same simple way with zero dayfirst
  ambiguity (see date_utils.py).
- Per-upload format DETECTION for Created time / Resolved time /
  WhatsApp Survey Received (date_utils.parse_any_date), not a fixed
  assumption. Freshdesk's raw export format for these columns has been
  observed as both ISO ("2025-12-01 00:37:13") in one export and
  day-first ("01/01/26", no time, 2-digit year) in another -- assuming
  either one by column name silently corrupted real data; see
  docs/excel_process_notes/01-creation-to-assignment.md for both
  incidents (there have been two, in opposite directions).

IMPORTANT: only upload the genuinely raw Freshdesk export here -- if a
file has already been through dashboard_automation.py (or any other
manual cleanup) before upload, this runs a second time on top of it,
and while the backfill rules are idempotent, double-parsing already
date-only values from an unfamiliar format is exactly the kind of thing
that caused the second incident above. When in doubt, re-export fresh
from Freshdesk rather than reusing a processed file.

Rules (unchanged from the original):
1. Created time, Resolved time, WhatsApp Survey Received: date-only
   (time component dropped).
2. Group == "Replacement" and Replacement Group Assignment is blank ->
   fill with Created time.
3. UTR is not blank and Refund Group Assignment is blank -> fill with
   Created time.
4. Resolved time is not blank and Close Looping Group Assignment is
   blank -> fill with Resolved time.
5. Partner Name is set and not one of the excluded pseudo-partners
   (Chat 360 / Product Non-Serviceable / Service Denial) and Service
   Partner Assigned Date Stamp is blank -> fill with Created time.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import columns as col  # noqa: E402
import date_utils  # noqa: E402

# Local aliases into the shared column-name module (see columns.py) -- kept
# short since these are referenced constantly below.
COL_CREATED = col.CREATED_TIME
COL_RESOLVED = col.RESOLVED_TIME
COL_WHATSAPP_SURV = col.WHATSAPP_SURVEY_RECEIVED
COL_GROUP = col.GROUP
COL_REPL_GROUP = col.REPLACEMENT_GROUP_ASSIGNMENT
COL_UTR = col.UTR
COL_REFUND_GROUP = col.REFUND_GROUP_ASSIGNMENT
COL_CLOSE_LOOP = col.CLOSE_LOOPING_GROUP_ASSIGNMENT
COL_PARTNER = col.PARTNER_NAME
COL_SP_ASSIGN_DT = col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP

EXCLUDED_PARTNERS = ["Chat 360", "Product Non-Serviceable", "Service Denial"]

# Freshdesk's own timestamp fields vs. the custom/webhook-populated ones
# -- see date_utils.py for why these need different parsers.
NATIVE_TIMESTAMP_COLS = [COL_CREATED, COL_RESOLVED, COL_WHATSAPP_SURV]
CUSTOM_DATE_COLS = [COL_REPL_GROUP, COL_REFUND_GROUP, COL_CLOSE_LOOP, COL_SP_ASSIGN_DT]


def is_blank(series):
    as_str = series.astype(str).str.strip().str.lower()
    return series.isna() | (as_str == "") | as_str.isin(["nan", "nat"])


def clean_illegal_excel_chars(value):
    if isinstance(value, str):
        return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", value)
    return value


def process(df):
    df = df.copy()

    for col in NATIVE_TIMESTAMP_COLS:
        if col in df.columns:
            # parse_any_date, not parse_native_timestamp: this is raw,
            # not-yet-cleaned upload data, and Freshdesk's export format
            # for these columns has been observed to vary between
            # exports (ISO in one, day-first DD/MM/YY in another) -- see
            # date_utils.py's docstring.
            df[col] = date_utils.parse_any_date(df[col]).dt.normalize()

    for col in CUSTOM_DATE_COLS:
        if col in df.columns:
            df[col] = date_utils.parse_ddmmyyyy(df[col]).dt.normalize()

    if COL_GROUP in df.columns and COL_REPL_GROUP in df.columns:
        mask = (df[COL_GROUP].astype(str).str.strip() == "Replacement") & is_blank(df[COL_REPL_GROUP])
        df.loc[mask, COL_REPL_GROUP] = df.loc[mask, COL_CREATED]

    if COL_UTR in df.columns and COL_REFUND_GROUP in df.columns:
        mask = (~is_blank(df[COL_UTR])) & is_blank(df[COL_REFUND_GROUP])
        df.loc[mask, COL_REFUND_GROUP] = df.loc[mask, COL_CREATED]

    if COL_RESOLVED in df.columns and COL_CLOSE_LOOP in df.columns:
        mask = (~is_blank(df[COL_RESOLVED])) & is_blank(df[COL_CLOSE_LOOP])
        df.loc[mask, COL_CLOSE_LOOP] = df.loc[mask, COL_RESOLVED]

    if COL_PARTNER in df.columns and COL_SP_ASSIGN_DT in df.columns:
        partner_excluded = is_blank(df[COL_PARTNER]) | df[COL_PARTNER].isin(EXCLUDED_PARTNERS)
        mask = (~partner_excluded) & is_blank(df[COL_SP_ASSIGN_DT])
        df.loc[mask, COL_SP_ASSIGN_DT] = df.loc[mask, COL_CREATED]

    for col in NATIVE_TIMESTAMP_COLS + CUSTOM_DATE_COLS:
        if col in df.columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")

    return df.map(clean_illegal_excel_chars)
