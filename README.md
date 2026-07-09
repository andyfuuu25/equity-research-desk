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
| **Evaluation** | Five-factor institutional quant score (0–100) with sector-adaptive weights, valuation ratios, growth metrics, price performance vs. S&P 500, and analyst consensus | Yahoo Finance + in-house quant model (no LLM) |

The report masthead shows the **live share price with day change**, and an
**interactive 1-year price chart** sits above the sections — range toggles
(1M/3M/6M/1Y), an indexed **vs S&P 500** overlay, and a crosshair tooltip.

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
- **Quota-safe validation** — invalid tickers are rejected by one cheap lookup
  before any rate-limited API is touched.

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
    ├─► Data layer (parallel)
    │     ├─ yfinance ─────── fundamentals, calendar, price history
    │     ├─ Alpha Vantage ── news + sentiment  (optional key)
    │     │     └─ fallback: Yahoo Finance headlines (no key)
    │     └─ Quant model ──── 5-factor institutional evaluator
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

The launcher window stays open while the app runs. **Press q to
stop the app** — it shuts both servers down and, if a key is saved on disk,
asks whether to **wipe it** on the way out (default: keep).

## Manual setup

**Prerequisites:** Python 3.12+ · Node.js 20.9+

Get your GEMINI API Key [here](https://aistudio.google.com/apikey) for free.

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        
# Add your keys to the .env (see Configuration)
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

---

## Costs & rate limits

**Everything in this project is free.** All libraries are MIT/BSD/Apache
open source, and both external APIs run on free tiers that require **no
credit card** — when a quota is exhausted, requests fail with an error;
you are never billed.


> ⚠️ The only way this project can ever cost money is if you attach a billing
> account to your Google Cloud project yourself. A plain AI Studio key has no
> billing attached — keep it that way and you cannot be charged.


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
  "executive_summary": { "company": "...", "sector": "...", "industry": "...", "body": "..." },
  "future_pipeline":   { "earnings_date": "2026-08-27", "body": "..." },
  "evaluation": {
    "metrics": { "trailing_pe": "...", "price_1w": "...", "...": "..." },
    "quant":   { "status": "PASSED", "composite_score": 78, "raw_metrics": { } }
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
│  ├─ evaluator.py             # 5-factor institutional quant model
│  └─ .env.example             # Key template (real .env is git-ignored)
└─ frontend/
   ├─ app/                     # Next.js App Router (landing + /report/[ticker])
   └─ components/              # Report shell + three section renderers
```

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

## License
All licenses in this repository are copyrighted by their respective authors.
