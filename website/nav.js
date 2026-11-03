// The list of shipped dashboards, in one place.
//
// The homepage builds its cards from this, and every page's nav builds its
// "Dashboards" menu from it, so adding a dashboard means adding one entry here
// -- not editing five navs that then drift apart. `id` must match the
// transform script's PROCESSED_PREFIX suffix (the name used in
// /api/dashboards/<id>), because the homepage looks up each card's freshness
// badge by it.
window.DASHBOARDS = [
  {
    id: "creation-to-assignment",
    name: "Creation to Assignment",
    href: "/dashboards/creation-to-assignment/",
    description: "Ageing from ticket creation to inward, spare, refund, replacement and SP assignment.",
  },
  {
    id: "daily-pending-closure",
    name: "Daily Pending and Closure",
    href: "/dashboards/daily-pending-closure/",
    description: "Daily inflow and closure by group, channel, bucket movement and service partner.",
  },
  {
    id: "overall-cancelled",
    name: "Overall Cancelled",
    href: "/dashboards/overall-cancelled/",
    description: "Cancelled, spam, auto-closed and forwarded tickets by reason, over time.",
  },
];

// Cycled per dashboard so the cards on the homepage and the dots in the nav
// menu give each dashboard the same colour in both places.
window.DASHBOARD_ACCENTS = [
  "var(--accent-blue)",
  "var(--accent-violet)",
  "var(--accent-teal)",
  "var(--accent-coral)",
  "var(--accent-pink)",
];

(function () {
  const CHEVRON =
    '<svg class="nav-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>';

  // "/dashboards/overall-cancelled" and "/dashboards/overall-cancelled/" are
  // the same page; compare without the trailing slash so the current entry is
  // marked either way.
  function samePage(a, b) {
    return a.replace(/\/+$/, "") === b.replace(/\/+$/, "");
  }

  function buildMenu(here) {
    const wrap = document.createElement("div");
    wrap.className = "nav-menu";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "nav-link nav-menu-btn";
    button.setAttribute("aria-haspopup", "true");
    button.setAttribute("aria-expanded", "false");
    button.innerHTML = `Dashboards ${CHEVRON}`;

    const list = document.createElement("div");
    list.className = "nav-menu-list";
    list.hidden = true;

    window.DASHBOARDS.forEach((d, i) => {
      const a = document.createElement("a");
      a.href = d.href;
      const dot = document.createElement("span");
      dot.className = "nav-dot";
      dot.style.background =
        window.DASHBOARD_ACCENTS[i % window.DASHBOARD_ACCENTS.length];
      const label = document.createElement("span");
      label.textContent = d.name;
      a.appendChild(dot);
      a.appendChild(label);
      if (samePage(here, d.href)) a.setAttribute("aria-current", "page");
      list.appendChild(a);
    });

    function close() {
      list.hidden = true;
      button.setAttribute("aria-expanded", "false");
    }

    button.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = list.hidden;
      list.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    });

    // Clicking anywhere else, or Escape, closes it -- a menu that can only be
    // dismissed by hitting the same button again is the kind of thing you
    // notice every single day.
    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !list.hidden) {
        close();
        button.focus();
      }
    });

    wrap.appendChild(button);
    wrap.appendChild(list);
    return wrap;
  }

  function render() {
    const nav = document.querySelector("nav[data-nav]");
    if (!nav) return; // The homepage has no nav bar; it IS the dashboard list.
    const here = window.location.pathname;

    // Replaces the no-JS fallback links that sit in the markup.
    nav.textContent = "";

    const home = document.createElement("a");
    home.className = "nav-link";
    home.href = "/";
    home.textContent = "Home";
    nav.appendChild(home);

    nav.appendChild(buildMenu(here));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
