"""Dashboard 9: SP TAT Performance (step-wise).

Reproduces the SP TAT Performance workbook
(docs/excel_process_notes/09-sp-tat.md) against the master dataset and writes
it to KV as processed:sp-tat.

Scope: on-site service-partner closures -- Resolution Type is Without Spare,
With Spare or Accessories Only, and the ticket has a real Partner Name. That
selects the workbook's RAW sheet to within 4 tickets.

Each step of the on-site journey is aged and banded 0-1 / 2-3 / 4-5 / 6-7 / 7+,
split by whether a spare part was involved (any Spare Name filled in).
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import dashboard_lib as lib  # noqa: E402
import date_utils  # noqa: E402
from preprocess_raw import EXCLUDED_PARTNERS  # noqa: E402

PROCESSED_PREFIX = "processed:sp-tat"

BANDS = lib.TAT_BANDS

# Resolution types in scope, compared on letters and digits only. Freshdesk
# spells "Issue Resolved – Accessories Only" with an en dash where every other
# type uses a hyphen, and the workbook's copy of it has been through an
# encoding round-trip ("Issue Resolved ‚Äì Accessories Only") -- punctuation
# can't be trusted, the words can.
ONSITE_TYPES = [
    "Issue Resolved - Without Spare",
    "Issue Resolved - With Spare",
    "Issue Resolved - Accessories Only",
]

SPARE_NO, SPARE_YES = "SPARE-NO", "SPARE-YES"

MEASURES = {
    "to_sp": "Case creation → SP assignment",
    "sp_to_spare": "SP assignment → Spare assigned",
    "to_spare": "Case creation → Spare assigned",
    # The workbook's "Spare delivered to SP visit done": Resolved time minus
    # Inward Payment Group Assignment. Kept as the workbook defines it -- see
    # the open question in the doc about whether that's the right start date.
    "spare_to_visit": "Spare delivered → SP visit done",
    "sp_to_close": "SP assignment → Close looping",
    "to_resolved": "Case creation → Resolved",
}
# Which steps each sheet block shows, in its row order.
STEPS = {
    SPARE_NO: ["to_sp", "sp_to_close", "to_resolved"],
    SPARE_YES: ["to_sp", "sp_to_spare", "to_spare", "spare_to_visit", "sp_to_close", "to_resolved"],
}

UNKNOWN_PLACE = "Unknown pincode"


def alnum_key(series):
    return series.astype(str).str.casefold().str.replace(r"[^0-9a-z]", "", regex=True)


def main():
    df = lib.load_master()

    partner = lib.required_column(df, col.PARTNER_NAME).astype(str).str.strip()
    excluded = {p.casefold() for p in EXCLUDED_PARTNERS}
    rtype = alnum_key(lib.required_column(df, col.RESOLUTION_TYPE))
    in_scope = (rtype.isin(alnum_key(pd.Series(ONSITE_TYPES)).tolist())
                & (partner != "") & ~partner.str.casefold().isin(excluded))

    created = date_utils.parse_native_timestamp(lib.required_column(df, col.CREATED_TIME))
    resolved = date_utils.parse_native_timestamp(lib.required_column(df, col.RESOLVED_TIME))
    sp = date_utils.parse_native_timestamp(
        lib.required_column(df, col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP))
    # Not touched by preprocess_raw, so still in the export's own format
    # (seen as dd-mm-yyyy hh:mm:ss) -- hence the format-detecting parser.
    spare = date_utils.parse_any_date(lib.optional_date_column(df, col.SPARE_GROUP_ASSIGNMENT))
    inward = date_utils.parse_any_date(
        lib.optional_date_column(df, col.INWARD_PAYMENT_GROUP_ASSIGNMENT))
    surveyed = date_utils.parse_native_timestamp(
        lib.required_column(df, col.WHATSAPP_SURVEY_RECEIVED))

    has_spare = pd.Series(False, index=df.index)
    for name in col.SPARE_NAMES:
        if name in df.columns:
            has_spare |= df[name].astype(str).str.strip() != ""

    band = lib.tat_band
    band_nonneg = lambda d: lib.tat_band(d, drop_negative=True)  # noqa: E731

    places = lib.load_reference("pincode_city_state.csv", "pincode", "city", "state")
    place = lib.lookup(lib.required_column(df, col.PINCODE), places)

    t = pd.DataFrame({
        "_resolved": resolved,
        "_month": lib.month_label(resolved),
        "_spare": has_spare.map({True: SPARE_YES, False: SPARE_NO}),
        # Created time is midnight, so INT(SP - Created) is already calendar days.
        "to_sp": lib.calendar_days(sp, created).map(band),
        # Both real timestamps: the workbook's INT(Spare - SP) stands. It drops
        # negatives (IF(x<0,"",...)), as here.
        "sp_to_spare": lib.elapsed_days(spare, sp).map(band_nonneg),
        "to_spare": lib.calendar_days(spare, created).map(band),
        # Resolved is date-only, Inward Payment isn't: calendar days on both
        # sides instead of the workbook's one-sided INT (see doc).
        "spare_to_visit": lib.calendar_days(resolved, inward).map(band),
        # Same one-sided truncation in the workbook, plus a negative guard --
        # together they DROP every ticket resolved the day its SP was assigned
        # (203 in the workbook's data). Calendar days make those 0.
        "sp_to_close": lib.calendar_days(resolved, sp).map(band_nonneg),
        "to_resolved": lib.calendar_days(resolved, created).map(band),
        "_partner": partner,
        "_survey": lib.required_column(df, col.CSAT_SURVEY).map(lib.csat_dsat),
        "_survey_month": lib.month_label(surveyed),
        "_city": place.map(lambda p: p[0] if p and p[0] else UNKNOWN_PLACE),
        "_state": place.map(lambda p: p[1] if p and p[1] else UNKNOWN_PLACE),
    })[in_scope]

    done = t[t["_resolved"].notna()]
    months = lib.sorted_months(done["_month"])
    rated = t[t["_survey"].notna() & t["_survey_month"].notna()]
    survey_months = lib.sorted_months(rated["_survey_month"])
    print(f"On-site partner tickets: {len(t)} (resolved {len(done)}); months: {months}")

    tat = {
        s: {m: {k: lib.count_by(done[(done["_spare"] == s) & (done["_month"] == m)], k, BANDS)
                for k in STEPS[s]}
            for m in months}
        for s in (SPARE_NO, SPARE_YES)
    }

    def by_place(key):
        return {
            "tat": {m: lib.nested_counts(done[done["_month"] == m], [key], "to_resolved", BANDS)
                    for m in months},
            "survey": {m: lib.nested_counts(rated[rated["_survey_month"] == m], [key],
                                            "_survey", ["CSAT", "DSAT"])
                       for m in survey_months},
        }

    output = {
        "bands": BANDS,
        "measures": MEASURES,
        "steps": STEPS,
        "months": months,
        "survey_months": survey_months,
        "tat": tat,
        # The sheet's "SP SURVEY ANALYSIS": each partner's CSAT/DSAT by the
        # month the survey came back. Partners discovered from the data, not a
        # typed list.
        "partner_survey": {m: lib.nested_counts(rated[rated["_survey_month"] == m], ["_partner"],
                                                "_survey", ["CSAT", "DSAT"])
                           for m in survey_months},
        "state": by_place("_state"),
        "city": by_place("_city"),
        "unknown_place": UNKNOWN_PLACE,
        "latest": done["_resolved"].max().strftime("%Y-%m-%d") if len(done) else None,
    }
    lib.write_processed(PROCESSED_PREFIX, output)


if __name__ == "__main__":
    main()
