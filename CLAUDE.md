# Freshdesk Analytics Dashboard Site

Replaces a daily manual Excel workflow (10 dashboards built from Freshdesk
ticket exports via VLOOKUPs, pivot tables, and formulas) with one website,
built incrementally, one dashboard at a time.

## Architecture

```
You (daily): export tickets from Freshdesk -> drop file on the upload page
       |
       v
Upload page (Cloudflare Pages Function, gated by Cloudflare Access)
       |  saves raw file to Workers KV, fires a GitHub repository_dispatch event
       v
GitHub Actions workflow (triggered by upload, not a schedule)
  - merges new file into master dataset in KV (upsert by Ticket ID)
  - runs each dashboard's transform script
       v
Processed dashboard JSON in KV  ->  Cloudflare Pages (static site) reads latest JSON
```

- No local storage of data — the exported file passes through the user's
  machine only briefly between Freshdesk download and upload.
- No automated Freshdesk API polling — ingestion is manual-upload triggered,
  which avoids Freshdesk API rate-limit/duration problems entirely.
- No database, no R2 (R2 requires enabling billing even on the free tier) —
  dated raw uploads and processed dashboard JSON both live in Cloudflare
  Workers KV. A single KV value is capped at 25MB, so large exports (the
  daily raw file, and the ever-growing master dataset) are split across
  multiple line-aligned chunk keys plus a small manifest key recording the
  chunk count — see `chunkText`/`writeChunked` in
  `website/functions/api/upload.js` and `write_chunked`/`read_chunked` in
  `scripts/process_upload.py`. Revisit if KV's daily operation limits
  (100k reads/1k writes) or 1GB total storage become a real constraint.

## Cloudflare resources

- KV namespace: `freshdesk-dashboards` (id `8b60514429c14289aad068539e588e15`), bound
  as `TICKETS_KV` in the Pages Function via `wrangler.toml`.
- Pages project: `freshdesk-dashboards`, deployed from `website/` by
  `.github/workflows/deploy-pages.yml` on every push to `main`.

## Folder structure

```
freshdesk-dashboards/
  website/
    upload/                  # drag-and-drop upload page (Pages Function)
    dashboards/               # one component/section per dashboard
  scripts/
    process_upload.py         # triggered by upload — cleans + merges into KV master dataset
    preprocess_raw.py         # the 5 raw-export cleanup rules, run by process_upload.py
    date_utils.py             # shared date parsers — see comments, this matters a lot
    kv_store.py                # shared KV chunked read/write helpers
    dashboards/
      creation_to_assignment.py
      pendency_view.py
      daily_pending_closure.py
      csat_tracker.py
      overall_cancelled.py
      refund_tat.py
      replacement_tat.py
      sp_closure_bifurcation.py
      sp_tat_performance.py
      no_sp_assigned.py
  docs/
    excel_process_notes/      # one detailed formula-reference doc per dashboard
  .github/workflows/
    process-upload.yml        # triggered by repository_dispatch
```

## Conventions

- Each dashboard's transform script lives at `scripts/dashboards/<name>.py`,
  reads the cleaned + merged master dataset from KV, and writes
  `processed:<name>` (chunked) to KV.
- Each dashboard gets its own section/route under `website/dashboards/`, reading
  its own JSON via `/api/dashboards/<name>` (a generic Pages Function).
- **The raw Freshdesk export is cleaned before it ever reaches the master
  dataset** — `process_upload.py` runs `preprocess_raw.py`'s 5 business
  rules (see its docstring) on every new upload, backfilling a handful of
  specific blank assignment-date columns and normalizing date formatting
  to unambiguous ISO strings. This does **not** cover every date column —
  only the ones the 5 rules mention. Check whether a date column your
  dashboard needs is one of them before assuming it arrives clean; if
  not, use `date_utils.parse_ddmmyyyy` (defensive, handles messy raw
  formatting) rather than assuming ISO. Getting this wrong is exactly
  what caused two real bugs in Dashboard 1 — see
  `docs/excel_process_notes/01-creation-to-assignment.md`.
- Formulas must be reproduced exactly as documented in
  `docs/excel_process_notes/<name>.md` — including matching known quirks,
  unless a note says the quirk was intentionally corrected.
- Every dashboard needs a **month-filter control** in its UI (data spans
  multiple months per export) — default to showing the most recent month,
  let the user pick any month present in the dataset.
- Validate every transform script's output against the real numbers in the
  source Excel dashboard for a known date range before wiring it into the
  live pipeline.

## Session workflow

- One Claude Code session per dashboard. Finish, validate, commit, then
  start a *new* session for the next dashboard — don't keep building in one
  long-running chat.
- Use a subagent for any Excel formula reverse-engineering that involves
  reading large sheets, so only the summary lands in the main session.

## Dashboard status

- [x] 1. Creation to Assignment Report (incl. Weekly View drill-down) —
      *built, deployed, and validated against real production data
      (183,632 tickets) diffed cell-by-cell against the user's live
      reference workbook. Found and fixed three real bugs (a dayfirst
      date-parsing bug, a wrong WEEKNUM boundary, and a missing raw-data
      cleanup step — now scripts/preprocess_raw.py). After all three,
      4 of 6 rows are exact or off-by-one; the remaining two are
      expected to differ (the live sheet has a known drag-error bug this
      dashboard was asked to fix, not replicate). See "Validation against
      real production data" in
      docs/excel_process_notes/01-creation-to-assignment.md for the full
      story.*
- [ ] 2. Pendency View
- [ ] 3. Daily Pending and Closure Dashboard
- [ ] 4. C-SAT Tracker Report
- [ ] 5. Overall Cancelled Report
- [ ] 6. Refund TAT Performance
- [ ] 7. Replacement TAT Performance
- [ ] 8. Service Partner Closure Bifurcation Report
- [ ] 9. SP TAT Performance
- [ ] 10. No Service Partner Assigned Report
