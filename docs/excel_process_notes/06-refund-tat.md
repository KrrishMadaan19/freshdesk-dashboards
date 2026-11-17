# Dashboard 6 — Refund TAT Performance

Source workbook: `REFUND TAT PERFORMANCE DASHBOARD APR'26'25 TO 22ND SEP'26
(AUTOMATED)(copy).xlsx` — 36 MB; RAW claims 889,092 rows but holds 17,675
(the used range is inflated). Transform: `scripts/dashboards/refund_tat.py` →
KV `processed:refund-tat`. Page: `website/dashboards/refund-tat/`.

## Helper columns on RAW

| Col | Name | Formula |
|---|---|---|
| EE | Resolved month | `TEXT(Resolved time,"MMM'YY")` |
| EG/EH | Case creation → Refund bucket | `INT(Refund Group Assignment − Created time)`, banded |
| EI/EJ | "Refund bucket movement to close looping" | `INT(Resolved time − Refund Group Assignment)`, banded |
| EK/EL | Case creation → closure | `INT(Resolved time − Created time)`, banded |
| EM | Serviceable / NON serviceable | `VLOOKUP(ERP Model, 'serviable and non serviceable'!A:C, 3, 0)` |
| EN | Csat/Dsat | Satisfied / Extremely Satisfied → CSAT, any other rating → DSAT |
| EO | Survey Received Month | `TEXT(WhatsApp Survey Received,"MMM'YY")` |
| EP/EQ | Correct City / State | typed values; reproduce as pincode → `City 1` / `State name` from `city & State` |
| ER/ES | Overall Resolution TAT | identical to EK/EL |

Bands everywhere: `IF(x<=1,"0-1",IF(x<=3,"2-3",IF(x<=5,"4-5",IF(x<=7,"6-7","7+"))))`
— `lib.tat_band`, shared with Replacement and SP TAT.

Lookup tables copied into `scripts/reference/`, first row per key kept (VLOOKUP's
rule): `erp_model_serviceability.csv` (5,334 rows → 3,677 models; 14 models are
listed as both classes) and `pincode_city_state.csv` (21,503 → 21,490 pincodes).

## Sheet → site view

| Workbook | Site |
|---|---|
| AUTO-DASHBOARD: class × resolved month × 3 TATs × bands | TAT (measure + class pickers) |
| AUTO-DASHBOARD rows 28–38: survey month × CSAT/DSAT | Survey |
| STATE-WISE / CITY-WISE: overall TAT bands + CSAT/DSAT for one month | State / City (any month) |
| CATEGORY-WISE: ERP Category / Sub Category / class × month | Category |

## Validation

`refund_tat.main()` run end to end on the workbook's 17,675 RAW rows, every
sheet diffed: **4,680 cells, 3,587 exact, 1,093 explained cell-for-cell, 0
unexplained.** Every explained cell traces to one of discrepancies 1, 2 or 4
below.

## Discrepancies in the workbook

1. **"Refund bucket → close looping" is a day short on a quarter of tickets.**
   It's `INT(Resolved − Refund Group Assignment)` where Resolved is date-only
   and the assignment keeps its time-of-day, so any assignment after midnight
   loses a day. 4,477 tickets (25.4%) sit one band too fast; the workbook's
   "0-1" band holds 9,858 where calendar days give 6,673. The workbook's three
   ageings add up (creation→refund + refund→resolved = creation→resolved) on
   only 23.7% of rows. The site uses calendar days on both sides, so they add
   up on all of them. The label is also wrong — the Close Looping Group
   Assignment column isn't involved; the site calls it "Refund bucket →
   Resolved".

2. **City and State stop being filled in partway through August.** They're
   typed values, not formulas. 1,473 of August's 3,553 refunds (41%) are
   `#N/A`, against a few dozen in any earlier month — and STATE-WISE and
   CITY-WISE are showing August. Where filled, they agree with the pincode
   lookup on every row. The site looks every ticket up.

3. **CATEGORY-WISE reads the wrong columns.** Its "ERP Category" block counts
   the ERP Sub Category column (DJ) and its "ERP Sub Category" block counts ERP
   Model (DK) — written for an older export with one column fewer before them.
   So Jan'26's category total is 60 for a month with 931 refunds. The site
   reads the columns by name.

4. **54 Refund Group Assignments have the year 20026** (`13-07-20026`), all
   July tickets — a hand edit; no Freshdesk export can produce a five-digit
   year. Excel can't subtract text, so they fall out of the two refund ageings
   but stay in creation→resolved and the survey block.

5. **The two classes never add up to the month.** 887 tickets have an ERP Model
   the serviceability table doesn't list, and the workbook has no row for them.
   The site adds `Unmapped`. The workbook's model lookup also disagrees with
   the export's own `Product Classification` field on 1,371 tickets — the site
   follows the workbook (lookup), since that's the deliberate definition.

6. **AUTO-DASHBOARD has no SERVICEABLE Sep'26 row** (NON-SERVICEABLE does).

7. **The row set is an accident of paste timing.** RAW only gets tickets that
   are `Resolved` when pasted. Against the Oct-12 export, 1,024 tickets with a
   Refund Group Assignment, resolved Jan 2 – Sep 22, are missing: 804 `Closed`,
   575 "Request Cancelled – Customer did not share the required details"
   (cancellations close directly and skip `Resolved`), and 134 genuine "Issue
   Resolved – With Refund" missed like late ratings in C-SAT. Most land in
   Aug–Sep (419 and 278). **The site counts every ticket that entered the
   refund bucket** — see the open question below.

## Open question for the business

Should cancelled refund requests count in refund TAT? They entered the refund
bucket, but most close because the customer never responded, so their
end-to-end time measures waiting on the customer rather than the refund team.
Excluding them is a one-line change to `SCOPE_COLUMN`'s filter in the
transform.
