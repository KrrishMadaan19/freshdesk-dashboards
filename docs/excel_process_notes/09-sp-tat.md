# Dashboard 9 — SP TAT Performance (step-wise)

Source workbook: `SP TAT PERFORMANCE DASHBOARD STEP-WISE DEC'25 TO 22ND
SEP'26(copy).xlsx` — RAW 9,241 rows. Transform: `scripts/dashboards/sp_tat.py`
→ KV `processed:sp-tat`. Page: `website/dashboards/sp-tat/`.

## Scope

On-site service-partner closures: Resolution Type is *Issue Resolved – Without
Spare*, *– With Spare* or *– Accessories Only*, and the ticket has a real
Partner Name (not one of preprocess_raw's pseudo-partners). Against the Oct-12
export that selects 9,197 tickets: 9,193 in the workbook, 4 extra, 48 missed
(resolved Sep 23, a day past the comparison window).

Resolution types are matched on letters and digits only. Freshdesk spells
"Accessories Only" with an en dash; the workbook's copy has been through an
encoding round-trip (`Issue Resolved ‚Äì Accessories Only`). Punctuation
can't be trusted, the words can.

## Helper columns on RAW — all reproduced row-for-row

| Col | Name | Formula | Site |
|---|---|---|---|
| EE | Spare Y/N | any of Spare Name 1–5 filled → SPARE-YES | same |
| EG/EH | Case creation → SP assignment | `INT(SP Assigned − Created)` | same (Created is midnight, so INT = calendar days) |
| EI/EJ | Case creation → Spare assigned | `INT(Spare Group Assignment − Created)` | same |
| EK/EL | SP → Spare assigned | `INT(Spare GA − SP Assigned)`, negatives dropped | same (both real timestamps — elapsed days kept) |
| EM/EN | "Spare delivered → SP visit done" | `INT(Resolved − Inward Payment Group Assignment)` | calendar days |
| EO/EP | SP Assigned → close looping | `INT(Resolved − SP Assigned)`, negatives dropped | calendar days |
| EQ/ER | Case creation → resolved | `INT(Resolved − Created)` | same |
| ES/ET | CSAT/DSAT, survey month | as the other TAT workbooks | same |
| EU/EV | Correct City / State | typed; pincode lookup | `pincode_city_state.csv` |

## Validation

`sp_tat.main()` on the workbook's 9,241 RAW rows:

- **AUTO-DASHBOARD, 360 cells: 278 exact, 78 the truncation fix
  (discrepancy 2), 4 June cells copied from May (discrepancy 1), 0 unexplained.**
- **SP SURVEY ANALYSIS, 738 cells across 9 months: 738 exact.**

The AUTO-DASHBOARD's counts are typed numbers, not formulas, so they were
first matched against RAW's own helper columns: every month equals RAW
exactly except June.

## Discrepancies in the workbook

1. **June's "case creation → SP assignment" row (no spare) was copied from
   May.** Four of its five cells are May's numbers (56, 26, 42, 124); RAW gives
   31, 24, 13, 101. The whole count block is typed rather than formula-driven,
   which is how a copy like this survives.

2. **SP Assigned → close looping drops same-day closures.** `INT(Resolved −
   SP Assigned)` truncates only one side (Resolved is date-only, the
   assignment has a time), so a ticket resolved the day its partner was
   assigned comes out −1 — and the formula's negative guard then drops it.
   203 such tickets vanish from the measure; 2,587 more sit a band too fast.
   The site uses calendar days: same-day is 0.
   "Spare delivered → SP visit done" has the same one-sided truncation (no
   guard, so nothing drops — the band just shifts).

3. **The partner survey list is typed in and has gone stale.** Its "Overall"
   row sums 41 listed partners. Fine through March; by Aug'26 it shows 52 of
   245 partner CSATs and 26 of 68 DSATs, and Sep'26 shows 5 of 34 DSATs (15%).
   The site lists every partner.

4. **STATE-WISE's header cell reads `#VALUE!`.**

5. **The hidden `DASHBOARD` sheet is a stale pivot** (Dec'25 – 8 Feb'26) and
   isn't part of the report.

## Open question for the business

"Spare delivered → SP visit done" is measured from the **Inward Payment Group
Assignment** — set on only ~190 of 9,241 tickets, so the row is nearly empty.
If a different date marks the spare's delivery (e.g. Spare Return Group
Assignment), it's a one-column change in the transform.
