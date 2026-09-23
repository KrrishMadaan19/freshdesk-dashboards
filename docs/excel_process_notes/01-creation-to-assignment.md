# Dashboard 1: Creation to Assignment Report — formula reference

Source: `AUTO - DASHBOARD` sheet, reading from `RAW DATA June onwards`.

> **Correction (2026-09-23):** the line above is wrong for `AUTO -
> DASHBOARD` specifically — see "Two different raw sheets" below. It reads
> from the legacy `RAW DATA` sheet, not `RAW DATA June onwards`. Only
> `Weekly View` (and therefore the website, which only builds the weekly
> drill-down + a from-scratch monthly rollup off the merged master
> dataset, not off `AUTO - DASHBOARD` directly) reads `RAW DATA June
> onwards`.

## Step 1 — per-ticket calculated columns (computed once per raw data refresh)

Six TAT types, each with an **ageing** column (days, integer) and a **TAT
bucket** column derived from it. `I` = Created time for all of them.

| TAT type | Ageing column | Ageing formula (source date column) | Bucket column |
|---|---|---|---|
| Inward | CREATION TO INWARD AGEING | `BS` (Inward Payment Group Assignment) − `I` | CREATION TO INWARD TAT |
| Spare | CREATION TO SPARE AGEING | `BU` (Spare Group Assignment) − `I`, **see fix below** | CREATION TO SPARE TAT |
| Refund | CREATION TO REFUND AGEING | `BM` (Refund Group Assignment) − `I` | CREATION TO REFUND TAT |
| Replacement | CREATION TO REPLACEMENT AGEING | `BN` (Replacement Group Assignment) − `I` | CREATION TO REPLACEMENT TAT |
| SP | CREATION TO SP AGEING | `DS` (Service Partner Assigned Date Stamp) − `I` | CREATION TO SP TAT |

**Ageing formula pattern** (example, Inward — same pattern for all five):
```
=IF(OR(BS2="",I2=""),"",INT(BS2-I2))
```

**Spare ageing fix (the actual thing you asked for):** for rows where
`PARTNER Y/N = "YES"`, the base date should be `DS` (Service Partner Assigned
Date Stamp) instead of `I` (Created time) — because when a partner is
servicing the ticket, the spare-ageing clock should start from partner
assignment, not ticket creation.

```
PARTNER Y/N = YES:  =IF(OR(BU2="",DS2=""),"",INT(BU2-DS2))
PARTNER Y/N = NO:   =IF(OR(BU2="",I2=""),"",INT(BU2-I2))     (unchanged)
```

**TAT bucket formula pattern** (example, Inward — apply same pattern to all
five, each referencing its OWN row's ageing column):
```
=IF(EE2="","",IF(EE2<0,"",IF(EE2<=0,"0",IF(EE2=1,"1",IF(EE2=2,"2",
  IF(EE2=3,"3",IF(EE2<=5,"4-5",IF(EE2<=7,"6-7","7+"))))))))
```
Buckets: `0, 1, 2, 3, 4-5, 6-7, 7+` (string labels).

> Note: in the source file, the Spare TAT bucket formula references the
> ageing column from the row *below* instead of its own row (an apparent
> drag error — every other TAT bucket column self-references correctly).
> Build this corrected (self-referencing) unless told otherwise.

## Step 2 — supporting per-ticket fields

```
CREATED MONTH:  =TEXT(I2,"MMM'yy")            e.g. "Jan'26"
PARTNER Y/N:    =IF(AG2="","NO","YES")         AG = Partner Name
```

## Step 3 — dashboard matrix (AUTO - DASHBOARD sheet)

Two stacked matrices — **counts** (rows 2–9) and **percentages** (rows 12–19,
= count ÷ row total for that month) — same row/column structure:

- **Columns:** grouped by month (`Dec'25` ... current month), each month
  spanning 7 sub-columns for buckets `0, 1, 2, 3, 4-5, 6-7, 7+`.
- **Rows** (6 TAT types, one is split by partner):
  1. CREATION TO INWARD TAT
  2. SP TO SPARE TAT — PARTNER (YES) — Spare TAT bucket, filtered `PARTNER Y/N = YES`
  3. CREATION TO SPARE TAT — PARTNER (NO) — Spare TAT bucket, filtered `PARTNER Y/N = NO`
  4. CREATION TO REFUND TAT
  5. CREATION TO REPLACEMENT TAT
  6. CREATION TO SP TAT

**Count formula pattern** (Inward, no partner filter):
```
=COUNTIFS('RAW DATA June onwards'!$EF:$EF, <bucket label>,
          'RAW DATA June onwards'!$EO:$EO, <month label>)
```

**Count formula pattern with partner filter** (Spare rows only):
```
=COUNTIFS('RAW DATA June onwards'!$EH:$EH, <bucket label>,
          'RAW DATA June onwards'!$EO:$EO, <month label>,
          'RAW DATA June onwards'!$EP:$EP, "YES"|"NO")
```

**Percentage formula:** each count cell ÷ SUM of that TAT type's 7 bucket
cells for that same month.

## Step 4 — Weekly View (drill-down, same build)

Same 6×7 matrix as Step 3, but for **one selected month** (`Weekly View!$B$1`,
e.g. `"AUG'26"`), broken down by **week** instead of laid out by month.

**Count formula pattern** (Inward, no partner filter):
```
=COUNTIFS('RAW DATA June onwards'!$EF:$EF, <bucket label>,
          'RAW DATA June onwards'!$EO:$EO, <selected month, e.g. B1>,
          'RAW DATA June onwards'!$EQ:$EQ, <week label, e.g. "WK 1">)
```
Same partner-filtered variant as Step 3 applies to the two Spare rows (add
the `$EP:$EP` = "YES"/"NO" criteria).

**CREATED WEEK field** (`EQ` column, computed once per raw data refresh):
```
=" WK "&WEEKNUM(DAY(I2))
```
This is **not** a calendar/ISO week number — `DAY(I2)` extracts just the
day-of-month (1–31), and `WEEKNUM` on that small number effectively buckets
it into `WK 1`–`WK 5` by day-of-month, regardless of which weekday the month
actually starts on. Replicate this exact bucketing (day-of-month → WK1–WK5)
rather than a real calendar week number, so results match the live sheet.
Flag to the business if a true calendar week is actually wanted — this looks
like a deliberate simplification rather than a bug, but worth confirming.

### Weekly View website requirements

- Add a **week drill-down** under the month filter: selecting a month shows
  that month's weekly breakdown (WK1–WK5) instead of — or in addition to —
  the monthly bucket view. A toggle or a "view by week" expand-on-click under
  the selected month works well; doesn't need to be a separate page.
- Same count grid + percentage grid layout as Step 3, just with WK1–WK5
  columns instead of month columns.

## Website version requirements

- **Month filter**: the sheet lays every month out side by side; the website
  should instead let the user pick one month (dropdown or tabs) and show
  that month's 6×7 count grid + percentage grid, defaulting to the most
  recent month present in the data.
- Data source: the merged master dataset in Cloudflare Workers KV (all
  months in one continuous table — no need to replicate the source file's
  split between a legacy `RAW DATA` sheet and `RAW DATA June onwards`).
- Validate output against the real AUTO-DASHBOARD numbers for at least one
  full month before treating this as done.

## Implementation notes (added while building the website version)

These came out of actually reading the source workbook
(`creation-to-assignment/NEW CREATION TO ASSIGNMENT TATs DEC'25 to 11TH
AUG'26.xlsx`) and building `scripts/dashboards/creation_to_assignment.py` —
kept here so the next session doesn't have to re-derive them.

**Column letter → header mapping** (confirmed in `RAW DATA June onwards`):

| Letter | Header | Used as |
|---|---|---|
| A | `Ticket ID` | merge/upsert key |
| I | `Created time` (this workbook snapshot has it truncated to `Created ti` — treated as a one-off artifact, not the real Freshdesk export header) | `I` |
| AG | `Partner Name` | `AG` |
| BM | `Refund Group Assignment` | `BM` |
| BN | `Replacement Group Assignment` | `BN` |
| BS | `Inward Payment Group Assignment` | `BS` |
| BU | `Spare Group Assignment` | `BU` |
| DS | `Service Partner Assigned Date Stamp` | `DS` |
| EG | header is literally misspelled `CREATION TO SPARE AGEGING` in the sheet — irrelevant to the website build since we compute this column ourselves rather than reading it, but flagging in case anyone cross-references the raw sheet directly. |

All 13 computed columns (EE–EQ: the five ageing/TAT pairs, `CREATED MONTH`,
`PARTNER Y/N`, `CREATED WEEK`) exist in the sheet exactly where this doc
guessed — nothing missing.

**`WEEKNUM(DAY(...))` bucket boundaries: the naive "1–7 → WK1" reading in
this doc is correct.** An earlier version of this note "corrected" it to
1–6/7–13/etc, derived from replicating Excel's actual `WEEKNUM` algorithm
against its date epoch — that derivation was wrong. Checked directly
against the live sheet once real multi-day data existed: every ticket
created on day-of-month 7 shows `WK 1`, every one on day 14 shows `WK 2`.
The naive scheme (1–7, 8–14, 15–21, 22–28, 29–31) is what `week_bucket()`
implements now. Lesson: theoretical derivation lost to empirical
observation here — when in doubt, check the live data.

## Validation against real production data (2026-08-24)

The first real upload (183,632 tickets, Dec'25–Aug'26) surfaced two real
bugs in the transform, found by diffing the website's Aug'26-WK1 numbers
against the user's own live reference workbook cell-by-cell:

1. **`Created time` was parsed with `dayfirst=True`.** `Created time` is
   ISO (`YYYY-MM-DD HH:MM:SS`), which the original comment claimed made
   `dayfirst` irrelevant ("year-first is unambiguous either way"). **That
   claim is false.** `pandas.to_datetime` still swaps the month/day
   positions whenever both are ≤12, regardless of which token is
   recognized as the year — e.g. `pd.to_datetime('2026-01-08',
   dayfirst=True)` returns `2026-08-01`. This silently relabeled ~39% of
   tickets into the wrong month (any Created time where both month and
   day are ≤12), which is what caused the original massive discrepancy —
   not just undercounting, but counting a mostly *wrong population* per
   TAT row. Fixed: `Created time` is now parsed with an explicit
   `format="%Y-%m-%d %H:%M:%S"` instead of `dayfirst`.

2. **Vectorized `pd.to_datetime(series, dayfirst=True)` on the DD-MM-YYYY
   assignment columns (BS/BU/BM/BN/DS) silently NaT's individually-valid
   values.** Pandas infers *one* format for an entire column from a
   sample of its values and applies it to all rows — a column that's
   mostly `DD-MM-YYYY HH:MM:SS` will NaT a bare `DD-MM-YYYY` value with no
   time suffix, even though that exact string parses correctly on its
   own. This was the single biggest cause of the `CREATION TO REFUND TAT`
   undercount (NaT'd ~250 of ~790 populated `Refund Group Assignment`
   values in the Aug'26-WK1 slice alone). Fixed via `parse_ddmmyyyy()` in
   the transform script, which parses element-wise instead of as a batch.

After both fixes, Aug'26 WK1 (day-of-month 1–7) compared to the live sheet as:

| Row | Website | Sheet |
|---|---|---|
| CREATION TO INWARD TAT | 28 | 28 |
| SP TO SPARE TAT — PARTNER (YES) | 193 | 50 |
| CREATION TO SPARE TAT — PARTNER (NO) | 64 | 212 |
| CREATION TO REFUND TAT | 790 | 888 |
| CREATION TO REPLACEMENT TAT | 1057 | 1120 |
| CREATION TO SP TAT | 1173 | 1197 |

**The Spare-row mismatch is not a bug** — it's the drag-error fix from
Step 1 of this doc working as documented. The live sheet's own
`CREATION TO SPARE TAT` bucket column has the off-by-one row reference
this doc already flagged, so its Spare counts (50/212) are the *buggy*
numbers; the website's (193/64) are the corrected ones, verified via an
independent ticket-level recompute against the raw data that matched the
website's numbers exactly. Don't try to make the website match the sheet
here.

**The REFUND/REPLACEMENT/SP TAT gap turned out to be a missing
preprocessing step, not a code bug** — see below. Once that was added,
these three rows went to exact-or-off-by-one.

## Raw-data cleanup, folded into the pipeline (2026-08-27)

The Freshdesk raw export isn't used directly — a separate cleanup step
(previously a manual script the user ran in Colab before every upload,
`dashboard_automation.py`) fills in a handful of specific blank
assignment-date columns from business rules and normalizes date
formatting. This is now `scripts/preprocess_raw.py`, run automatically by
`process_upload.py` on every new upload, so the manual step is gone.

**This is what explains the REFUND/REPLACEMENT/SP TAT gap above.** It
looked like a CSV-export completeness issue (~96 tickets with a real
timestamp in the live sheet but blank in the raw CSV) — it wasn't. The
live sheet already had equivalent enrichment logic applied somewhere in
its own history; the website's pipeline was just missing it. Rerunning
the same Aug'26 WK1 comparison with `preprocess_raw.py` in the pipeline:

| Row | Website | Sheet |
|---|---|---|
| CREATION TO INWARD TAT | 28 | 28 |
| CREATION TO REFUND TAT | 889 | 888 |
| CREATION TO REPLACEMENT TAT | 1121 | 1120 |
| CREATION TO SP TAT | 1197 | 1197 |

The 5 rules (see `preprocess_raw.py`'s docstring for the exact conditions):

1. `Created time`, `Resolved time`, `WhatsApp Survey Received`: date-only
   (time component dropped).
2. `Group == "Replacement"` and `Replacement Group Assignment` is blank
   → fill with `Created time`.
3. `UTR` is not blank and `Refund Group Assignment` is blank → fill with
   `Created time`.
4. `Resolved time` is not blank and `Close Looping Group Assignment` is
   blank → fill with `Resolved time`.
5. `Partner Name` is set and not one of `Chat 360` / `Product
   Non-Serviceable` / `Service Denial` (pseudo-partner statuses, not real
   service partners) and `Service Partner Assigned Date Stamp` is blank
   → fill with `Created time`.

**Important: this does NOT touch `Inward Payment Group Assignment` or
`Spare Group Assignment`.** Those two columns aren't covered by any of
the 5 rules, so they still arrive in the master dataset as raw,
inconsistently-formatted `DD-MM-YYYY` text — `creation_to_assignment.py`
still has to parse them defensively (`date_utils.parse_ddmmyyyy`,
element-wise, for the same whole-column-format-inference reason as
before). Every other date column preprocessing does touch (`Created
time`, `Refund`/`Replacement Group Assignment`, `Service Partner Assigned
Date Stamp`) is written back as a clean, unambiguous ISO date-only string
(`YYYY-MM-DD`), so downstream scripts can parse those with
`date_utils.parse_native_timestamp` — no dayfirst juggling needed. See
`scripts/date_utils.py` for both parsers and why each exists.

**A future dashboard that needs `Close Looping Group Assignment`** gets
it pre-cleaned and backfilled for free (rule 4) — no extra work needed
there. Any *other* date column not in the 5 rules will need the same
defensive `parse_ddmmyyyy` treatment Inward/Spare get here, unless it
turns out to already be in clean ISO format (check a raw sample before
assuming either way — that's what caused both of this dashboard's bugs).

Formula logic was unit-tested against synthetic data (bucket boundaries,
partner-conditional spare-ageing base date, month sort order, the 5
cleanup rules including the partner-exclusion case, and a regression test
for the `dayfirst`-on-ISO bug specifically) before this real-data
validation pass. Both together are the basis for treating this dashboard
as validated.

## Re-verification against a fresh workbook (2026-09-23)

The user reported the website's Weekly View "SP TO SPARE TAT — PARTNER
(YES)" numbers still looked wrong and shared a new copy of the live
workbook (`CREATION TO ASSIGNMENT 1ST JAN'26 TO 22ND SEP'26(copy).xlsb`,
177,276 rows in `RAW DATA June onwards`). Re-derived every formula from
scratch (via Excel COM/xlwings, not just cached values) rather than
trusting the conclusion above at face value.

**Two different raw sheets feed two different views, and only one still
has the drag-error bug:**

- `Weekly View` reads from `RAW DATA June onwards`. In *this* sheet, the
  Spare TAT bucket column (`EH`) **self-references correctly on every row
  checked** (rows 2–6, 13, 19, 31, 40, 58, 59, 65, 69, and scattered rows
  through 177,276) — **no drag-error**. The Spare ageing column (`EG`) is
  genuinely partner-conditional exactly as documented (YES → base date
  `DR` Service Partner Assigned Date Stamp; NO → base date `I` Created
  time). This matches `creation_to_assignment.py`'s `_spare_bucket` /
  `ageing_days` / `spare_base` logic **formula-for-formula**.
- `AUTO - DASHBOARD` (the monthly matrix) actually reads from the
  **legacy `RAW DATA` sheet** (135,327 rows), not `RAW DATA June
  onwards` as this doc's opening line claims. In *that* sheet, the
  drag-error is still live and confirmed at rows 100, 5000, 25000,
  50000, 75000, 100000, 125000, and the last row 135327 (`EK135327`
  references `EJ135328` — one row past the end of the data).

**Conclusion: the "website deliberately shows the corrected version, sheet
has a drag-error" story from 2026-08-24 is still true, but only applies to
`AUTO - DASHBOARD` (monthly) vs. the legacy `RAW DATA` sheet.** For the
*weekly* view specifically, the sheet the website should match
(`Weekly View` / `RAW DATA June onwards`) has no bug today — whether it
was fixed after 2026-08-24 or was never affected isn't known. Either way,
if the website's weekly Spare-YES numbers don't match this file's Weekly
View, the formula logic is not the suspect anymore — look at
date-parsing/preprocessing instead (same class of bug this dashboard hit
twice before). Prime suspects: `Spare Group Assignment` (not covered by
any `preprocess_raw.py` rule, still parsed defensively via
`parse_ddmmyyyy`) and `Service Partner Assigned Date Stamp` (covered by
rule 5's Created-time backfill — an assumption never independently
re-verified against a real file's actual populated `DR` values, only
inferred from the aggregate count gap it closed).

**Column letters have drifted and now disagree between the two raw
sheets** (confirmed via this file's header rows — ignore any letter in
Step 1/2/3 above when cross-checking a live file, they're stale):

| Header | `RAW DATA June onwards` (Weekly View's source) | Legacy `RAW DATA` (AUTO-DASHBOARD's source) |
|---|---|---|
| Ticket ID | A | — |
| Group | H | — |
| Created time | I | I |
| Resolved time | K | — |
| Partner Name | AF | AG |
| WhatsApp Survey Received | BE | — |
| Refund Group Assignment | BL | — |
| Replacement Group Assignment | BM | — |
| Close Looping Group Assignment | BQ | — |
| Inward Payment Group Assignment | BR | — |
| Spare Group Assignment | BT | BV |
| UTR | CQ | — |
| Service Partner Assigned Date Stamp | DR | DW |
| Spare ageing / TAT bucket | EG / EH | EJ / EK |
| Created Month | EO | ER |
| Partner Y/N | EP | ES |
| Created Week | EQ | *(no equivalent — legacy sheet has no weekly breakdown)* |

This drift is **not a code risk** — `scripts/columns.py` and every
transform script already key off header *names*, never letters — but it
means this doc's letter references are actively misleading if anyone
manually cross-checks them against a live file. Prefer header names when
adding to this doc going forward.

**Ground truth for a concrete diff**, read directly from `Weekly View`'s
live Excel-computed values (buckets `0, 1, 2, 3, 4-5, 6-7, 7+`):

| Week | SP-Spare YES | SP-Spare NO |
|---|---|---|
| Sep'26 WK1 | 18, 34, 40, 33, 37, 19, 53 | 28, 12, 8, 1, 4, 2, 4 |
| Sep'26 WK2 | 16, 36, 27, 25, 37, 36, 32 | 23, 6, 7, 6, 11, 9, 13 |

Next step: run this file's raw ticket data through the real
`preprocess_raw.py` + `creation_to_assignment.py` pipeline and diff
against the table above — don't treat the formula-logic match above as
proof the website is correct end-to-end; the last two real bugs this
dashboard had were both in date parsing, not formula logic.

## Real bug #3 found and fixed (2026-09-23): SP Assigned time-of-day truncation

Ran the raw ticket data from the fresh workbook (exported via Excel COM,
177,275 rows) through the actual `preprocess_raw.py` + a faithful
reproduction of `creation_to_assignment.py`'s logic, diffed against the
ground-truth table above. Result: **`PARTNER-NO` matched exactly on both
weeks (all 14 numbers); `PARTNER-YES` was off on both weeks**, with the
row *totals* close to the sheet's (e.g. 235 actual vs. 234 expected for
WK1) but individual bucket counts shifted toward higher day-counts —
same population of tickets, wrong bucket per ticket.

**Root cause:** `preprocess_raw.py` truncated `Service Partner Assigned
Date Stamp` to midnight (`.dt.normalize()`), same as every other cleaned
date column. That's correct for columns compared against `Created time`
(also midnight — rule 1) since `INT(midnight_a − midnight_b)` only
depends on calendar days regardless of any truncation. But the Spare-YES
formula compares it against `Spare Group Assignment`, which is **not**
touched by `preprocess_raw.py` at all and keeps its real time-of-day.
Forcing one side of that specific subtraction to midnight while the other
keeps a real time-of-day silently shifts the day-count for any ticket
where the two timestamps' times-of-day don't happen to align — exactly
the "same population, wrong bucket" pattern observed.

Verified with a controlled hypothesis test: keeping `Service Partner
Assigned Date Stamp`'s original time-of-day (falling back to `Created
time`'s midnight value only for genuinely backfilled-blank rows, per
rule 5) produced an **exact match, all 28 numbers**, both weeks:

| Week | Partner | Buckets `0,1,2,3,4-5,6-7,7+` |
|---|---|---|
| Sep'26 WK1 | YES | 18, 34, 40, 33, 37, 19, 53 — exact |
| Sep'26 WK1 | NO | 28, 12, 8, 1, 4, 2, 4 — exact |
| Sep'26 WK2 | YES | 16, 36, 27, 25, 37, 36, 32 — exact |
| Sep'26 WK2 | NO | 23, 6, 7, 6, 11, 9, 13 — exact |

Also verified `CREATION TO SP TAT` (the *other* formula that reads
`Service Partner Assigned Date Stamp`, against `Created time`) is
**byte-for-byte unaffected** by this change (mathematically expected,
since `Created time` is always midnight, so the truncation argument above
applies there too — confirmed empirically as well, not just by proof).

**Fix applied in `scripts/preprocess_raw.py`:** `Service Partner Assigned
Date Stamp` was pulled out of `CUSTOM_DATE_COLS` (which still normalizes
`Refund`/`Replacement`/`Close Looping Group Assignment` — those are only
ever compared against `Created time`, so normalizing them is correct and
unchanged) and is now parsed and written back separately, keeping its
full timestamp (`%Y-%m-%d %H:%M:%S`) instead of being truncated to
`%Y-%m-%d`. Rule 5's backfill logic is unchanged — blank values still get
filled with `Created time`'s (midnight) value.

**This means every website upload prior to this fix undercounted "SP TO
SPARE TAT — PARTNER (YES)" in the wrong buckets** (skewed toward higher
day-counts than reality) for any month it had processed. Re-upload the
current master dataset (or wait for the next scheduled upload) and
re-run `scripts/dashboards/creation_to_assignment.py` to correct
already-published numbers once this fix is deployed.
