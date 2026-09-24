# Dashboard 5: Overall Cancelled Tickets Report — formula reference

Source workbook: `OVERALL CANCELLED TICKETS REPORT (UPDATED TILL 22ND SEP'26).xlsb`
Reverse-engineered 2026-09-24 via Excel COM (formulas, not cached values).

Three sheets, all reading the same `RAW` sheet directly via `COUNTIFS` — no
pivot tables, no external links, no VBA.

| Sheet | Rows | Columns |
|---|---|---|
| `OVERALL - DASHBOARD` (note the spaces around the dash) | 15 resolution types | months |
| `WEEKLY` | same 15 | `WK 1`–`WK 5`, for one month |
| `DAILY TREND` | same 15 | `1st`–`31st`, for one month |

## Step 1 — the only two raw columns this dashboard reads

| Header name | Letter in this workbook | Role |
|---|---|---|
| `Resolved time` | `K` | the ONLY date driving all three sheets |
| `Resolution Type` | `BC` | the category dimension |

**`Created time` is never referenced by any formula here.** Every other
column present in `RAW` (`Ticket ID`, `City`, `State`, `Product`, `ERP
Category`, …) is carried along unused — available if drill-downs are
wanted later.

Column letters are recorded for auditability only. Everything is addressed
by header name (see `scripts/columns.py`) because the export's column
positions shift as fields are added.

## Step 2 — helper columns (computed in the workbook, reproduced in code)

| Header (verbatim, casing is inconsistent in the sheet) | Formula |
|---|---|
| `RESOLVED MONTH` | `=TEXT(K2,"mmm'yy")` |
| `DAYS` | `=DAY(K2)&` ordinal suffix (`1st`, `2nd`, `3rd`, `4th`…) |
| `resolved week` | `="WK "&WEEKNUM(DAY(K2))` |
| `resolution type2` | `=IF(BC2="","RESOLUTION TYPE NOT SELECTED",(BC2))` |

All four self-reference correctly on every row — no drag errors here
(unlike Dashboard 1's source workbook).

**Week bucketing is identical to Dashboard 1's** — the same
`WEEKNUM(DAY(...))` trick, which buckets by day-of-month rather than
calendar week. Verified empirically across all 87,972 rows, zero
exceptions:

```
1–7 → WK 1 · 8–14 → WK 2 · 15–21 → WK 3 · 22–28 → WK 4 · 29–31 → WK 5
```

`creation_to_assignment.py`'s `week_bucket()` is reused verbatim, just fed
`Resolved time`'s day instead of `Created time`'s.

## Step 3 — the 15 category rows

In sheet order:

```
Auto Closed
Blanks                                                      <- dead, see quirks
Forwarded to relevant team
Request Cancelled - Customer did not approve charges
Request Cancelled - Customer did not provide a visit appointment
Request Cancelled - Customer did not respond
Request Cancelled - Customer did not share the required details
Request Cancelled - Other brand product
Request Cancelled - Product working fine
Request Cancelled - Self-Resolved
Request Cancelled -Service denial/local repair suggested     <- no space after the dash
Resolution type not selected
Spam/ Junk                                                   <- space after the slash
FD automation issue
Test
```

The odd spacing is real and matches the data byte-for-byte — do not
"tidy" it.

## Step 4 — count formulas

All three sheets are plain `COUNTIFS` over the helper columns:

```
OVERALL - DASHBOARD  =COUNTIFS(RAW!$EE:$EE, <month label>, RAW!$EH:$EH, <row label>)
WEEKLY               =COUNTIFS(RAW!$EH:$EH, <row label>, RAW!$EG:$EG, <WK n>, RAW!$EE:$EE, <WEEKLY!A1>)
DAILY TREND          =COUNTIFS(RAW!$EF:$EF, <ordinal day>, RAW!$EE:$EE, <DAILY TREND!A1>, RAW!$EH:$EH, <row label>)
```

By name: count rows where `RESOLVED MONTH` / `resolved week` / `DAYS`
match the column label and `resolution type2` matches the row label.

**Case-sensitivity trap:** `COUNTIFS` is case-insensitive, pandas `==` is
not. The sheet's row label is `Resolution type not selected` while the
helper column emits `RESOLUTION TYPE NOT SELECTED`; the month headers are
typed `AUG'26` while `RESOLVED MONTH` produces `Aug'26`. Match
case-insensitively or these silently count zero.

## Step 5 — `RAW` is a PRE-FILTERED subset (must be reproduced)

`RAW` holds 87,972 rows against 173,884 in an unfiltered export of the
same date range. It contains only the 13 cancellation types plus blanks —
confirmed by diffing against the Dashboard 1 workbook, which covers the
identical range unfiltered and has 26 distinct `Resolution Type` values.

So the manual prep step is: **filter to `Resolution Type` ∈ the 13 values,
or blank**, then paste into `RAW`.

Implemented as an explicit **allow-list**, deliberately not a deny-list: a
new cancellation type added in Freshdesk would otherwise pass the filter,
match no dashboard row, and vanish silently from both the grid and the
totals. With an allow-list it shows up as absent instead.

## Website version

- **Overall view** — rows = the 15 categories, columns = every month in the
  data, matching the sheet's monthly-trend layout.
- **Weekly / Daily views** — driven by a single month picker, which replaces
  the sheet's two independently hand-typed `A1` month selectors (`WEEKLY!A1`
  and `DAILY TREND!A1` can silently disagree; one picker can't).
- **Day-1 rule** — the dashboard reflects data up to *yesterday*. Rows whose
  `Resolved time` falls on or after the processing date are excluded, so the
  most recent day shown is always complete rather than a partial snapshot.
  This is the automated equivalent of the business's "select day-1 date from
  Resolved date" step.

## Quirks & bugs in the source workbook

**BUG 1 — Grand Total column stops at July.** `L3` is `=SUM(B3:I3)`,
covering `Dec'25`–`Jul'26` and omitting `Aug'26`/`Sep'26`. Every value in
the total column is understated; `FD automation issue` and `Test` display
`0` despite 376 and 92 tickets.

*Website behaviour: NOT reproduced.* The formula is frozen at 8 columns —
it omits two months today and would omit three next month, so it cannot
carry forward on a dashboard that rebuilds from new data. The website sums
every month present.

**BUG 2 — Grand Total row stops at row 15.** `=SUM(B3:B15)` omits
`FD automation issue` (row 16) and `Test` (row 17), identically on all
three sheets — both rows were clearly appended after the totals were
written. `Aug'26` shows 10,829 against a true 11,202; `Sep'26` shows 6,269
against 6,364.

*Website behaviour: REPRODUCED, at the user's request (2026-09-24), so the
website and the workbook agree cell-for-cell.* Unlike BUG 1 this one is
deterministic — "exclude these two named categories from the total" — so it
carries forward cleanly. Revisit if the sheet is ever fixed.

**BUG 3 — the `Blanks` row is dead.** Always 0; `resolution type2` never
emits the string `Blanks`. Misleading, because it suggests there are no
blank resolution types when in fact there are 26,217 — they sit in
`Resolution type not selected`. *Website behaviour: dropped.*

**Quirk — `Dec'25` column is empty.** Data starts `Jan'26`. Vestigial, and
hidden in the sheet.

**Quirk — hidden columns.** `OVERALL - DASHBOARD` B:G (`Dec'25`–`May'26`)
are hidden but hold live values.

**Quirk — blank `Resolved time` would land in `Jan'00`.** `TEXT("","mmm'yy")`
returns `Jan'00`, which would silently disappear from every grid. There are
zero blanks in this file, but the transform excludes unparseable dates
explicitly rather than relying on that.

## Validation

Ground truth captured from the workbook's own live Excel-computed values,
and independently cross-checked by recomputing the grids from the 87,972
raw rows — exact match on all 75 `WEEKLY` cells and all 30
`Aug'26`+`Sep'26` `OVERALL` cells.

`Aug'26` (the most recent complete month) per category:

| Category | Aug'26 |
|---|---|
| Auto Closed | 19 |
| Forwarded to relevant team | 23 |
| RC - Customer did not approve charges | 167 |
| RC - Customer did not provide a visit appointment | 198 |
| RC - Customer did not respond | 994 |
| RC - Customer did not share the required details | 2452 |
| RC - Other brand product | 94 |
| RC - Product working fine | 18 |
| RC - Self-Resolved | 375 |
| RC -Service denial/local repair suggested | 1220 |
| Resolution type not selected | 4253 |
| Spam/ Junk | 1016 |
| FD automation issue | 372 |
| Test | 1 |
| **Grand Total (as the sheet computes it, BUG 2)** | **10829** |

`Sep'26` weekly grid (`WEEKLY!A1 = Sep'26`), `WK 1`–`WK 5`:

| Category | WK 1 | WK 2 | WK 3 | WK 4 | WK 5 |
|---|---|---|---|---|---|
| Auto Closed | 4 | 2 | 0 | 0 | 0 |
| Forwarded to relevant team | 1 | 2 | 0 | 0 | 0 |
| RC - Customer did not approve charges | 45 | 47 | 53 | 12 | 0 |
| RC - Customer did not provide a visit appointment | 56 | 48 | 73 | 7 | 0 |
| RC - Customer did not respond | 235 | 242 | 306 | 55 | 0 |
| RC - Customer did not share the required details | 595 | 535 | 572 | 65 | 0 |
| RC - Other brand product | 26 | 27 | 23 | 3 | 0 |
| RC - Product working fine | 1 | 1 | 2 | 1 | 0 |
| RC - Self-Resolved | 104 | 60 | 75 | 12 | 0 |
| RC -Service denial/local repair suggested | 282 | 263 | 270 | 58 | 0 |
| Resolution type not selected | 633 | 687 | 678 | 95 | 0 |
| Spam/ Junk | 5 | 2 | 5 | 1 | 0 |
| FD automation issue | 4 | 0 | 0 | 0 | 0 |
| Test | 57 | 23 | 11 | 0 | 0 |
| **Grand Total (BUG 2)** | **1987** | **1916** | **2057** | **309** | **0** |

Note the workbook's data ends 22 Sep, so `Sep'26` is partial there and
`WK 4` holds only day 22. A live export covering more of September will
legitimately exceed these numbers — validate against `Aug'26`, which is
complete in both.
