# Equity Research Desk

On-demand, analyst-style research profiles for US-listed equities. Enter a
ticker and receive a live-generated report combining plain-English business
analysis, forward-looking catalysts, and a five-factor quantitative
evaluation — built entirely on free data sources and free-tier APIs.

> **Disclaimer** — This software produces automated research summaries for
> educational purposes only. Nothing it generates is investment advice or a
> recommendation to buy or sell any security.

---

## Features

| Section | Content | Source |
|---|---|---|
| **Executive Summary** | Three-paragraph plain-English profile: what the business does, how it makes money, and its competitive character | Yahoo Finance fundamentals + LLM |
| **Future Pipeline** | Forward catalysts classified into *Confirmed Catalysts*, *Developing Stories*, and *Risk Events*, plus the next earnings date | Alpha Vantage news (with keyless Yahoo Finance fallback) + LLM |
| **Evaluation** | Five-factor quant score (0–100) built on the academic factor literature — EBIT/EV (Greenblatt), 12-1 momentum, gross profitability (Novy-Marx), Sloan accruals, idiosyncratic volatility — with sector-adaptive weights, plus valuation ratios, growth metrics, price performance vs. S&P 500, and analyst consensus | Yahoo Finance + in-house quant model (no LLM) |

The report masthead shows the **live share price with day change**, and an
**interactive 1-year price chart** sits above the sections — range toggles
(1M/3M/6M/1Y), an indexed **vs S&P 500** overlay, and a crosshair tooltip.
Chart colors are validated for colorblind separation and contrast on both
the dark and light themes.

**Engineering highlights**

- **One LLM request per report** — both generated sections come from a single
  merged prompt, doubling daily capacity on free-tier quotas.
- **Automatic model fallback** — `gemini-2.5-flash` (quality-first) falls back
  to `gemini-2.0-flash` (~1,500 req/day) on quota exhaustion, so reports keep
  flowing.
- **Graceful degradation** — every data source can fail independently without
  blocking the report; news falls back to a keyless source; missing fields
  render as `N/A`.
- **Format-validated LLM output** — responses are structurally validated and
  regenerated once on failure before accepting a best-effort parse.
- **Parallel data pipeline** — all market-data fetches, the quant model, and
  the LLM call run concurrently; typical report time is 8–15 seconds.
- **Deduplicated fetching** — one `.info` lookup and one price-history pair
  per report feed the profile, metrics, quote, chart, performance table, and
  quant model, minimizing rate-limit exposure on the keyless data source.
- **Quota-safe validation** — invalid tickers are rejected by one cheap lookup
  before any rate-limited API is touched.

---

## Understanding the Quant Score

The **Evaluation** section is the heart of the report. It distills five
independent, academically-grounded measures of a company into a single
**0–100 composite score**. Here's how to read it.

### What the number means

Each factor is scored **0–100 as a percentile rank against the S&P 500** —
the same way institutional factor shops (AQR-style) score stocks. A factor
score of 87 means *"this company ranks higher than ~87% of its sector peers
in the S&P 500 on this measure."* The composite is the sector-weighted
average of those five percentile ranks, and every factor shows its
percentile right on the report (e.g. *"Gross Profitability: 91st pctile"*).

Ranking details:

- Stocks are ranked against their **own sector cohort** (e.g. the ~80
  Technology names in the index); small sectors fall back to the full index.
  The report always states the exact benchmark used.
- "Lower is better" factors (accruals, volatility) are inverted so **100 is
  always good**.
- The ranking universe comes from a **local factor snapshot** of the S&P 500
  built by `backend/build_universe.py` (see below). If the snapshot is
  missing or more than 30 days old, the model falls back to fixed reference
  thresholds and says so in the methodology line on the report.

A rough reading guide:

| Score | Reading |
|---|---|
| **75–100** | Top quartile of its sector on the weighted factor mix |
| **50–74** | Above the sector median — solid but not elite |
| **25–49** | Below the sector median on most weighted factors |
| **0–24** | Bottom quartile — expensive, weak, volatile, or dirty earnings vs. peers |

The score is a **research starting point, not a buy/sell signal.** It looks
only at the five factors below and is blind to everything else (management,
industry disruption, macro, valuation nuance, one-off events).

### What each factor measures

| Factor | In plain English | Scores high when… | Grounded in |
|---|---|---|---|
| **Earnings Yield** (EBIT/EV) | How much operating profit you get for the company's total price (debt included). The inverse of a P/E-style multiple. | The company is **cheaper** relative to its profits than its sector peers | Greenblatt, *Magic Formula* |
| **12-1 Momentum** | The stock's price trend over the past year, ignoring the most recent month (which tends to reverse). | The stock has been **trending up harder** than its sector peers | Jegadeesh & Titman (1993) |
| **Gross Profitability** (GP/Assets) | How much gross profit the company squeezes from its asset base — a clean measure of business quality. | The company is **more productive** with its assets than its sector peers | Novy-Marx (2013) |
| **Accruals** (Sloan) | How much of reported earnings is backed by **actual cash** vs. accounting estimates. *Lower is better.* | Earnings are **better backed by cash flow** than peers' (a warning fires if income runs far ahead of cash) | Sloan (1996) |
| **Idiosyncratic Volatility** | How jumpy the stock is beyond what the broad market explains — a risk measure. *Lower is better.* | The stock is **steadier** than its sector peers | Ang, Hodrick, Xing & Zhang (2006) |

### Why the weights shift by sector

The five factors don't matter equally in every industry, so the model
**re-weights them by sector**. A high-growth software company is judged more
on profitability and momentum; a utility is judged more on cheapness and
earnings quality. For example:

| Sector | Leans most on | Rationale |
|---|---|---|
| **Technology** | Gross profitability, momentum | Growth and asset efficiency drive returns |
| **Utilities** | Earnings yield, accruals | Regulated, capital-heavy — value and clean books matter |
| **Financial Services** | Earnings yield, momentum | Gross profit isn't meaningful for banks (weighted to zero) |
| **Healthcare** | Momentum, volatility | Pipeline/catalyst-driven, higher dispersion |

If a factor can't be computed (e.g. a young company with under ~11 months of
price history, or a bank that reports no gross profit), it's **dropped and
the remaining weights rescale** — the score is never silently dragged down by
missing data. Any such adjustment is shown as a ⚠ flag on the report.

### The earnings-quality flag

If a company's reported income runs **far ahead of the cash it actually
generated** (high Sloan accruals — a classic red flag for aggressive
accounting), the badge switches from **PASSED** to **FLAGGED**, the composite
is **capped at 40**, and a warning explains why. This is a caution, not an
accusation — it's exactly the kind of thing a careful analyst double-checks.

### Building the ranking universe

Percentile ranking needs a local factor snapshot of the S&P 500:

```bash
cd backend
python build_universe.py        # ~3-5 minutes, free yfinance data only
```

This computes the five factors for all ~503 constituents (two bulk price
downloads + per-ticker fundamentals) and writes `universe_snapshot.json`.
Notes:

- **Refresh cadence:** run it whenever you like — daily is ideal, weekly is
  fine. Snapshots older than **30 days** are ignored and the model falls
  back to fixed-threshold scoring (clearly stated on the report).
- **Automate it (optional):** on Windows, Task Scheduler → "Create Basic
  Task" → nightly → `python C:\path\to\backend\build_universe.py`.
- **Rate limits:** yfinance may throttle a full run; the builder retries
  missing names after a cooldown and backfills still-missing fundamentals
  from the previous snapshot (annual statements barely move between runs),
  so coverage only improves.
- The constituent list ships with the repo
  (`backend/sp500_constituents.json`, sourced from Wikipedia); the snapshot
  itself is generated locally and git-ignored.

---

## Architecture

```
[Browser]
    │  ticker
    ▼
[Next.js 16 frontend]  :3000
    │  POST /api/report
    ▼
[FastAPI backend]      :8000
    │
    ├─► Data layer (parallel; one .info lookup + one price-history
    │   │            pair shared across every consumer)
    │     ├─ yfinance ─────── fundamentals, calendar, price history
    │     ├─ Alpha Vantage ── news + sentiment  (optional key)
    │     │     └─ fallback: Yahoo Finance headlines (no key)
    │     └─ Quant model ──── 5-factor evaluator, percentile-ranked
    │           └─ universe_snapshot.json (S&P 500 factor snapshot,
    │              built offline by build_universe.py)
    │
    └─► LLM layer
          └─ Gemini (single merged call → Sections 1 & 2,
             validated, retried once, model fallback on quota)
```

---

## Quick start (Windows, one click)

Double-click **`launch.bat`**. It will:

1. Locate Node.js and Python (with install links if missing)
2. Ask for your **free** Gemini API key on first run
   ([get one here](https://aistudio.google.com/apikey) — no credit card)
3. Ask whether to **save** the key (`backend\.env`) or keep it
   **session-only** — session keys live in process memory and wipe
   automatically when the server windows close
4. Install any missing dependencies (first run only)
5. Start both servers and open the app at <http://localhost:3000>

The launcher window stays open while the app runs. **Press any key in it to
stop the app** — it shuts both servers down and, if a key is saved on disk,
asks whether to **wipe it** on the way out (default: keep).

## Manual setup

**Prerequisites:** Python 3.12+ · Node.js 20.9+

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # add your keys (see Configuration)
python -m uvicorn main:app --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

---

## Configuration

All configuration is via environment variables (or `backend/.env`).
See [backend/.env.example](backend/.env.example).

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | **Yes** | Google Gemini key for report generation. Free at [AI Studio](https://aistudio.google.com/apikey). |
| `ALPHA_VANTAGE_API_KEY` | No | Adds sentiment-tagged news. Without it, headlines load from Yahoo Finance keylessly. Free at [alphavantage.co](https://www.alphavantage.co/support/#api-key). |
| `GEMINI_MODEL` | No | Override the primary model (default `gemini-2.5-flash`). |
| `NEXT_PUBLIC_API_URL` | No | Frontend → backend base URL (default `http://localhost:8000`). |

---

## Costs & rate limits

**Everything in this project is free.** All libraries are MIT/BSD/Apache
open source, and both external APIs run on free tiers that require **no
credit card** — when a quota is exhausted, requests fail with an error;
you are never billed.

| Service | Free-tier limit | Card required | Overage behavior |
|---|---|---|---|
| Gemini `gemini-2.5-flash` | ~20 requests/day | No | 429 error → app auto-falls back ↓ |
| Gemini `gemini-2.0-flash` (fallback) | ~1,500 requests/day | No | 429 error, no charge |
| Alpha Vantage | 25 requests/day | No | Empty response → Yahoo fallback |
| Yahoo Finance (via `yfinance`) | Unmetered, keyless | No | — |

Each report consumes exactly **1 Gemini request** and **at most 1 Alpha
Vantage request**.

> ⚠️ The only way this project can ever cost money is if you attach a billing
> account to your Google Cloud project yourself. A plain AI Studio key has no
> billing attached — keep it that way and you cannot be charged.

> **Data note:** `yfinance` uses Yahoo Finance's public endpoints, which is
> fine for personal research but not licensed for commercial redistribution.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/report` | Generate a full report. Body: `{"ticker": "NVDA"}` |
| `GET` | `/api/health` | Liveness check |

<details>
<summary>Response shape (<code>POST /api/report</code>)</summary>

```jsonc
{
  "ticker": "NVDA",
  "generated_at": "2026-07-08T21:30:00+00:00",
  "quote": { "price": 204.12, "change": 7.19, "change_pct": 3.65 },
  "chart": { "points": [ { "date": "2025-07-09", "close": 159.34, "spy": 620.45 } ] },  // ~252 daily closes
  "executive_summary": { "company": "...", "sector": "...", "industry": "...", "body": "..." },
  "future_pipeline":   { "earnings_date": "2026-08-27", "body": "..." },
  "evaluation": {
    "metrics": { "trailing_pe": "...", "price_1w": "...", "...": "..." },
    "quant": {
      "status": "PASSED",          // or FLAGGED (earnings-quality warning, score capped) / FAILED
      "composite_score": 78,
      "factor_percentiles": { },   // per-factor sector percentile ranks (percentile mode only)
      "benchmark": "...",          // ranking cohort + snapshot date (percentile mode only)
      "flags": [],                 // data-quality warnings (missing factors, fallbacks)
      "methodology": "...",        // scoring disclosure shown in the UI
      "raw_metrics": { }
    }
  }
}
```

Errors: `400` invalid ticker format · `404` unknown ticker ·
`503` LLM unavailable (bad key or quota).
</details>

---

## Project structure

```
├─ launch.bat                  # One-click Windows launcher
├─ SPEC.md                     # Full product & engineering specification
├─ backend/
│  ├─ main.py                  # FastAPI app — parallel report orchestration
│  ├─ data.py                  # Data aggregation (yfinance, Alpha Vantage, fallback)
│  ├─ llm.py                   # Prompting, validation/retry, model fallback
│  ├─ evaluator.py             # 5-factor quant model (sector percentile ranking)
│  ├─ universe.py              # Snapshot loading + percentile math
│  ├─ build_universe.py        # S&P 500 factor snapshot builder (run nightly)
│  ├─ sp500_constituents.json  # Bundled index constituent list
│  └─ .env.example             # Key template (real .env is git-ignored)
└─ frontend/
   ├─ app/                     # Next.js App Router (landing + /report/[ticker])
   └─ components/              # Report shell + three section renderers
```

---

## Security & privacy

- **Secrets never enter version control.** `.gitignore` blocks `.env` and all
  variants (`.env.*`); only the empty `.env.example` template is committed.
- **Session-only key mode**: decline saving at the launcher prompt and keys
  exist purely as process environment variables — wiped when the server
  windows close, nothing written to disk.
- **Exit-time wipe**: even with a saved key, the launcher offers to delete
  `backend\.env` every time you shut the app down from its window.
- **Keys stay local.** They are sent only to Google / Alpha Vantage over
  HTTPS, never logged, and never returned by any API response.
- CORS is locked to `http://localhost:3000`.

Before publishing a fork, run a final check that nothing sensitive is staged:
`git status` should never list `backend/.env`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Node.js not found" | Install from <https://nodejs.org>, then re-run `launch.bat` |
| Report fails with 503 "API key not valid" | Re-check the key in `backend\.env`, or delete the file and relaunch to be re-prompted |
| Report fails with 503 quota error | Daily Gemini limit reached on both models — wait for the daily reset |
| Port 3000/8000 already in use | Close previous server windows (or any other app on those ports) |
| Empty news section | Normal for thinly covered tickers; both news sources returned nothing |

---

## Roadmap

- [ ] Server-sent events — stream sections to the browser as they complete
- [ ] SEC EDGAR 8-K ingestion for the Future Pipeline section
- [ ] Multi-ticker regression test suite across sectors
- [ ] Structured logging & per-section latency metrics

## License

No license has been selected yet. Until one is added, all rights are
reserved by the authors — choose a license (e.g. MIT) before accepting
external contributions.
