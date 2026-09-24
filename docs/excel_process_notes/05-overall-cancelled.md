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
- **No day-1 cutoff** (decided 2026-09-24). An earlier build excluded rows
  resolved on the current date, mirroring the business's "select day-1 date"
  step. The user asked for every ticket in the upload to be counted instead,
  so the cutoff was removed; the most recent day is therefore partial until
  that day ends. The page states the latest resolved date it holds.
- **Tickets with no `Resolved time` are excluded, and the count is shown on
  the page.** Every view buckets by resolved month/week/day, so a ticket
  without that date has nowhere to sit. In the 2026-09-24 upload this was
  3,351 tickets — and they are overwhelmingly *not* cancellations: 3,317 are
  still in progress (`Pending` 2,260, `Customer Responded` 822, `Open` 205,
  `Reopened` 19, `SP Update` 11) and simply have not been resolved yet. Only
  34 are `Closed`, of which 24 carry a cancellation type — those 24 are a
  genuine Freshdesk data-quality gap (closed and cancelled, but the resolved
  timestamp was never written). Surfacing the count keeps this visible
  instead of silently dropping rows.

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

### Reconciling the website against the workbook

The two will not agree exactly, for reasons that are fully accounted for:

| | Rows |
|---|---|
| Workbook `RAW` sheet | 87,972 |
| − duplicate re-resolution rows (September only) | −618 |
| = unique tickets in the workbook | 87,354 |
| Website, from the 2026-09-24 export | 87,252 |
| Unexplained remainder | 102 (0.1%) |

**The 618 duplicates matter most.** The workbook is appended to daily, so a
ticket that is reopened and re-resolved gains a row each time — one ticket
in this file appears 8 times, resolved on 5, 7, 8, 9, 10, 12, 16 and 19 Sep
with the reason alternating. Jan–Aug were bulk historical loads and contain
zero duplicates; only the month being actively appended to is affected.

So **the workbook counts resolution events; the website counts tickets.** A
Freshdesk export carries only each ticket's current state, so event history
cannot be reconstructed from it — this is a limitation of the input, not a
choice. Expect the website's figure for the in-progress month to read lower.

The residual ~102 is snapshot drift: the workbook was saved 22 Sep, the
export pulled 24 Sep, and tickets change in between. Re-exporting both on
the same day removes it. Note `Jan'26`–`Apr'26` match the workbook
*exactly* (13,554 / 8,607 / 8,088 / 9,132), which is what confirms the
drift is age rather than logic.
