# Dashboard 8 — Service Partner Closure Bifurcation

Source workbook: `SERVICE PARTNER CLOSURE BIFURCATION REPORT (UPDATED TILL
22ND SEP'26)(copy).xlsb` — RAW claims 178,188 rows, holds 26,635. Transform:
`scripts/dashboards/sp_closure_bifurcation.py` → KV
`processed:sp-closure-bifurcation`. Page: `website/dashboards/sp-closure-bifurcation/`.

## What it is

One scorecard per resolved month (the sheet shows one month, `A1`): for each
service partner, its tickets by resolution type, how many on-site jobs closed
within TAT, and its CSAT/DSAT.

## Helper columns on RAW — all reproduced row-for-row except TAT

| Col | Name | Formula |
|---|---|---|
| EE | PARTNER NAME | `=AF` (Partner Name) |
| EF / EG | RESOLVED MONTH / WEEK | from Resolved time (week = day-of-month band) |
| EH / EI | SURVEY RECEIVED MONTH / WEEK | from WhatsApp Survey Received |
| EJ | CSAT / DSAT | Satisfied, Extremely satisfied → CSAT; any other rating → DSAT |
| EK | RESOLUTION TYPE 2 | Resolution Type, blank → `RESOLUTION TYPE BLANK` |
| EL | SERVICE PARTNER ASSIGNED DATE | `INT(IF(SP Assigned Date Stamp="", Created time, SP Assigned Date Stamp))` |
| EM | TYPE 3 | Without Spare / With Spare / Installation, else blank |
| EN | AGEING | `INT(Resolved − EL)` for the three on-site types |
| EO | TAT | `IF(EN<=3,"UNDER TAT","OUT TAT")` |

EN subtracts two date-only values, so unlike Refund there's no one-side
truncation here.

## DASHBOARD columns

Total complaint = Without Spare + With Spare + Installation + With Refund +
With Replacement (only these five resolution types count). UNDER TAT and TAT %
for the three on-site types. CSAT / DSAT / CSAT % from surveys received in the
month (any resolution type), matched on Partner Name.

## Scope

Tickets with a `Partner Name`, excluding the pseudo-partners `preprocess_raw.py`
already excludes (Chat 360 / Product Non-Serviceable / Service Denial). Against
the Oct-12 export this selects the workbook's RAW exactly — 26,477 of its
tickets, zero extra; the remaining 158 were resolved Sep 23, a day past the
comparison window. Unlike Refund and C-SAT, this workbook's row set is complete.

Account owners come from the DASHBOARD's column B, copied to
`scripts/reference/partner_owner.csv` (17 partners).

## Validation

`sp_closure_bifurcation.main()` on the workbook's 26,635 RAW rows, every
partner cell on the Sep'26 sheet diffed: **1,507 cells, 1,494 exact, 13
explained (discrepancy 3), 0 unexplained.**

## Discrepancies in the workbook

1. **GRAND TOTAL only covers the first 35 partners.** Every total is
   `=SUM(C4:C38)` while the partner list runs to row 140. Sep'26 total
   complaints read 561; the listed partners hold 1,409; the real figure is
   1,615. Every grand-total TAT % is computed from the partial sums.

2. **The partner list is typed in, and misses partners.** 138 fixed rows; in
   Sep'26, 17 partners with 206 complaints (12.8%) aren't on it — including
   Easy Solution Services with 129. The site lists every partner with activity
   in the month.

3. **458 tickets carry a stale 7-day TAT.** The TAT formula is `<=3`, but in
   scattered blocks of rows the cell holds UNDER TAT for ageing 4–7 —
   evidently values left over from an older `<=7` formula. It isn't a rule:
   within every resolution type and every month, tickets at the same ageing
   are split between UNDER and OUT (With Spare at 4–7 days: 347 UNDER, 270
   OUT). The site applies the current `<=3` everywhere. Sep'26 is affected on
   13 cells.

4. **Two conflicting owner lists.** Column B and the hidden `Sheet3` disagree
   on Easy care solution (Shivam vs Vivek), SK Services – Mumbai (Shivam vs
   Vivek), Yash Films (Ashish vs Yash Gupta), MZI (Jasminder vs Faraz) and
   Homeserve (Ashish vs Faraz). Only 2 cells actually use Sheet3 (RV Solution,
   Maars-e-Services). The site uses column B as displayed; 121 of the 138
   listed partners have no owner at all.

5. **One ticket was resolved before its partner was assigned** (negative
   ageing) and counts as UNDER TAT. Left as is — it's in the data.

## Open question for the business

**Should With Spare have a longer TAT than 3 days?** On Nov'26 data only 8.1%
of With Spare jobs close within 3 days, against ~47% for Without Spare and
Installation — waiting for the part dominates. The stale 7-day rows suggest
someone once intended 7 days for these. `TAT_DAYS` is one constant in the
transform; making it per-type is a two-line change.
