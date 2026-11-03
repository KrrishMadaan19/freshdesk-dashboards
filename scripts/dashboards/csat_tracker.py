"""Dashboard 4: C-SAT Tracker.

Reproduces the C-SAT Tracker workbook (docs/excel_process_notes/04-csat-tracker.md)
against the master dataset, and writes it to KV as processed:csat-tracker.

Everything keys off `WhatsApp Survey Received` -- the date the customer's
rating came back -- not Created or Resolved time. A ticket with no such date
was never rated and is not part of this dashboard at all, which is exactly
what the workbook's DATA sheet is pre-filtered to.

What the workbook's helper columns compute, all reproduced row-for-row on its
own 18,887 rows with zero differences:
  EE Month     TEXT(received, "MMM'YY")
  EF CSAT      the raw `CSAT Survey` rating
  EH Status    Positive / Negative / "" from the rating (see POSITIVE/NEGATIVE)
  EI ResMap    `Resolution Type`, blank -> "Not Selected Resolution Type"
  EJ Week      day-of-month bucket, lib.week_bucket
  EK Day       day-of-month ordinal
  EL Tier      VLOOKUP(Pincode) into the city-tier table, first match
"""

import csv
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import dashboard_lib as lib  # noqa: E402
import date_utils  # noqa: E402

PROCESSED_PREFIX = "processed:csat-tracker"

RECEIVED_COL = col.WHATSAPP_SURVEY_RECEIVED
RATING_COL = col.CSAT_SURVEY
RESOLUTION_TYPE_COL = col.RESOLUTION_TYPE
PINCODE_COL = col.PINCODE

# The five ratings, in the order the workbook's Dashboard sheet lays them out
# (worst to best). The per-sheet orders differ -- Resolution Wise and Daily
# Flow put the two "satisfied" columns first -- but one order everywhere on
# the site reads better than faithfully reproducing three.
RATINGS = [
    "Extremely dissatisfied",
    "Dissatisfied",
    "Neither satisfied nor dissatisfied",
    "Satisfied",
    "Extremely satisfied",
]

# The workbook counts the neutral rating as NEGATIVE: its Status helper puts
# "Neither satisfied nor dissatisfied" in the Negative branch, and every
# Negative total on every sheet is the sum of the bottom three ratings. That is
# a business definition, not a formula slip -- reproduced as-is.
POSITIVE = ["Satisfied", "Extremely satisfied"]
NEGATIVE = ["Extremely dissatisfied", "Dissatisfied", "Neither satisfied nor dissatisfied"]

NOT_SELECTED = "Not Selected Resolution Type"

# City tiers from the workbook's METRO & NON-METRO sheet. "Unmapped" is ours:
# the workbook's tier blocks only have the three real tiers, so a ticket whose
# pincode isn't in the table (or maps to the table's literal "#N/A" text)
# silently drops out and the three columns don't add up to the month's total.
# The three tier columns still match the workbook cell for cell; the fourth
# just makes the gap visible.
TIERS = ["Top 25", "Next 15", "Rest"]
UNMAPPED = "Unmapped"

TIER_TABLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reference", "pincode_tiers.csv",
)


def normalise_pincode(value):
    """Pincodes arrive as text, and a CSV round-trip through anything numeric
    can leave "400104.0". Strip that and whitespace -- nothing more, so a
    genuinely malformed pincode stays unmatched instead of being guessed at."""
    text = "" if pd.isna(value) else str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def load_tiers():
    """pincode -> tier, from the workbook's lookup sheet.

    The sheet has 128,591 rows for 20,848 distinct pincodes, and 738 pincodes
    appear with DIFFERENT tiers on different rows. VLOOKUP returns the first
    match, so pincode_tiers.csv was built keeping the first row per pincode --
    it reproduces the workbook's tier column exactly on all 18,887 of its rows.
    Rows whose tier is the literal text "#N/A" are kept in the file (so the
    file is a faithful copy) but are not a tier, and land in UNMAPPED.
    """
    known = {t.casefold(): t for t in TIERS}
    tiers = {}
    with open(TIER_TABLE, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            tier = known.get(row["tier"].strip().casefold())
            if tier:
                tiers[row["pincode"]] = tier
    return tiers


def rating_matcher():
    # Case-insensitive, like COUNTIFS. A rating outside the five is not
    # counted anywhere (the workbook's COUNTIFS can't see it either) but IS
    # reported, so a renamed rating in Freshdesk can't vanish quietly.
    return lib.category_matcher(RATINGS)


def grid(df, row_col, row_labels, col_col, col_labels):
    """{row: {col: count}} for every row label and column label."""
    return {
        r: lib.count_by(df[df[row_col] == r], col_col, col_labels)
        for r in row_labels
    }


def resolution_order(labels):
    """Resolution types discovered from the data, alphabetically, with the
    blank-type bucket last. The workbook hard-codes 17 rows on both its
    Resolution Wise and Daily Tracker-DSAT sheets, so a type added later
    (Sep'26: "Issue Resolved - Accessories Only", 7 DSATs) matches no row and
    vanishes -- including from DSAT's Grand Total, which reads 132 for a month
    with 139 negatives. Discovering rows from the data can't drop one."""
    rest = sorted(l for l in labels if l != NOT_SELECTED)
    return rest + ([NOT_SELECTED] if NOT_SELECTED in labels else [])


def main():
    df = lib.load_master()

    received = date_utils.parse_native_timestamp(
        lib.required_column(df, RECEIVED_COL)
    ).dt.normalize()
    rating = lib.required_column(df, RATING_COL).map(rating_matcher())
    raw_rating = lib.required_column(df, RATING_COL).astype(str).str.strip()

    resolution = lib.required_column(df, RESOLUTION_TYPE_COL).astype(str).str.strip()
    resolution = resolution.where(resolution != "", NOT_SELECTED)

    tiers = load_tiers()
    tier = lib.required_column(df, PINCODE_COL).map(
        lambda p: tiers.get(normalise_pincode(p), UNMAPPED)
    )

    df = pd.DataFrame({
        "_received": received,
        "_rating": rating,
        "_raw_rating": raw_rating,
        "_resolution": resolution,
        "_tier": tier,
    })

    surveyed = df[df["_received"].notna()].copy()
    surveyed["_month"] = lib.month_label(surveyed["_received"])
    surveyed["_date"] = surveyed["_received"].dt.strftime("%Y-%m-%d")
    surveyed["_week"] = surveyed["_received"].dt.day.map(lib.week_bucket)
    surveyed["_day"] = surveyed["_received"].dt.day.map(lib.day_ordinal)
    surveyed["_status"] = surveyed["_rating"].map(
        lambda r: "Positive" if r in POSITIVE else "Negative" if r in NEGATIVE else None
    )

    # A received date with no rating: the workbook's Daily Survey Received
    # Count includes these (it counts the date column alone) while every
    # rating grid can't. Kept as its own figure so the two reconcile.
    unrated = surveyed[surveyed["_raw_rating"] == ""]
    unknown = surveyed[(surveyed["_raw_rating"] != "") & surveyed["_rating"].isna()]
    if len(unknown):
        print(f"WARNING: {len(unknown)} ratings outside the known five, not counted: "
              f"{unknown['_raw_rating'].value_counts().to_dict()}")

    rated = surveyed[surveyed["_rating"].notna()]
    months = lib.sorted_months(surveyed["_month"])
    print(f"Surveyed rows: {len(surveyed)}  rated: {len(rated)}  "
          f"unrated: {len(unrated)}  unknown rating: {len(unknown)}")
    print(f"Months found: {months}")

    tier_cols = TIERS + [UNMAPPED]
    monthly, tier_all, tier_pos, tier_neg = {}, {}, {}, {}
    weekly, daily, received_by_day, resolution_grid, dsat_daily = {}, {}, {}, {}, {}
    resolutions = {}

    for m in months:
        mr = rated[rated["_month"] == m]
        ms = surveyed[surveyed["_month"] == m]

        monthly[m] = lib.count_by(mr, "_rating", RATINGS)
        tier_all[m] = lib.count_by(mr, "_tier", tier_cols)
        tier_pos[m] = lib.count_by(mr[mr["_status"] == "Positive"], "_tier", tier_cols)
        tier_neg[m] = lib.count_by(mr[mr["_status"] == "Negative"], "_tier", tier_cols)

        weekly[m] = grid(mr, "_week", lib.WEEKS, "_rating", RATINGS)

        dates = sorted(ms["_date"].unique())
        daily[m] = grid(mr, "_date", dates, "_rating", RATINGS)
        received_by_day[m] = lib.count_by(ms, "_date", dates)

        res_rows = resolution_order(set(mr["_resolution"]))
        resolutions[m] = res_rows
        resolution_grid[m] = grid(mr, "_resolution", res_rows, "_rating", RATINGS)
        negatives = mr[mr["_status"] == "Negative"]
        dsat_rows = resolution_order(set(negatives["_resolution"]))
        dsat_daily[m] = {
            "rows": dsat_rows,
            "counts": grid(negatives, "_resolution", dsat_rows, "_day", lib.DAY_ORDINALS),
        }

    output = {
        "ratings": RATINGS,
        "positive": POSITIVE,
        "negative": NEGATIVE,
        "tiers": tier_cols,
        "weeks": lib.WEEKS,
        "days": lib.DAY_ORDINALS,
        "months": months,
        "monthly": monthly,
        "tier_all": tier_all,
        "tier_positive": tier_pos,
        "tier_negative": tier_neg,
        "weekly": weekly,
        "daily": daily,
        "received_by_day": received_by_day,
        "resolutions": resolutions,
        "resolution": resolution_grid,
        "dsat_daily": dsat_daily,
        "unrated_by_month": lib.count_by(unrated, "_month", months),
        "unknown_ratings": unknown["_raw_rating"].value_counts().to_dict(),
        "latest": surveyed["_received"].max().strftime("%Y-%m-%d") if len(surveyed) else None,
    }

    lib.write_processed(PROCESSED_PREFIX, output)


if __name__ == "__main__":
    main()
