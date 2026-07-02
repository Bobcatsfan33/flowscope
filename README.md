# 📡 FlowScope

**A free, self-hosted options-flow & catalyst dashboard — an open competitive
take on Unusual Whales / ThetaData, built entirely on free data sources.**

FlowScope continuously scans the **S&P 500 + Nasdaq-100**, ranks every name by
**options-flow intensity**, tells you whether the flow points **bullish or
bearish**, and overlays every free signal that can move a stock — insider
trades, congressional/officials trading, federal contract awards, SEC 8-Ks,
news, and earnings. (A 13F institutional overlay is planned but not yet wired
to a data source.)

It runs with **zero API keys** out of the box and gets richer as you add free
keys. Everything is URL-based, auto-updating, and searchable.

---

## What you get

| Feature | How |
|---|---|
| **Ranked options flow** | Every S&P 500 + NDX 100 ticker scored 0-100 on unusual-volume intensity (vol/OI, premium size, breadth). |
| **Direction signal** | Bullish/bearish/neutral with a confidence %. This is a **premium-skew proxy** — computed from reported call vs put traded premium (volume × price), weighted toward near-the-money strikes — not observed trade-by-trade order flow. Surfaced as `direction_basis: "premium_skew_proxy"` in the API. |
| **Searchable & sortable** | Live client-side search, direction filter, min-score slider, click-to-drill-down. |
| **Auto-update** | Background scheduler rescans on an interval **during US market hours (Mon–Fri 09:30–16:00 ET)**; off-hours the last snapshot keeps being served (no fake freshness). The UI repolls every 30s. Manual "Scan now" button bypasses the market-hours gate. |
| **Catalyst overlay** | Insider (Form 4), congress/officials, federal contracts, SEC filings, news, earnings — attached to each ticker and shown as a live feed. Institutional (13F) overlay is **planned** (no free data source wired yet). |
| **Failover by design** | Each data type tries multiple sources in priority order; the app keeps working if any one source is down. |

---

## Quick start (zero keys)

```bash
git clone https://github.com/Bobcatsfan33/flowscope.git
cd flowscope
./run.sh          # creates venv, installs deps, starts on http://localhost:8000
```

Open **http://localhost:8000**. The first scan populates in ~10-60s (it runs in
the background; the page shows "warming up" until then).

### Docker

```bash
cp .env.example .env       # optional: add keys
docker compose up --build  # http://localhost:8000
```

### Deploy to a public URL (free)

`render.yaml` is included for one-click [Render](https://render.com) deploys
(Docker, free plan, health-checked). Fly.io / Railway work the same way from the
Dockerfile.

---

## 🔑 API keys — what to get and why

**None are required.** With zero keys, FlowScope already runs on:
Yahoo (options chains), SEC EDGAR (insider + filings), USAspending (federal
contracts), and the Senate disclosure feed.

Adding these **free, no-credit-card** keys unlocks more coverage, greeks, and
better failover. Put them in `.env` (copy from `.env.example`).

| Env var | Provider | Free? | Unlocks | Get it at |
|---|---|---|---|---|
| `FINNHUB_API_KEY` | Finnhub | ✅ free, no CC | **Biggest win:** options failover, insider *direction*, **both-chamber** congress trades, company news, earnings calendar | https://finnhub.io/register |
| `TRADIER_TOKEN` | Tradier sandbox | ✅ free, no CC | Full options chains **with greeks** + delayed quotes (best options failover) | https://developer.tradier.com/ |
| `FMP_API_KEY` | Financial Modeling Prep | ✅ free tier | **Reserved hook — no code path uses this key yet.** Shown as "configured (not yet used)" in the capability strip. | https://site.financialmodelingprep.com/developer/docs |
| `NEWSAPI_KEY` | NewsAPI | ✅ free dev tier | **Reserved hook — no code path uses this key yet.** Shown as "configured (not yet used)". | https://newsapi.org/register |
| `QUIVER_API_KEY` | Quiver Quantitative | ✅ limited free | **Reserved hook — no code path uses this key yet.** Shown as "configured (not yet used)". | https://www.quiverquant.com/ |
| `SEC_USER_AGENT` | SEC EDGAR | n/a (no key) | **Set this to your email** — SEC requires a descriptive UA or it blocks you | — |

> **Recommended pair to start:** `FINNHUB_API_KEY` + `TRADIER_TOKEN`. Those two
> cover the highest-value gaps (directional insider/congress + greeks).

Once you paste a key into `.env` and restart, the dashboard's **capability
strip** (top of the page) lights that source green automatically — no code
changes needed. Reserved hooks (FMP, NewsAPI, Quiver, AlphaVantage) are shown
honestly as configured-but-unused until their integrations land.

---

## How the score works

For each ticker FlowScope pulls the nearest expirations and computes, per
contract: traded **premium** (`volume × price × 100`), **vol/OI ratio** (fresh
positioning when > 1; volume on a zero-OI strike counts as maximally unusual),
and **moneyness**. It then blends:

```
flow_score = 55% · log-scaled unusual premium
           + 25% · peak vol/OI ratio (among contracts above the premium floor)
           + 20% · breadth (# of unusual contracts)        → 0-100
```

**Direction** is a **premium-skew proxy**: signed traded premium (calls +,
puts −), weighted 1.5× for near-the-money strikes where conviction
concentrates; confidence is `|net| / gross`. Because it is derived from
end-of-chain volume × price rather than observed trade aggressor side, it can
misread sold calls / sold puts — treat it as a skew indicator, not tape-read
flow. Catalysts add a capped boost (e.g. insider **buy** +6 — neutral/sale
Form 4s add nothing — congress +5) so a name with both unusual flow *and* an
insider buy ranks above pure flow.

See [`app/scoring.py`](app/scoring.py) — it's pure, documented, and unit-tested.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/flow?q=&direction=&min_score=&limit=` | Ranked, filtered flow list |
| `GET /api/flow/{symbol}` | Single-ticker detail (top contracts + catalysts) |
| `GET /api/catalysts?kind=&symbol=&limit=` | Catalyst feed |
| `GET /api/health` | Scan status (incl. `market_session` + `data_as_of`) |
| `GET /api/meta` | Active capabilities + config |
| `POST /api/refresh` | Trigger an out-of-band scan |

Interactive docs at `/docs` (FastAPI/OpenAPI).

---

## Configuration

All tunables live in `.env` (see `.env.example`): `REFRESH_INTERVAL_SECONDS`,
`MAX_TICKERS_PER_CYCLE` (rate-limit safety cap), `UNIVERSE_REFRESH_HOURS`,
`HTTP_TIMEOUT_SECONDS`, `LOG_LEVEL`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Architecture

```
app/
  config.py            settings + capability flags
  models.py            immutable ContractFlow / Catalyst / TickerFlow / Snapshot
  scoring.py           pure flow scoring + direction
  universe.py          S&P500 + NDX100 (Wikipedia, bundled fallback)
  aggregator.py        orchestrates scan: options → rank → catalyst overlay
  scheduler.py         APScheduler background cycles
  store.py             thread-safe snapshot store
  http_client.py       shared async httpx client w/ retries
  sources/
    options/           yahoo (no key) → tradier → finnhub  [failover]
    catalysts/         sec_edgar, congress_senate (no key) + finnhub, usaspending
  routers/             flow, catalysts, system
  static/              zero-build dashboard (index.html / app.js / styles.css)
```

---

## Disclaimer

FlowScope aggregates **delayed, free** public data for **research and
educational** purposes. It is **not investment advice**. Free options data is
delayed and may be incomplete; do your own diligence.
