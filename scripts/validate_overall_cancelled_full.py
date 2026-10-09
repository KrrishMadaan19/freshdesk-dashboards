"""Full-pipeline validation for Dashboard 5 (Overall Cancelled).

The existing check (validate_against_workbook_raw.py) recomputes the derivations
itself and compares two grids. That proves the logic but never runs the actual
transform -- the same blind spot that hid a real date bug in Dashboard 1 for
weeks. This runs overall_cancelled.main() end to end with KV stubbed and diffs
the JSON it would write against ALL THREE sheets, every cell.

Sheet -> grid mapping, from the workbook's own formulas:
  OVERALL - DASHBOARD  COUNTIFS(RAW!EE=month,   RAW!EH=category)      -> output["overall"]
  WEEKLY               COUNTIFS(RAW!EG=week,    EE=A1, EH=category)   -> output["weekly"][month]
  DAILY TREND          COUNTIFS(RAW!EF=day,     EE=A1, EH=category)   -> output["daily"][month]
where EE=RESOLVED MONTH, EF=DAYS, EG=resolved week, EH=resolution type2.
"""
import json
import os
import sys

import pandas as pd

SCRATCH = os.path.dirname(os.path.abspath(__file__))
REPO = r"C:\Users\KrrishMadaan\OneDrive - Lifelong Online Retail Private Limited\Desktop\Excel automation\freshdesk-dashboards"
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "scripts", "dashboards"))

import dashboard_lib as lib  # noqa: E402
import overall_cancelled as oc  # noqa: E402

DUMP = json.load(open(os.path.join(SCRATCH, "dump.json"), encoding="utf-8"))
RAW = pd.read_csv(os.path.join(SCRATCH, "overall_cancelled_raw.csv"),
                  low_memory=False, keep_default_na=False)
print(f"workbook RAW rows: {len(RAW):,}")

# Run the real transform. Only the two columns it reads are needed; everything
# else in the master dataset is irrelevant to this dashboard.
captured = {}
lib.load_master = lambda: RAW
lib.write_processed = lambda prefix, output: captured.update(output=output)
oc.main()
out = captured["output"]
print(f"months in output: {out['months']}\n")


def cell(sheet, ref):
    c = DUMP[sheet]["cells"].get(ref)
    if c is None:
        return None
    v = c.get("v2")
    return v


def headers(sheet, row):
    """Column letter -> header text for one header row, skipping column A."""
    found = {}
    for ref, c in DUMP[sheet]["cells"].items():
        letters = "".join(ch for ch in ref if ch.isalpha())
        digits = "".join(ch for ch in ref if ch.isdigit())
        if letters == "A" or digits != str(row):
            continue
        v = c.get("v2")
        if isinstance(v, str) and v.strip():
            found[letters] = v.strip()
    return found


def row_labels(sheet, first, last):
    out = {}
    for r in range(first, last + 1):
        v = cell(sheet, f"A{r}")
        if isinstance(v, str) and v.strip():
            out[r] = v.strip()
    return out


def diff(sheet, header_row, grid, label):
    """Diff one sheet against one grid of {row_label: {column_label: count}}."""
    cols = headers(sheet, header_row)
    rows = row_labels(sheet, header_row + 1, header_row + 16)
    checked = off = skipped_blanks = 0
    examples = []
    for r, row_label in rows.items():
        if row_label.casefold() == "blanks":
            # Deliberately not emitted -- the helper column provably never
            # produces this string. Verify the sheet agrees it is all zero.
            for letters in cols:
                if (cell(sheet, f"{letters}{r}") or 0) != 0:
                    examples.append(f"'Blanks' {letters}{r} is NON-ZERO in the sheet")
            skipped_blanks += 1
            continue
        key = row_label
        if key.casefold() in ("grand total",):
            key = "Grand Total"
        # Match the output's row spelling case-insensitively.
        folded = {k.casefold(): k for k in grid}
        mine_row = grid.get(folded.get(key.casefold(), key), {})
        # Column labels are matched case-insensitively: the sheet's header row
        # displays "JAN'26" while its own RESOLVED MONTH helper column -- what
        # the COUNTIFS actually compares against -- emits "Jan'26". COUNTIFS
        # does not care; an exact dict lookup does, and reported 111 phantom
        # mismatches until this was fixed.
        folded_cols = {c.casefold(): v for c, v in mine_row.items()}
        for letters, col_label in cols.items():
            want = cell(sheet, f"{letters}{r}")
            if want is None:
                continue
            got = folded_cols.get(col_label.casefold(), 0)
            checked += 1
            if int(want) != int(got):
                off += 1
                if len(examples) < 3:
                    examples.append(
                        f"{row_label[:34]!r} / {col_label}: sheet={int(want)} mine={int(got)}")
    status = "OK  " if off == 0 else "FAIL"
    print(f"{status} {label:<34} {checked - off:>5}/{checked:<5} cells match"
          f"   (Blanks rows skipped: {skipped_blanks})")
    for e in examples:
        print(f"         {e}")
    return off


total = 0

# 1. OVERALL - DASHBOARD: months across, header row 2.
total += diff("OVERALL - DASHBOARD", 2, out["overall"], "OVERALL - DASHBOARD (monthly)")

# 2/3. WEEKLY and DAILY TREND are both scoped to the month named in A1.
for sheet, key in (("WEEKLY", "weekly"), ("DAILY TREND", "daily")):
    month = cell(sheet, "A1")
    grid = out[key].get(month)
    if grid is None:
        print(f"FAIL {sheet}: output has no {key} grid for month {month!r} "
              f"(available: {list(out[key])[:12]})")
        total += 1
        continue
    total += diff(sheet, 2, grid, f"{sheet} ({month})")

print(f"\ntotal cells off across all three sheets: {total}")
print("FULL PIPELINE MATCHES THE WORKBOOK" if total == 0 else "DIFFERENCES PRESENT")
