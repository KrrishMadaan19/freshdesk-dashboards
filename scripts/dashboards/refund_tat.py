"""Dashboard 6: Refund TAT Performance.

Reproduces the Refund TAT Performance workbook
(docs/excel_process_notes/06-refund-tat.md) against the master dataset and
writes it to KV as processed:refund-tat.

Scope: tickets that entered the refund bucket (`Refund Group Assignment` is
set), counted in the month they were resolved. See SCOPE below for why that,
and not the workbook's own row set, defines the report.

Three ageings, each banded 0-1 / 2-3 / 4-5 / 6-7 / 7+ (lib.tat_band):
  to_refund           Created time            -> Refund Group Assignment
  refund_to_resolved  Refund Group Assignment -> Resolved time
  to_resolved         Created time            -> Resolved time
split by serviceability, which the workbook takes from the ERP MODEL via a
lookup table -- not from the export's own `Product Classification` field.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import dashboard_lib as lib  # noqa: E402
import date_utils  # noqa: E402

PROCESSED_PREFIX = "processed:refund-tat"

BANDS = lib.TAT_BANDS

MEASURES = [
    {"key": "to_refund", "label": "Case creation → Refund bucket"},
    # The workbook calls this "Refund bucket movement to close looping", but
    # its formula is Resolved time - Refund Group Assignment; the Close
    # Looping Group Assignment column isn't involved. Labelled for what it is.
    {"key": "refund_to_resolved", "label": "Refund bucket → Resolved"},
    {"key": "to_resolved", "label": "Case creation → Resolved"},
]

SERVICEABLE = "SERVICEABLE"
NON_SERVICEABLE = "NON-SERVICEABLE"
# A model the lookup table doesn't know. The workbook has no row for these
# (887 of its 17,675 tickets), so its two classes never add up to the month.
UNMAPPED = "Unmapped"
CLASSES = [SERVICEABLE, NON_SERVICEABLE, UNMAPPED]

UNKNOWN_PLACE = "Unknown pincode"

# SCOPE. The workbook's RAW sheet is a daily paste of tickets that were
# `Resolved` at paste time, so it silently misses (a) refunds rated or
# resolved after their paste day, and (b) tickets that went straight to
# `Closed` -- mostly cancellations. Against the Oct-12 export: 1,024 tickets
# with a Refund Group Assignment, resolved Jan 2 - Sep 22, aren't in the
# workbook (134 of them genuine "Issue Resolved - With Refund"). The site
# counts every ticket that entered the refund bucket instead -- one explicit
# rule, rather than an accident of paste timing.
SCOPE_COLUMN = col.REFUND_GROUP_ASSIGNMENT


def main():
    df = lib.load_master()

    created = date_utils.parse_native_timestamp(lib.required_column(df, col.CREATED_TIME))
    resolved = date_utils.parse_native_timestamp(lib.required_column(df, col.RESOLVED_TIME))
    refund = date_utils.parse_native_timestamp(lib.required_column(df, SCOPE_COLUMN))
    surveyed = date_utils.parse_native_timestamp(
        lib.required_column(df, col.WHATSAPP_SURVEY_RECEIVED))

    in_scope = refund.notna() & resolved.notna()
    print(f"Tickets with a {SCOPE_COLUMN}: {int(refund.notna().sum())}  "
          f"(resolved: {int(in_scope.sum())})")

    serviceability = lib.load_reference("erp_model_serviceability.csv", "erp_model", "serviceability")
    places = lib.load_reference("pincode_city_state.csv", "pincode", "city", "state")
    place = lib.lookup(lib.required_column(df, col.PINCODE), places)

    t = pd.DataFrame({
        "_resolved": resolved,
        "_month": lib.month_label(resolved),
        "_class": lib.lookup(lib.required_column(df, col.ERP_MODEL), serviceability, UNMAPPED)
                     .map(lambda v: v.upper() if v.upper() in (SERVICEABLE, NON_SERVICEABLE) else UNMAPPED),
        "to_refund": lib.calendar_days(refund, created).map(lib.tat_band),
        "refund_to_resolved": lib.calendar_days(resolved, refund).map(lib.tat_band),
        "to_resolved": lib.calendar_days(resolved, created).map(lib.tat_band),
        "_survey": lib.required_column(df, col.CSAT_SURVEY).map(lib.csat_dsat),
        "_survey_month": lib.month_label(surveyed),
        "_city": place.map(lambda p: p[0] if p and p[0] else UNKNOWN_PLACE),
        "_state": place.map(lambda p: p[1] if p and p[1] else UNKNOWN_PLACE),
        "_category": lib.required_column(df, col.ERP_CATEGORY).astype(str).str.strip(),
        "_subcategory": lib.required_column(df, col.ERP_SUB_CATEGORY).astype(str).str.strip(),
    })[in_scope]

    months = lib.sorted_months(t["_month"])
    print(f"Months found: {months}")

    tat = {
        cls: {
            m: {ms["key"]: lib.count_by(part[part["_month"] == m], ms["key"], BANDS)
                for ms in MEASURES}
            for m in months
        }
        for cls, part in ((c, t[t["_class"] == c]) for c in CLASSES)
    }

    rated = t[t["_survey"].notna() & t["_survey_month"].notna()]
    survey_months = lib.sorted_months(rated["_survey_month"])
    survey = {m: lib.count_by(rated[rated["_survey_month"] == m], "_survey", ["CSAT", "DSAT"])
              for m in survey_months}

    def by_place(key):
        return {
            "tat": {m: lib.nested_counts(t[t["_month"] == m], [key], "to_resolved", BANDS)
                    for m in months},
            "survey": {m: lib.nested_counts(rated[rated["_survey_month"] == m], [key],
                                            "_survey", ["CSAT", "DSAT"])
                       for m in survey_months},
        }

    def by_label(key):
        return {m: {k: int(v) for k, v in t[t["_month"] == m][key]
                    .replace("", "(blank)").value_counts().items()}
                for m in months}

    output = {
        "bands": BANDS,
        "measures": MEASURES,
        "classes": CLASSES,
        "months": months,
        "survey_months": survey_months,
        "tat": tat,
        "survey": survey,
        "state": by_place("_state"),
        "city": by_place("_city"),
        "category": by_label("_category"),
        "subcategory": by_label("_subcategory"),
        "unknown_place": UNKNOWN_PLACE,
        "latest": t["_resolved"].max().strftime("%Y-%m-%d") if len(t) else None,
    }
    lib.write_processed(PROCESSED_PREFIX, output)


if __name__ == "__main__":
    main()
