// One heat-map table renderer for the dashboard pages. A page describes a
// view as data (a "spec") and this draws it, so the TAT dashboards -- which
// are all variations of rows x bands -- don't each carry their own copy.
//
// spec = {
//   corner:   heading for the row-label column
//   rows:     row keys, in display order
//   rowName:  key -> display text (optional)
//   columns:  column keys
//   grid:     {row: {column: count}}
//   cellPct:  true -> show each cell as a share of its row (under the count)
//   extras:   [{label, kind: "total"|"rate", value(rowObj, rowKey)}]
//   totalRow: true -> append a Grand Total row summing every column
//   totalKeys: extra keys to sum into the total row (for extras that need them)
// }
(function () {
  const sum = (obj, keys) => keys.reduce((t, k) => t + (obj?.[k] ?? 0), 0);
  const pct = (n, d) => (d > 0 ? `${((n / d) * 100).toFixed(1)}%` : "–");

  function th(text, cls) {
    const el = document.createElement("th");
    el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }

  function countCell(count, max, rowTotal) {
    const td = document.createElement("td");
    td.className = "cell";
    if (max > 0 && count > 0) {
      td.style.backgroundColor = `rgba(var(--heat-rgb), ${0.08 + (count / max) * 0.77})`;
    }
    const span = document.createElement("span");
    span.className = "count";
    span.textContent = count.toLocaleString();
    td.appendChild(span);
    if (rowTotal !== null) {
      const p = document.createElement("span");
      p.className = "pct";
      p.textContent = pct(count, rowTotal);
      td.appendChild(p);
    }
    return td;
  }

  function extraCell(extra, value) {
    const td = document.createElement("td");
    td.className = extra.kind === "rate" ? "rate" : "total";
    td.textContent = typeof value === "number" ? value.toLocaleString() : value;
    return td;
  }

  function render(headerRowEl, bodyEl, spec) {
    const { rows, columns, grid } = spec;
    const extras = spec.extras || [];
    const rowName = spec.rowName || ((r) => r);

    headerRowEl.innerHTML = "";
    headerRowEl.appendChild(th(spec.corner, "row-label"));
    for (const c of columns) headerRowEl.appendChild(th(c));
    for (const e of extras) headerRowEl.appendChild(th(e.label, e.kind === "rate" ? "rate-head" : ""));

    // Heat scale from body cells only, never the total row.
    let max = 0;
    for (const r of rows) for (const c of columns) max = Math.max(max, grid?.[r]?.[c] ?? 0);

    bodyEl.innerHTML = "";
    for (const r of rows) {
      const row = grid?.[r] || {};
      const tr = document.createElement("tr");
      const label = th(rowName(r), "row-label");
      tr.appendChild(label);
      const rowTotal = sum(row, columns);
      for (const c of columns) tr.appendChild(countCell(row[c] ?? 0, max, spec.cellPct ? rowTotal : null));
      for (const e of extras) tr.appendChild(extraCell(e, e.value(row, r)));
      bodyEl.appendChild(tr);
    }

    if (spec.totalRow && rows.length) {
      const totals = {};
      for (const k of [...columns, ...(spec.totalKeys || [])]) {
        if (!(k in totals)) totals[k] = rows.reduce((t, r) => t + (grid?.[r]?.[k] ?? 0), 0);
      }
      const tr = document.createElement("tr");
      tr.className = "grand-total-row";
      tr.appendChild(th("Grand Total", "row-label"));
      const grand = sum(totals, columns);
      for (const c of columns) tr.appendChild(countCell(totals[c], 0, spec.cellPct ? grand : null));
      for (const e of extras) tr.appendChild(extraCell(e, e.value(totals, null)));
      bodyEl.appendChild(tr);
    }
  }

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // "2026-09-04" -> "4 Sep 2026". By hand: toLocaleDateString writes "Sept"
  // in current browsers' en-GB, which clashes with the "Sep'26" labels.
  function longDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return `${d} ${MONTHS[m - 1]} ${y}`;
  }

  window.HeatTable = { render, sum, pct, longDate };
})();
