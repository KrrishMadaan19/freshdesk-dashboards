"""Dashboard 3: Daily Pending and Closure.

Reproduces the formulas in docs/excel_process_notes/03-daily-pending-closure.md
against the master dataset, and writes a per-month, per-block daily grid to KV
as processed:daily-pending-closure.

Shape differs from Dashboards 1 and 5. Those are one grid each; this is SEVEN
stacked blocks per month, each one "categories down, days-of-month across",
with an MTD total and a per-day average. The source workbook keeps one sheet
per month rather than one sheet per view.

Two things about the source workbook are worth knowing before reading on.

ONE: only its SEP'26 sheet is live. Every earlier month is pasted-as-values
with whatever row set existed when it was frozen -- Jan'26 lists 16 service
partners, Aug'26 lists 51, Sep'26 lists 161, and the block sets themselves
differ (Jan'26 has no bucket-wise closure block at all). So SEP'26's formulas
are the only spec there is, and they are applied here to EVERY month, with row
labels discovered from the data instead of frozen. New groups, sources and
partners therefore appear on their own. The cost is that this dashboard's
historical months will not match the workbook's historical sheets cell-for-cell
-- they cannot, because those sheets were each built from a different row set.

TWO: its two raw sheets put different fields at the same column letters.
'RAW DATA June onwards'!AF is `Partner Name`; 'RAW-DATA Jan-May'!AF is
`Service`. EF is `RESOLVED DATE` in one and `Email` in the other. Every
bucket-date column shifts between them. Addressing anything here positionally
would read Email as a resolved date for half the year, so every column is
looked up by name through columns.py -- see that module.
"""

import calendar
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import dashboard_lib as lib  # noqa: E402
import date_utils  # noqa: E402

MASTER_PREFIX = lib.MASTER_PREFIX
PROCESSED_PREFIX = "processed:daily-pending-closure"

# The three dimensions the blocks count by.
GROUP_COL = col.GROUP
SOURCE_COL = col.SOURCE
PARTNER_COL = col.PARTNER_NAME

# The two dates the inflow/closure blocks key off. The workbook reads its own
# helper columns `CREATION DATE` = INT(Created time) and `RESOLVED DATE` =
# IF(Resolved time="","",INT(Resolved time)); taking the date part of the
# parsed timestamp is the same thing without the helper column.
CREATED_COL = col.CREATED_TIME
RESOLVED_COL = col.RESOLVED_TIME

# The eight bucket-movement date columns, in the workbook's own row order.
# Each is its own row in the bucket-inflow block: the count for a day is how
# many tickets moved into that bucket on it.
BUCKET_DATE_COLS = [
    col.REFUND_GROUP_ASSIGNMENT,
    col.REPLACEMENT_GROUP_ASSIGNMENT,
    col.INWARD_PAYMENT_GROUP_ASSIGNMENT,
    col.SPARE_GROUP_ASSIGNMENT,
    col.PICKUP_INITIATED_DATE,
    col.ESCALATION_GROUP_ASSIGNMENT,
    col.CLOSE_LOOPING_GROUP_ASSIGNMENT,
    col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP,
]

# preprocess_raw.py writes these back as unambiguous ISO text, so the plain
# no-dayfirst parser is correct for them. Service Partner Assigned Date Stamp
# is in here too -- it keeps its time-of-day (deliberately, for Dashboard 1's
# ageing arithmetic), which parse_native_timestamp handles and .dt.date then
# discards, exactly as the workbook's INT() does.
ISO_DATE_COLS = {
    col.CREATED_TIME,
    col.RESOLVED_TIME,
    col.REFUND_GROUP_ASSIGNMENT,
    col.REPLACEMENT_GROUP_ASSIGNMENT,
    col.CLOSE_LOOPING_GROUP_ASSIGNMENT,
    col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP,
}

# PRODUCT CLASSIFICATION 2 in the workbook is
#   =IF(AL="SERVICEABLE","SERVICEABLE",IF(AL="NON SERVICEABLE","NON SERVICEABLE","NOT SELECTED"))
# which is exhaustive by construction: anything that isn't one of the two named
# values -- including blanks and any value added in Freshdesk later -- falls
# into NOT SELECTED. Unlike the allow-lists in Dashboard 5, nothing can go
# missing here, so a three-way bucket is safe.
CLASSIFICATION_ROWS = ["SERVICEABLE", "NON SERVICEABLE", "NOT SELECTED"]
NOT_SELECTED = "NOT SELECTED"

# (key, title, total row label, description shown on the page)
#
# Block order and titles follow the SEP'26 sheet top to bottom. The workbook
# labels its total rows inconsistently ("Over All Inflow", "TOTAL", "Total",
# "Grand Total"); those labels are kept verbatim so a reader comparing the two
# side by side sees the same words.
BLOCKS = [
    ("inflow", "Inflow", "Over All Inflow",
     "Tickets created on each day, by the group they landed in."),
    ("bucket-inflow", "Inflow (as per bucket movement dates)", "TOTAL",
     "Tickets that moved into each bucket on each day, counted on that bucket's own date column."),
    ("inflow-source", "Inflow Source", "Total",
     "Tickets created on each day, by the channel they came in through."),
    ("sp-inflow", "SP Inflow", "Grand Total",
     "Tickets assigned to each service partner on each day, counted on Service Partner Assigned Date Stamp."),
    ("closure", "Closure (bucket-wise)", "Over All Closure",
     "Tickets resolved on each day, by the group that closed them."),
    ("closure-classification", "Closure — product classification", "PRODUCT CLASSIFICATION-WISE",
     "Tickets resolved on each day, split by whether the product was serviceable."),
    ("sp-closure", "SP Closure", "Grand Total",
     "Tickets resolved on each day, by service partner."),
]


def unparsed_count(df, name, parsed):
    """How many non-blank values in this column failed to parse.

    Reported rather than swallowed. The 2026-09-30 export carried 55 `Refund
    Group Assignment` values reading "13-07-20026" -- a mistyped year, in a
    column that is otherwise ISO. No parser can rescue a year of 20026, so they
    are genuinely unusable and are dropped; what would be wrong is dropping them
    invisibly, because then nobody ever fixes the source records. 55 of 19,420
    is small, but the only way anyone learns it is non-zero is if the page says
    so.
    """
    if name not in df.columns:
        return 0
    non_blank = df[name].fillna("").astype(str).str.strip() != ""
    return int((non_blank & parsed.isna()).sum())


def parsed_date(df, name):
    """A date column as a normalised date series, parsed the way that column
    needs. Which parser applies is NOT a property of this dashboard -- it is a
    property of whether preprocess_raw.py cleaned that column on the way in, so
    the decision lives in ISO_DATE_COLS next to the reason for it."""
    raw = lib.optional_date_column(df, name)
    if name in ISO_DATE_COLS:
        return date_utils.parse_native_timestamp(raw).dt.normalize()
    # Not cleaned upstream, so the format is whatever this export happened to
    # use. parse_any_date DETECTS it per column instead of assuming; the
    # alternative, parse_ddmmyyyy, turns "2026-01-08" into 2026-08-01 if such a
    # column ever arrives ISO -- verified, not theoretical -- and Freshdesk has
    # already changed format on a column once in this project's history.
    return date_utils.parse_any_date(raw).dt.normalize()


def text_column(df, name):
    """A dimension column as stripped text, with blanks as ''. Blank never
    matches a row label, which is what COUNTIFS does with an empty criterion
    cell -- note the workbook's `No Group` is a literal value in the export,
    not a blank."""
    if name not in df.columns:
        print(f"WARNING: column '{name}' not present -- its block will be empty")
        return pd.Series("", index=df.index)
    return df[name].fillna("").astype(str).str.strip()


def tally(dates, categories):
    """-> {month: {label: {day: count}}}.

    One pass per block. Rows with no usable date for this block are dropped
    (they have no day to sit under), as are blank categories, matching
    COUNTIFS on a two-criterion pair.

    Matching is case-insensitive -- COUNTIFS is, and pandas `==` is not. The
    first label spelling seen wins as the display label, so a source that
    reports "Easy care solution" and "EASY CARE SOLUTION" lands in one row
    rather than two that each look half-counted.
    """
    keep = dates.notna() & (categories != "")
    frame = pd.DataFrame({
        "month": lib.month_label(dates[keep]),
        "day": dates[keep].dt.day,
        "label": categories[keep],
    })

    canonical = {}
    for label in frame["label"]:
        canonical.setdefault(label.casefold(), label)
    frame["label"] = frame["label"].map(lambda s: canonical[s.casefold()])

    out = {}
    for (month, label, day), n in frame.value_counts(["month", "label", "day"]).items():
        out.setdefault(month, {}).setdefault(label, {})[int(day)] = int(n)
    return out


def tally_single_row(dates, label):
    """As tally(), for a block whose rows are date COLUMNS rather than values
    of one column -- every non-blank date is a count of one for `label`."""
    keep = dates.notna()
    frame = pd.DataFrame({"month": lib.month_label(dates[keep]), "day": dates[keep].dt.day})
    out = {}
    for (month, day), n in frame.value_counts(["month", "day"]).items():
        out.setdefault(month, {}).setdefault(label, {})[int(day)] = int(n)
    return out


def merge_tallies(tallies):
    """Combine per-row tallies that each cover one label into one structure."""
    merged = {}
    for t in tallies:
        for month, by_label in t.items():
            merged.setdefault(month, {}).update(by_label)
    return merged


def sort_labels(labels):
    """Alphabetical, case-insensitively -- the workbook's own row order. Note
    its partner lists contain near-duplicate spellings of the same company
    ("Akash Refrigeration" / "Akash Refrigetation", "Meer Infotech" / "Meera
    Infotech"). Those are real distinct values in the export, so they stay
    distinct rows here; silently merging them would be guessing at which pairs
    are typos."""
    return sorted(labels, key=lambda s: (s.casefold(), s))


def build_block(tallied, month, row_order, total_label, days_in_month, avg_days):
    """One block for one month: rows x days, plus MTD and AVG per row."""
    by_label = tallied.get(month, {})
    rows = row_order if row_order is not None else sort_labels(by_label)

    counts = {}
    mtd = {}
    avg = {}
    for label in rows:
        per_day = by_label.get(label, {})
        # Sparse on purpose: a 161-partner block over 31 days is mostly zeros,
        # and the page treats a missing day as 0.
        counts[label] = {str(d): per_day[d] for d in sorted(per_day) if per_day[d]}
        mtd[label] = sum(per_day.values())
        avg[label] = round(mtd[label] / avg_days, 1) if avg_days else 0.0

    # The total row sums every category row. The workbook's own closure total
    # does NOT -- see the note in the docs; it is a drag error whose excluded
    # row depends on alphabetical position, so reproducing it would mean the
    # total's meaning changed whenever a group was added.
    total_per_day = {}
    for label in rows:
        for day, n in counts[label].items():
            total_per_day[day] = total_per_day.get(day, 0) + n
    total_mtd = sum(mtd[label] for label in rows)

    return {
        "rows": rows,
        "totalLabel": total_label,
        "counts": counts,
        "mtd": mtd,
        "avg": avg,
        "total": total_per_day,
        "totalMtd": total_mtd,
        "totalAvg": round(total_mtd / avg_days, 1) if avg_days else 0.0,
        "days": [str(d) for d in range(1, days_in_month + 1)],
    }


def main():
    df = lib.load_master()

    created = parsed_date(df, CREATED_COL)
    resolved = parsed_date(df, RESOLVED_COL)
    sp_assigned = parsed_date(df, col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP)

    # Every date column this dashboard reads, checked for values that are filled
    # in but unreadable -- see unparsed_count().
    unparsed = {}
    for name in [CREATED_COL, RESOLVED_COL] + BUCKET_DATE_COLS:
        n = unparsed_count(df, name, parsed_date(df, name))
        if n:
            unparsed[name] = n
            print(f"WARNING: {n} unreadable date(s) in '{name}' -- these rows are "
                  f"not counted in any block keyed on that column")

    group = text_column(df, GROUP_COL)
    source = text_column(df, SOURCE_COL)
    partner = text_column(df, PARTNER_COL)

    classification = text_column(df, col.PRODUCT_CLASSIFICATION).map(
        lambda v: v.upper() if v.upper() in ("SERVICEABLE", "NON SERVICEABLE") else NOT_SELECTED
    )

    tallies = {
        "inflow": tally(created, group),
        "bucket-inflow": merge_tallies(
            tally_single_row(parsed_date(df, name), name) for name in BUCKET_DATE_COLS
        ),
        "inflow-source": tally(created, source),
        "sp-inflow": tally(sp_assigned, partner),
        "closure": tally(resolved, group),
        "closure-classification": tally(resolved, classification),
        "sp-closure": tally(resolved, partner),
    }

    # Months come from inflow and closure only. The bucket-date columns can
    # carry a stray far-future or far-past date, and letting one of those
    # invent a whole month of otherwise-empty grids would be worse than
    # leaving its handful of tickets out of the month list.
    months = lib.sorted_months(
        pd.Series(sorted(set(tallies["inflow"]) | set(tallies["closure"])))
    )
    print(f"Months found: {months}")

    # Row order is fixed where the workbook fixes it, and discovered from the
    # data where the workbook froze a hand-maintained list.
    FIXED_ROWS = {
        "bucket-inflow": BUCKET_DATE_COLS,
        "closure-classification": CLASSIFICATION_ROWS,
    }

    # Discovered labels are collected across EVERY month, not per month, so all
    # months show the same rows in the same order.
    #
    # Per-month discovery was the obvious choice and the wrong one: it drops a
    # label with no activity that month, so Sep showed 18 groups against the
    # workbook's 19 and 111 service partners against its 161. Every one of those
    # missing rows was zero all month -- verified, no exceptions -- so no number
    # was ever wrong, but rows that don't line up read as a discrepancy to
    # anyone comparing the two side by side, and checking 161 rows to find
    # which 50 are merely absent is exactly the manual work this replaces.
    #
    # Across the dataset this yields 19 / 11 / 19 / 160 / 160 rows against the
    # sheet's 19 / 11 / 19 / 161 / 161. The two it lacks are dead rows in the
    # sheet: `Product Non-Serviceable` never receives an SP-assigned date, and
    # `BABITA ELECTRICALS` (not to be confused with `BABITA ELECTRICAL SERVICE`,
    # which is present) has no resolved ticket anywhere in the data.
    row_order = {}
    for key, _, _, _ in BLOCKS:
        if key in FIXED_ROWS:
            row_order[key] = FIXED_ROWS[key]
            continue
        labels = set()
        for month in months:  # only displayed months, so no row is zero everywhere
            labels |= set(tallies[key].get(month, {}))
        row_order[key] = sort_labels(labels)

    monthly = {}
    for month in months:
        period = pd.Period(lib.month_sort_key(month), freq="M")
        days_in_month = calendar.monthrange(period.year, period.month)[1]

        # AVG denominator: the workbook's AVERAGE(D:Y) is a hand-maintained
        # range the analyst extends as days are filled in ("update the AVG
        # column with the corresponding cell address which have been
        # updated"). The faithful automatic equivalent is the days this month
        # actually has data for, so a month-to-date average isn't diluted by
        # days that haven't happened yet.
        last_day = 0
        for key in ("inflow", "closure"):
            for per_day in tallies[key].get(month, {}).values():
                if per_day:
                    last_day = max(last_day, max(per_day))
        avg_days = last_day or days_in_month

        monthly[month] = {
            "daysInMonth": days_in_month,
            "lastDayWithData": last_day,
            "avgDays": avg_days,
            "weekdays": [
                calendar.day_abbr[calendar.weekday(period.year, period.month, d)].upper()
                for d in range(1, days_in_month + 1)
            ],
            "blocks": {
                key: build_block(
                    tallies[key], month, row_order[key], total_label,
                    days_in_month, avg_days,
                )
                for key, _, total_label, _ in BLOCKS
            },
        }

    output = {
        "months": months,
        "blocks": [
            {"key": key, "title": title, "totalLabel": total_label, "description": desc}
            for key, title, total_label, desc in BLOCKS
        ],
        "monthly": monthly,
        "latestCreated": created.max().date().isoformat() if created.notna().any() else None,
        "latestResolved": resolved.max().date().isoformat() if resolved.notna().any() else None,
        "unparsedDates": unparsed,
    }

    lib.write_processed(PROCESSED_PREFIX, output)
    print(f"({len(months)} months x {len(BLOCKS)} blocks)")


if __name__ == "__main__":
    main()
