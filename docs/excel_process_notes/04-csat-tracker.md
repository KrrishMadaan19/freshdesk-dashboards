# Dashboard 4 — C-SAT Tracker

Source workbook: `C-SAT Tracker-2026 (UPDATED TILL 22ND SEP'26)(COPY).xlsx`
(29 MB, 16 sheets, 6 visible report sheets). Transform:
`scripts/dashboards/csat_tracker.py` → KV `processed:csat-tracker`. Page:
`website/dashboards/csat-tracker/`.

Everything here was read from the workbook's formulas, not from any written
description of it.

## The date that drives everything

Every grid keys off **`WhatsApp Survey Received`** — the day the customer's
rating came back. Not Created time, not Resolved time. The workbook's `DATA`
sheet is pre-filtered to rows that have this date, so a ticket that was never
rated isn't in this report at all. The transform does the same.

## Helper columns on `DATA` — all reproduced row-for-row

| Col | Name | Formula | Reproduced |
|---|---|---|---|
| EE | Month | `TEXT(BE,"MMM'YY")` from WhatsApp Survey Received | 18,887 / 18,887 |
| EF | CSAT Survey | `=BD` (the raw rating) | 18,887 / 18,887 |
| EG | Received | `INT(BE)` | (date-only) |
| EH | C-sat Status | Satisfied, Extremely satisfied → `Positive`; the other three → `Negative` | 18,887 / 18,887 |
| EI | Resolution Mapping | `Resolution Type`, blank → `Not Selected Resolution Type` | 18,887 / 18,887 |
| EJ | WEEK | `"WK "&WEEKNUM(DAY(EG))` = days 1–7 → WK 1, 8–14 → WK 2, … | 18,887 / 18,887 |
| EK | Days | day-of-month ordinal (`1st`, `22nd`) | 18,887 / 18,887 |
| EL | METRO & NON-METRO | `VLOOKUP(Pincode, 'METRO & NON-METRO'!A:F, 4, 0)` | 18,887 / 18,887 |

**"Neither satisfied nor dissatisfied" is Negative.** EH puts it in the
Negative branch and every Negative/DSAT total on every sheet is the bottom
three ratings. That's a business definition, so it's reproduced.

`WEEKNUM(DAY(date))` looks like a bug — it runs WEEKNUM on a day number, which
Excel reads as a date in January 1900 — but it reduces exactly to "days 1–7 are
WK 1", which is what `lib.week_bucket` already does for Dashboards 1 and 5.

## Sheet → site view

| Workbook sheet | Formula shape | Site view | Output key |
|---|---|---|---|
| Dashboard rows 17–29 | `COUNTIFS(EE=month, EF=rating)` | Monthly | `monthly` |
| Dashboard rows 46–55 | `COUNTIFS(EE=month, EL=tier)` | City tier → All | `tier_all` |
| Dashboard rows 59–68 | `COUNTIFS(EE, EL, EH="Positive"/"Negative")` | City tier → CSAT / DSAT | `tier_positive`, `tier_negative` |
| Dashboard rows 72–82 | the above as % of row total | City tier (the % under each count) | computed on the page |
| Weekly Tracker | `COUNTIFS(EF=rating, EJ=week, EE=month)` | Weekly | `weekly` |
| Daily Flow \<month\> | `COUNTIFS(EG=date, EF=rating)` | Daily | `daily` |
| Daily Survey Received Count | `COUNTIF(EG=date)` | Daily → "Received" column | `received_by_day` |
| Resolution Wise | `COUNTIFS(EI=type, EF=rating, EE=month)` | By resolution | `resolution` |
| Daily Tracker-DSAT | `COUNTIFS(EK=day, EE=month, EI=type, EH="Negative")` | DSAT daily | `dsat_daily` |

The hidden `Daily Flow` sheets for earlier months are the same shape as the
visible September one; the site's Daily view covers every month.

### Pincode → city tier

`scripts/reference/pincode_tiers.csv` is the workbook's `METRO & NON-METRO`
sheet reduced to one row per pincode. The sheet has 128,591 rows for only
20,848 distinct pincodes, and **738 pincodes appear with conflicting tiers**
(e.g. `743384` is both `Rest` and `Top 25`). VLOOKUP returns the first match,
so the file keeps the first row per pincode — that's what reproduces EL exactly.
If the lookup sheet is ever corrected, regenerate the file from it the same way.

## Validation

### 1. Logic, on the workbook's own raw rows

`csat_tracker.main()` was run end to end with KV stubbed and `load_master()`
returning the workbook's 18,887 `DATA` rows. Its JSON was diffed against every
visible sheet:

| Sheet | Cells | Mismatches |
|---|---|---|
| Dashboard month × rating, incl. Total / Positive / Negative | 80 | 0 |
| Dashboard tier blocks | 81 | 11 — all explained, see discrepancy 4 |
| Weekly Tracker | 25 | 0 |
| Daily Tracker-DSAT, incl. Grand Total | 558 | 0 |
| Resolution Wise | 85 | 0 |
| Daily Flow Sep'26 | 150 | 0 |
| Daily Survey Received Count (Jan–Sep) | 273 | 0 |
| **Total** | **1,252** | **11, every one accounted for** |

### 2. Pipeline, on the real export in KV

Run on the 186,819-row master dataset (Oct 12 export, zero duplicate Ticket
IDs), compared with the workbook over Jan 1 – Sep 22. **The export has more
surveys than the workbook in every month.** See discrepancy 6 — the export is
the more complete source, so the site's numbers are deliberately not the
workbook's.

## Discrepancies found in the workbook

None of these are reproduced on the site except where noted.

1. **Response-rate denominators are typed in by hand, and two months read the
   wrong sheet.** `RESPONSE TRIGGERED` (Dashboard col J) and `SURVEY TRIGERRED`
   (Daily Flow col L) are typed numbers — nothing in the Freshdesk export
   produces them. On top of that, `J27` (Jul'26) is
   `SUM('Daily Flow Jun''26 '!L4:L33)` and `J28` (Aug'26) is
   `SUM('Daily Flow Jun''26 '!L5:L34)`: both read **June's** sheet, shifted a
   row or two, so July's and August's "responses received %" divide by the
   wrong month's trigger counts. There are also two June sheets, `Daily Flow
   Jun'26` and `Daily Flow Jun'26 ` (trailing space). **The site has no
   response-rate view**, because the export doesn't carry the trigger count.

2. **"OVERALL C-SAT & DSAT %" is not a percentage.** Dashboard `G46:J55`
   repeats the count block's COUNTIFS exactly, with no division, so it shows
   the same counts under a "%" heading. The site shows real shares.

3. **New resolution types disappear from the DSAT sheets.** `Daily
   Tracker-DSAT` and `Resolution Wise` both hard-code 17 resolution types as
   rows. Sep'26 has 7 DSATs resolved as `Issue Resolved – Accessories Only`
   (a type not on the list, and spelled with an en dash where every other type
   uses a hyphen). They match no row, so they vanish, and the DSAT `GRAND
   TOTAL` (`=SUM(B3:B19)`) reads **132 for a month with 139 negatives**. The
   site discovers rows from the data, so a new type can't drop out.

4. **The "all responses" tier block counts surveys with no rating.** Dashboard
   rows 47–55 filter on month and tier only, so the 24 surveys that came back
   with a date but no rating are included — while the CSAT and DSAT tier
   blocks (rows 60–68) can't include them. The overall count therefore isn't
   CSAT + DSAT. This accounts for all 11 tier mismatches in the validation
   above, cell for cell (e.g. Jan'26 Top 25: 5 unrated → site 593, workbook
   598). The site counts rated responses only, so the three tier blocks agree
   with each other. Unrated surveys appear in the Daily view's "Received"
   column, matching Daily Survey Received Count.

5. **Tier columns never add up to the month.** Pincodes that aren't in the
   lookup table — or whose first entry is the literal text `#N/A`, true of
   1,167 pincodes — get no tier, and the workbook has no column for them.
   Sep'26: 31 responses unaccounted for. The site adds an `Unmapped` column;
   the three real tiers still match the workbook cell for cell.

6. **The workbook misses ratings that arrive after a ticket's paste day — and
   that hides DSAT.** The export has 680 rated tickets (Jan 1 – Sep 22) that
   the workbook never picked up. Most were rated a day after resolution
   (median +1 day), whereas 78% of the workbook's rows were rated the same
   day they were resolved — consistent with the daily paste capturing a
   ticket once and never revisiting it. Late ratings skew negative, so the
   workbook understates DSAT in every month:

   | Month | Workbook DSAT % | Export DSAT % | Gap (pts) |
   |---|---|---|---|
   | Jan'26 | 19.2 | 20.5 | +1.3 |
   | Feb'26 | 15.1 | 15.9 | +0.8 |
   | Mar'26 | 15.6 | 16.2 | +0.6 |
   | Apr'26 | 16.8 | 17.6 | +0.7 |
   | May'26 | 18.2 | 19.1 | +0.8 |
   | Jun'26 | 16.4 | 17.3 | +0.9 |
   | Jul'26 | 18.7 | 19.3 | +0.6 |
   | Aug'26 | 17.3 | 17.5 | +0.2 |
   | Sep'26 (1–22) | 12.6 | 15.8 | **+3.3** |

   In September the workbook is missing 92 of 231 negative ratings — 40%.

7. **Re-surveyed tickets: workbook keeps both ratings, the export keeps the
   latest.** Four Sep'26 tickets were rated twice (a DSAT after a replacement,
   then a CSAT after a refund). The workbook's appended DATA holds both rows;
   a Freshdesk export holds one `CSAT Survey` value per ticket, so the site
   sees only the second. This is a limit of the export, not a transform
   choice. It's small (4 tickets in ~9 months of data), but it always runs in
   the same direction: a DSAT that's later fixed disappears. Keeping it would
   need a response log that persists across uploads.

8. **Oct'25 and Nov'25 are pasted values; Dec'25 is all zeros.** The
   Dashboard's first two months aren't formulas, and Dec'25 has no rows in
   DATA, so its percentages are `#DIV/0!`. The site starts at the first month
   with data.

## What the site adds

- `Unmapped` tier column (discrepancy 5).
- A `Received` column on the Daily view, so the unrated surveys are visible
  rather than silently in or out of a total (discrepancy 4).
- Every resolution type with a rating, not a fixed 17 (discrepancy 3).
- Any rating text outside the five known ones is reported in the footnote
  instead of dropping out unseen.
