# Dashboard 3: Daily Pending and Closure — formula reference

Source workbook: `Daily Pending and Closure Dashboard 2026(Copy).xlsb` (169 MB)
Reverse-engineered 2026-10-01 via Excel COM (formulas, not cached values).

14 sheets. Unlike Dashboards 1 and 5 — which are one grid each over one RAW
sheet — this workbook keeps **one sheet per month**, each a stack of seven
blocks shaped "categories down, days-of-month across", with an MTD total and a
per-day average in columns B and C.

| Sheet | Rows × cols | What it is |
|---|---|---|
| `JAN'26` … `SEP'26` (9 sheets) | 33 × 95–408 | one month each |
| `RAW DATA June onwards` | 177,276 × 148 | the raw export the live sheet reads |
| `RAW-DATA Jan-May` | 134,718 × 151 | an older raw export, **different schema** |
| `CAT-WISE INFLOW` | 2,653 × 13 | a pivot, ERP-category inflow |
| `CATEGORY-WISE` | 27 × 13 (from `A6`) | ERP category × month |
| `PIVOT` | 19 × 2 | the analyst's scratch pivot for one day |

`CAT-WISE INFLOW` and `CATEGORY-WISE` are not referenced by any month sheet's
formulas and are not part of this dashboard.

## The two things to understand before trusting this workbook

### 1. Only `SEP'26` is live

Every other month sheet is **pasted values with no formulas at all** — and each
was frozen with whatever row set existed at the time:

| Sheet | Blocks | Service partners listed | Inflow sources |
|---|---|---|---|
| `JAN'26` | 6 (no bucket-wise closure) | 16 | 5 |
| `AUG'26` | 7 | 51 | 5 |
| `SEP'26` | 7 | **161** | **11** |

Group labels drift too — `JAN'26` has `QP_Inbound`, `Non Serviceable` and
`close looping`; `SEP'26` has none of those and adds `B2B Corporate`,
`Clove Dental Free Coupon Registration`, `EBO Support` and others.

So `SEP'26`'s formulas are the only specification that exists. The
implementation applies them to **every** month and **discovers row labels from
the data** rather than freezing a list, which is why new groups, sources and
partners appear on their own.

**Consequence, stated plainly:** this dashboard's historical months will not
match the workbook's historical sheets cell-for-cell. They cannot — those
sheets were each built from a different row set, by hand, at a different time.
What they will be is internally consistent, which the workbook's are not.

### 2. The two RAW sheets put different fields at the same column letters

They diverge from column `Z` onward. Same letter, different field:

| Letter | `RAW DATA June onwards` | `RAW-DATA Jan-May` |
|---|---|---|
| `AF` | `Partner Name` | `Service` |
| `AL` | `Product Classification` | `Pickup Type` |
| `AX` | `Pickup Initiated Date` | `Order ID` |
| `BO` | `Escalation Group Assignment` | `Replacement Case Return Assignment` |
| `BQ` | `Close Looping Group Assignment` | `Fraud Group Assignment` |
| `BR` | `Inward Payment Group Assignment` | `Fraud Case Return Assignment` |
| `BT` | `Spare Group Assignment` | `Inward Payment Group Assignment` |
| `DR` | `Service Partner Assigned Date Stamp` | `Service Cancellation Reasons` |
| `EF` | `RESOLVED DATE` | `Email` |

Reading this dashboard by cell address would count `Email` as a resolved date
and `Service` as a partner name for half the year. Every column is therefore
resolved by header name through `scripts/columns.py`. Letters are recorded
below for auditability only.

## Step 1 — helper columns on `RAW DATA June onwards`

The month sheets' `COUNTIFS` never touch the source columns directly; they read
these helpers, which strip the time component so a whole day matches as one
value.

| Helper (letter) | Formula | Source column (letter) |
|---|---|---|
| `CREATION DATE` (`EE`) | `=INT(I2)` | `Created time` (`I`) |
| `RESOLVED DATE` (`EF`) | `=IF(K2="","",INT(K2))` | `Resolved time` (`K`) |
| `Refund Group Assignment` (`EH`) | `=IF(BL2="","",INT(BL2))` | `BL` |
| `Replacement Group Assignment` (`EI`) | `=IF(BM2="","",INT(BM2))` | `BM` |
| `Inward Payment Group Assignment` (`EJ`) | `=IF(BR2="","",INT(BR2))` | `BR` |
| `Spare Group Assignment` (`EK`) | `=IF(BT2="","",INT(BT2))` | `BT` |
| `Pickup Initiated Date` (`EL`) | `=IF(AX2="","",INT(AX2))` | `AX` |
| `Escalation Group Assignment` (`EM`) | `=IF(BO2="","",INT(BO2))` | `BO` |
| `Close Looping Group Assignment` (`EN`) | `=IF(BQ2="","",INT(BQ2))` | `BQ` |
| `Service Partner Assigned Date Stamp` (`EO`) | `=IF(DR2="","",INT(DR2))` | `DR` |
| `PRODUCT CLASSIFICATION 2` (`EP`) | `=IF(AL2="SERVICEABLE","SERVICEABLE",IF(AL2="NON SERVICEABLE","NON SERVICEABLE","NOT SELECTED"))` | `Product Classification` (`AL`) |
| `CREATION MONTH` (`EQ`) | `=TEXT(EE2,"MMM'YY")` | — |
| `RESOLVED MONTH` (`ER`) | `=TEXT(EF2,"mmm'yy")` | — |

`PRODUCT CLASSIFICATION 2` is exhaustive by construction — anything that isn't
one of the two named values, blanks included, becomes `NOT SELECTED`. Nothing
can go missing, so unlike Dashboard 5 this needs no allow-list.

In code, `INT(date)` is just the date part of the parsed timestamp, so no helper
columns are materialised.

## Step 2 — the seven blocks

Columns: `A` = row label, `B` = MTD, `C` = AVG, `D`–`AG` = days 1–31.
Every formula below is the `D` (day 1) cell of its block; the rest fill across.

| # | Block (sheet title) | Rows | Day comes from | Formula |
|---|---|---|---|---|
| 1 | `Inflow` | 19 groups | `CREATION DATE` | **none — pasted values** |
| 2 | `INFLOW (as per bucket movement dates)` | the 8 bucket date columns | each row's own column | `=COUNTIFS('RAW DATA June onwards'!$EH:$EH,D$25)` |
| 3 | `Inflow Source ` | 11 sources | `CREATION DATE` | `=COUNTIFS(…!$EE:$EE,D$37,…!$E:$E,$A38)` |
| 4 | `SP Inflow` | 161 partners | `Service Partner Assigned Date Stamp` | `=COUNTIFS(…!$EO:$EO,D$51,…!$AF:$AF,$A52)` |
| 5 | `Closure (BUCKET-WISE)` | 19 groups | `RESOLVED DATE` | `=COUNTIFS(…!$EF:$EF,D$216,…!$H:$H,$A218)` |
| 6 | `Closure` (product classification) | `SERVICEABLE` / `NON SERVICEABLE` / `NOT SELECTED` | `RESOLVED DATE` | `=COUNTIFS(…!$EF:$EF,D$239,…!$EP:$EP,$A241)` |
| 7 | `SP closure` | 161 partners | `RESOLVED DATE` | `=COUNTIFS(…!$EF:$EF,D$246,…!$AF:$AF,$A247)` |

Block 2's rows are date *columns*, not values of one column: each counts how
many tickets have a non-blank date in that column on that day. Its eight rows
appear in sheet order — Refund, Replacement, Inward Payment, Spare, Pickup,
Escalation, Close Looping, Service Partner Assigned.

Note block 4 keys off the SP-assigned date while block 7 keys off the resolved
date — an SP inflow and an SP closure are counted on different dates, which is
the point of having both.

### Block 1 has no formula — so its rule was derived and then proven

The documented procedure is manual: pivot the raw data (rows = `Group`, values
= count, filter = `Creation Date` for one day), `VLOOKUP` it into the month
sheet, **paste as values**, and replace `#N/A` with `0`. The rule is therefore
not recorded anywhere in the sheet.

The `PIVOT` sheet is the analyst's own working pivot, left in the file, filtered
to `CREATION DATE = 2026-09-22`. Day 22 is column `Y`. Comparing it against
`SEP'26!Y4:Y22`: **all 19 groups match, and the Grand Total matches at 592.**

So block 1 is `COUNTIFS(CREATION DATE = day, Group = label)` — the exact
parallel of block 5 on the creation date instead of the resolved date — proven
from the workbook's own artefact rather than assumed.

## Step 3 — MTD and AVG

- MTD is `=SUM(D3:AG3)` — the whole month, all 31 day columns.
- AVG is `=AVERAGE(D3:Y3)`, a **hand-maintained range**. `D:Y` is days 1–22,
  which is simply how far the sheet had been filled in; the procedure says
  "update the AVG column with the corresponding cell address which have been
  updated". It is not an average over the month.

The automatic equivalent used here is the average over the days the month
actually has data for, so a month-to-date average isn't diluted by days that
haven't happened yet. `avgDays` is reported alongside it.

## Verification against the workbook

`scripts/dashboards/daily_pending_closure.py`'s logic was run against the
workbook's **own** `RAW DATA June onwards` rows and compared to the cached
`SEP'26` grid, cell by cell. Both inputs come from the same file, so a mismatch
is a logic error, not a snapshot difference.

| Block | Cells | Result |
|---|---|---|
| `bucket-inflow` | 240 | **all match** |
| `inflow-source` | 330 | **all match** |
| `sp-inflow` | 4,830 | **all match** |
| `closure` | 570 | **all match** |
| `closure-classification` | 90 | **all match** |
| `sp-closure` | 4,830 | **all match** |
| `inflow` | 570 | every day's **total** matches; 156 individual cells differ — see below |

### Why `inflow` differs, and why that is the sheet being wrong

Day totals agree **exactly** on all 22 filled days (482, 497, 574, 517, 547,
491, 521, 580, 585, 543, 586, 557, 480, 505, 498, 470, 525, 480, 498, 515, 553,
592). What differs is which group each ticket sits under.

That is the signature of a stale paste. The values were pasted day by day from a
pivot taken that day; tickets reassigned to a different group afterwards keep
their old attribution in the sheet forever. Two details confirm it:

- **Day 22 is a perfect match, 0 cells off** — it is the most recently pasted
  day, and the leftover `PIVOT` sheet is dated Sep 22.
- **Day 23 is entirely blank in the sheet** while the raw data holds 119
  tickets created that day — it had not been pasted yet.

Computing the block makes it correct for every day and removes the manual
pivot-and-paste step entirely.

## Bug in the source workbook: `Over All Closure` drops its last row

Block 5's total is `=SUM(D218:D235)`, but its group rows run **218 to 236**.
Row 236 is `Testing`, and it is outside the range.

Measured on the live sheet, the total is wrong on **10 of 30 days** — on Sep 1
it reports 638 against an actual 685, understating by **47 tickets**.

Block 1's `Over All Inflow` is `=SUM(D4:D22)` across group rows 4–22 and is
**correct**. Only the closure total has the fault.

**This one is not reproduced.** Dashboard 5's total bug was reproduced on
request because it was deterministic — "exclude these two named categories" —
and so carries forward unambiguously. This one is a drag error: the row it drops
is whichever happens to sort last alphabetically. Reproduce it and the total's
meaning silently changes the day a group is added after `Testing`. The
implementation sums every category row; if the workbook's figure is wanted
instead, that is a one-line change and this note says where.

## Columns this dashboard needs

All by name, via `scripts/columns.py`:

`Created time`, `Resolved time`, `Group`, `Source`, `Partner Name`,
`Product Classification`, and the eight bucket dates — `Refund Group
Assignment`, `Replacement Group Assignment`, `Inward Payment Group Assignment`,
`Spare Group Assignment`, `Pickup Initiated Date`, `Escalation Group
Assignment`, `Close Looping Group Assignment`, `Service Partner Assigned Date
Stamp`.

Four were new to `columns.py`: `Source`, `Product Classification`,
`Escalation Group Assignment`, `Pickup Initiated Date`.

### Which parser each date column needs

Not a property of this dashboard but of whether `preprocess_raw.py` cleaned the
column on the way in — which is why the decision sits in one named set,
`ISO_DATE_COLS`, next to its reason.

| Parser | Columns |
|---|---|
| `parse_native_timestamp` (cleaned to ISO upstream) | `Created time`, `Resolved time`, `Refund Group Assignment`, `Replacement Group Assignment`, `Close Looping Group Assignment`, `Service Partner Assigned Date Stamp` |
| `parse_ddmmyyyy` (untouched upstream, still day-first text) | `Spare Group Assignment`, `Inward Payment Group Assignment`, `Pickup Initiated Date`, `Escalation Group Assignment` |

`Service Partner Assigned Date Stamp` keeps its time-of-day deliberately (see
`01-creation-to-assignment.md`); taking the date part discards it here, exactly
as the workbook's `INT()` does.

## Note on near-duplicate partner names

The partner lists contain what are plainly the same company spelled more than
one way — `Akash Refrigeration` / `Akash Refrigetation`, `Meer Infotech` /
`Meera Infotech`, `Eng-Vijay Kumar T-Bangalore` / `…-Banglaore`, `LYBLEY INDIA
PRIVATE LIMITED` / `Lybley India Pvt Ltd`. These are distinct values in the
export and stay distinct rows; merging them would mean guessing which pairs are
typos. Matching is case-insensitive (as `COUNTIFS` is), so case-only variants do
collapse into one row.
