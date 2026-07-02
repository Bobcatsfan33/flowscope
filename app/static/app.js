"use strict";

// ---- Config ---------------------------------------------------------------
const POLL_MS = 30_000; // re-pull from server every 30s (server rescans ~5min)

// ---- State ----------------------------------------------------------------
const state = {
  flows: [],
  catalysts: [],
  search: "",
  direction: "",
  minScore: 0,
  catalystKind: "",
  sortKey: "flow_score",
  sortDir: -1,
};

// ---- Helpers --------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const fmtMoney = (n) => {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(0);
};
const fmtNum = (n) => (n == null ? "—" : n.toLocaleString("en-US"));
// null = undefined/infinite ratio (calls, no puts); 999 kept for old snapshots.
const fmtRatio = (r) => (r == null || r >= 999 ? "∞" : r.toFixed(2));
const arrow = (dir) =>
  dir === "bullish" ? '<span class="arrow-up">▲</span>'
  : dir === "bearish" ? '<span class="arrow-down">▼</span>'
  : '<span class="arrow-flat">—</span>';
const sigClass = (d) => `sig ${d}`;
const escapeHtml = (s) =>
  String(s || "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---- Data fetching --------------------------------------------------------
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

async function refreshData() {
  try {
    const [flowRes, catRes, health, meta] = await Promise.all([
      fetchJSON("/api/flow?limit=600"),
      fetchJSON("/api/catalysts?limit=150"),
      fetchJSON("/api/health"),
      fetchJSON("/api/meta"),
    ]);
    state.flows = flowRes.data || [];
    state.catalysts = catRes.data || [];
    renderStatus(health.data, flowRes.meta);
    renderCaps(meta.data.capabilities);
    renderFlows();
    renderCatalysts();
  } catch (err) {
    setStatus("error", "connection error", String(err.message || err));
  }
}

// ---- Rendering: status + capabilities ------------------------------------
function setStatus(kind, text, sub) {
  $("#status-dot").className = `dot ${kind}`;
  $("#status-text").textContent = text;
  if (sub != null) $("#status-sub").textContent = sub;
}

function renderStatus(health, meta) {
  if (!health) return;
  if (health.running && !health.has_snapshot) {
    setStatus("warming", "scanning…", "first scan in progress");
  } else if (health.last_error) {
    setStatus("error", "last scan errored", health.last_error.slice(0, 60));
  } else if (health.has_snapshot) {
    const when = meta && meta.generated_at ? new Date(meta.generated_at) : null;
    const ago = when ? Math.round((Date.now() - when.getTime()) / 1000) : null;
    const closed = health.market_session === "closed" ? " · market closed" : "";
    const sub = `${meta ? meta.scanned : "?"} scanned · updated ${ago != null ? ago + "s ago" : "?"}${closed}`;
    setStatus("live", health.running ? "live · rescanning" : "live", sub);
  } else {
    setStatus("warming", "warming up…", "");
  }
}

function renderCaps(caps) {
  if (!caps) return;
  const labels = {
    yahoo_options: "Yahoo Options",
    sec_edgar: "SEC EDGAR",
    usaspending_contracts: "USAspending",
    senate_disclosures: "Senate Trades",
    finnhub: "Finnhub",
    tradier: "Tradier",
    fmp: "FMP",
    newsapi: "NewsAPI",
    quiver: "Quiver",
    alphavantage: "AlphaVantage",
  };
  $("#caps").innerHTML = Object.entries(caps)
    .map(([k, v]) => {
      // String values = reserved hooks ("configured (not yet used)" etc.):
      // never shown as live/green, only annotated.
      const reserved = typeof v === "string";
      const on = !reserved && !!v;
      const title = reserved ? ` title="${v}"` : "";
      const suffix = reserved ? " (reserved)" : "";
      return `<span class="cap ${on ? "on" : "off"}"${title}>${on ? "●" : "○"} ${labels[k] || k}${suffix}</span>`;
    })
    .join("");
}

// ---- Rendering: flow table ------------------------------------------------
function visibleFlows() {
  let rows = state.flows.slice();
  if (state.search) {
    const n = state.search.toUpperCase();
    rows = rows.filter((f) => f.symbol.includes(n));
  }
  if (state.direction) rows = rows.filter((f) => f.direction === state.direction);
  if (state.minScore > 0) rows = rows.filter((f) => f.flow_score >= state.minScore);
  rows.sort((a, b) => {
    const av = a[state.sortKey], bv = b[state.sortKey];
    if (av === bv) return 0;
    return (av > bv ? 1 : -1) * state.sortDir;
  });
  return rows;
}

function renderFlows() {
  const rows = visibleFlows();
  const body = $("#flow-body");
  const empty = $("#flow-empty");
  if (!rows.length) {
    body.innerHTML = "";
    empty.style.display = "block";
    empty.textContent = state.flows.length ? "No tickers match the filters." : "Warming up — first scan in progress…";
    return;
  }
  empty.style.display = "none";
  const maxScore = Math.max(...rows.map((r) => r.flow_score), 1);
  body.innerHTML = rows
    .map((f, i) => {
      const badges = (f.catalysts || [])
        .reduce((acc, c) => { acc[c.kind] = (acc[c.kind] || 0) + 1; return acc; }, {});
      const badgeHtml = Object.entries(badges)
        .map(([k, n]) => `<span class="badge ${k}">${k.replace("_", " ")}${n > 1 ? " ×" + n : ""}</span>`)
        .join("");
      const barW = Math.max(3, (f.flow_score / maxScore) * 70);
      return `<tr data-sym="${f.symbol}">
        <td>${i + 1}</td>
        <td>${f.symbol}</td>
        <td><div class="score-cell">
          <div class="score-bar-wrap"><div class="score-bar" style="width:${barW}px"></div></div>
          <span class="score-num">${f.flow_score.toFixed(1)}</span>
        </div></td>
        <td><span class="${sigClass(f.direction)}">${arrow(f.direction)} ${f.direction}</span></td>
        <td>${fmtMoney(f.call_premium)}</td>
        <td>${fmtMoney(f.put_premium)}</td>
        <td>${fmtRatio(f.call_put_ratio)}</td>
        <td>${fmtNum(f.total_volume)}</td>
        <td>${f.unusual_contracts}</td>
        <td><div class="cat-badges">${badgeHtml || '<span class="badge">—</span>'}</div></td>
      </tr>`;
    })
    .join("");
  body.querySelectorAll("tr").forEach((tr) =>
    tr.addEventListener("click", () => openDrawer(tr.dataset.sym)));
}

// ---- Rendering: catalyst feed --------------------------------------------
function renderCatalysts() {
  let items = state.catalysts.slice();
  if (state.catalystKind) items = items.filter((c) => c.kind === state.catalystKind);
  const feed = $("#catalyst-feed");
  if (!items.length) {
    feed.innerHTML = '<div class="empty">No catalysts yet.</div>';
    return;
  }
  feed.innerHTML = items
    .slice(0, 120)
    .map((c) => `<div class="feed-item" data-sym="${c.symbol}">
      <div class="feed-row1">
        <span class="feed-sym">${arrow(c.direction)} ${c.symbol}</span>
        <span class="badge ${c.kind}">${c.kind.replace("_", " ")}</span>
      </div>
      <div class="feed-head">${escapeHtml(c.headline)}</div>
      <div class="feed-detail">${escapeHtml(c.detail)} · ${escapeHtml((c.timestamp || "").slice(0, 10))} · ${escapeHtml(c.source)}</div>
    </div>`)
    .join("");
  feed.querySelectorAll(".feed-item").forEach((el) =>
    el.addEventListener("click", () => openDrawer(el.dataset.sym)));
}

// ---- Drawer (drill-down) --------------------------------------------------
function openDrawer(symbol) {
  const f = state.flows.find((x) => x.symbol === symbol);
  $("#drawer-title").textContent = symbol + (f ? `  ·  $${f.underlying_price}` : "");
  const body = $("#drawer-body");
  if (!f) {
    const cats = state.catalysts.filter((c) => c.symbol === symbol);
    body.innerHTML = renderCatSection(cats) || "<p>No flow data for this symbol.</p>";
  } else {
    body.innerHTML = `
      <div class="dsection">
        <h4>Signal</h4>
        <div class="kv"><span>Flow score</span><span>${f.flow_score.toFixed(1)}</span></div>
        <div class="kv"><span>Direction</span><span class="${sigClass(f.direction)}">${arrow(f.direction)} ${f.direction} (${(f.direction_confidence * 100).toFixed(0)}%)</span></div>
        <div class="kv"><span>Call premium</span><span>$${fmtMoney(f.call_premium)}</span></div>
        <div class="kv"><span>Put premium</span><span>$${fmtMoney(f.put_premium)}</span></div>
        <div class="kv"><span>Call/Put ratio</span><span>${fmtRatio(f.call_put_ratio)}</span></div>
        <div class="kv"><span>Total volume</span><span>${fmtNum(f.total_volume)}</span></div>
        <div class="kv"><span>Unusual contracts</span><span>${f.unusual_contracts}</span></div>
        <div class="kv"><span>Sources</span><span>${(f.sources || []).join(", ")}</span></div>
      </div>
      <div class="dsection">
        <h4>Top contracts by premium</h4>
        ${(f.top_contracts || []).map((c) => `<div class="contract-row">
          <span class="${c.type === "call" ? "arrow-up" : "arrow-down"}">${c.type.toUpperCase()}</span>
          <span>$${c.strike} ${(c.expiration || "").slice(5)}</span>
          <span>vol ${fmtNum(c.volume)} (${c.vol_oi_ratio}x OI)</span>
          <span>$${fmtMoney(c.premium)}</span>
        </div>`).join("") || "<p>—</p>"}
      </div>
      ${renderCatSection(f.catalysts || [])}`;
  }
  $("#drawer").classList.remove("hidden");
}

function renderCatSection(cats) {
  if (!cats || !cats.length) return "";
  return `<div class="dsection"><h4>Catalysts</h4>${cats
    .map((c) => `<div class="dcat">
      <div><span class="badge ${c.kind}">${c.kind.replace("_", " ")}</span> ${arrow(c.direction)} ${escapeHtml(c.headline)}</div>
      <div class="feed-detail">${escapeHtml(c.detail)}</div>
      ${c.url ? `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">source ↗</a>` : ""}
    </div>`)
    .join("")}</div>`;
}

// ---- Events ---------------------------------------------------------------
function wireEvents() {
  $("#search").addEventListener("input", (e) => { state.search = e.target.value.trim(); renderFlows(); });
  $("#direction-filter").addEventListener("change", (e) => { state.direction = e.target.value; renderFlows(); });
  $("#min-score").addEventListener("input", (e) => {
    state.minScore = Number(e.target.value);
    $("#min-score-val").textContent = e.target.value;
    renderFlows();
  });
  $("#catalyst-filter").addEventListener("change", (e) => { state.catalystKind = e.target.value; renderCatalysts(); });
  $("#drawer-close").addEventListener("click", () => $("#drawer").classList.add("hidden"));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").classList.add("hidden"); });

  document.querySelectorAll("thead th[data-sort]").forEach((th) =>
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (key === "rank") return;
      if (state.sortKey === key) state.sortDir *= -1;
      else { state.sortKey = key; state.sortDir = key === "symbol" ? 1 : -1; }
      renderFlows();
    }));

  $("#refresh-btn").addEventListener("click", async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "⟳ scanning…";
    try {
      await fetch("/api/refresh", { method: "POST" });
      setStatus("warming", "scan triggered", "results in ~10-40s");
    } catch (_) { /* ignore */ }
    setTimeout(() => { btn.disabled = false; btn.textContent = "⟳ Scan now"; refreshData(); }, 8000);
  });
}

// ---- Boot -----------------------------------------------------------------
wireEvents();
refreshData();
setInterval(refreshData, POLL_MS);
