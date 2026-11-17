"""Dashboard 8: Service Partner Closure Bifurcation.

Reproduces the SP Closure Bifurcation workbook
(docs/excel_process_notes/08-sp-closure-bifurcation.md) against the master
dataset and writes it to KV as processed:sp-closure-bifurcation.

One scorecard per resolved month: for every service partner, how many of its
tickets closed under each resolution type, how many of the three on-site types
closed within TAT, and the partner's CSAT/DSAT.

Scope: tickets with a real `Partner Name` -- every partner except the
pseudo-partners preprocess_raw.py already excludes. That reproduces the
workbook's RAW sheet exactly (26,477 of its tickets, zero extra).
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import columns as col  # noqa: E402
import dashboard_lib as lib  # noqa: E402
import date_utils  # noqa: E402
from preprocess_raw import EXCLUDED_PARTNERS  # noqa: E402

PROCESSED_PREFIX = "processed:sp-closure-bifurcation"

# The five resolution types the sheet counts, in its column order. Its
# "TOTAL COMPLAINT" is the sum of exactly these five.
WITHOUT_SPARE = "Issue Resolved - Without Spare"
WITH_SPARE = "Issue Resolved - With Spare"
INSTALLATION = "Resolved - With Installation"
REFUND = "Issue Resolved - With Refund"
REPLACEMENT = "Issue Resolved - With Replacement"
TYPES = [WITHOUT_SPARE, WITH_SPARE, INSTALLATION, REFUND, REPLACEMENT]

# The on-site types carry a TAT: resolved within TAT_DAYS calendar days of the
# partner being assigned. The sheet's formula is <=3; 458 of its rows hold a
# stale <=7 result instead (scattered blocks of pasted values), which is not
# reproduced -- see the doc.
TAT_TYPES = [WITHOUT_SPARE, WITH_SPARE, INSTALLATION]
TAT_DAYS = 3


def main():
    df = lib.load_master()

    partner = lib.required_column(df, col.PARTNER_NAME).astype(str).str.strip()
    excluded = {p.casefold() for p in EXCLUDED_PARTNERS}
    in_scope = (partner != "") & ~partner.str.casefold().isin(excluded)

    created = date_utils.parse_native_timestamp(lib.required_column(df, col.CREATED_TIME))
    resolved = date_utils.parse_native_timestamp(lib.required_column(df, col.RESOLVED_TIME))
    sp_assigned = date_utils.parse_native_timestamp(
        lib.required_column(df, col.SERVICE_PARTNER_ASSIGNED_DATE_STAMP))
    surveyed = date_utils.parse_native_timestamp(
        lib.required_column(df, col.WHATSAPP_SURVEY_RECEIVED))

    # =INT(IF(SP Assigned="", Created, SP Assigned)) -- a ticket with no
    # assignment stamp is aged from creation.
    assigned = sp_assigned.fillna(created)

    rtype = lib.required_column(df, col.RESOLUTION_TYPE).map(lib.category_matcher(TYPES))
    ageing = lib.calendar_days(resolved, assigned)

    t = pd.DataFrame({
        "_partner": partner,
        "_month": lib.month_label(resolved),
        "_type": rtype,
        "_under": rtype.isin(TAT_TYPES) & (ageing <= TAT_DAYS),
        "_survey": lib.required_column(df, col.CSAT_SURVEY).map(lib.csat_dsat),
        "_survey_month": lib.month_label(surveyed),
        "_resolved": resolved,
    })[in_scope]

    resolved_t = t[t["_resolved"].notna()]
    months = lib.sorted_months(resolved_t["_month"])
    survey_months = lib.sorted_months(t["_survey_month"].dropna())
    print(f"Partner tickets: {len(t)} (resolved {len(resolved_t)}); months: {months}")

    counted = resolved_t[resolved_t["_type"].notna()]
    rated = t[t["_survey"].notna() & t["_survey_month"].notna()]

    # Every partner with any activity in the month -- discovered from the
    # data. The sheet hard-codes 138 partners and so loses the rest (Sep'26:
    # 17 partners, 206 complaints).
    by_month = {}
    for m in sorted(set(months) | set(survey_months), key=lib.month_sort_key):
        mc = counted[counted["_month"] == m]
        mr = rated[rated["_survey_month"] == m]
        partners = {}
        for p in sorted(set(mc["_partner"]) | set(mr["_partner"])):
            pc = mc[mc["_partner"] == p]
            pr = mr[mr["_partner"] == p]
            row = lib.count_by(pc, "_type", TYPES)
            for ty in TAT_TYPES:
                row[f"under:{ty}"] = int(pc[(pc["_type"] == ty) & pc["_under"]].shape[0])
            row.update(lib.count_by(pr, "_survey", ["CSAT", "DSAT"]))
            partners[p] = row
        by_month[m] = partners

    owners = lib.load_reference("partner_owner.csv", "partner", "owner")
    # Owner keys are partner names; normalise_key only trims, so match the
    # display name directly (case-insensitively, like VLOOKUP).
    owner_ci = {k.casefold(): v for k, v in owners.items()}
    all_partners = {p for rows in by_month.values() for p in rows}

    output = {
        "types": TYPES,
        "tat_types": TAT_TYPES,
        "tat_days": TAT_DAYS,
        "months": [m for m in by_month],
        "partners": by_month,
        "owners": {p: owner_ci[p.casefold()] for p in all_partners if p.casefold() in owner_ci},
        "latest": resolved_t["_resolved"].max().strftime("%Y-%m-%d") if len(resolved_t) else None,
    }
    lib.write_processed(PROCESSED_PREFIX, output)


if __name__ == "__main__":
    main()
