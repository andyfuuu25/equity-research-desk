# Stock Analysis Platform — MVP Project Specification

**Version:** 0.1 (Draft)
**Date:** 2026-05-20
**Team:** 3 contributors

---

## 1. Problem Statement

Retail and semi-professional investors lack a fast way to generate a structured, up-to-date profile of a US-listed company. Existing tools are either too shallow (price + chart), too expensive (Bloomberg/FactSet), or require deep manual research across many sources. This platform solves that by letting a user enter a ticker and immediately receive a dynamically-generated, analyst-style profile.

---

## 2. MVP Goal

Deliver a working web interface where a user types a US stock ticker (e.g. `NVDA`) and receives a live-generated report with three structured sections:

1. **Executive Summary** — what the company does and how it makes money
2. **Future Pipeline** — upcoming catalysts, projects, and recent news
3. **Evaluation** — financial metrics, risk factors, and sentiment signals

The profile must be generated on-demand from live data sources. Nothing is pre-stored or cached beyond what is needed for rate-limit management.

---

## 3. Out of Scope for MVP

- User accounts / authentication
- Saved reports or report history
- Portfolio tracking or watchlists
- Non-US equities, ETFs, or crypto
- PDF/export functionality
- Mobile-native app (responsive web is sufficient)
- Proprietary data feeds (no Bloomberg, no paid APIs in v1)

---

## 4. System Architecture Overview

```
[User Browser]
     |
     v
[Frontend — React/Next.js]
     |  (ticker input + rendered report)
     v
[Backend API — FastAPI / Node.js]
     |
     +---> [Data Aggregator Layer]
     |         |-- Yahoo Finance / Financial Modeling Prep API (price, financials)
     |         |-- SEC EDGAR API (filings: 10-K, 10-Q, 8-K)
     |         |-- NewsAPI / Alpha Vantage News (headlines, sentiment)
     |
     +---> [LLM Orchestration Layer]
               |-- Prompt builder (structures retrieved data into prompts)
               |-- Anthropic Claude API (claude-sonnet-4-6)
               |-- Section parsers (strips and validates LLM output)
```

### Key Principle: Dynamic Generation

Every profile request triggers a fresh data fetch + LLM generation. There is no pre-built company database. This means:

- Price and financial metrics are always current
- News and catalysts reflect today's context
- The profile degrades gracefully if a data source is unavailable (section renders with a warning rather than blocking the whole report)

---

## 5. The Three Report Sections

### 5.1 Executive Summary

**Purpose:** A 3-paragraph plain-English overview of the company written for a beginner investor.

**Data inputs (all from `yfinance .info` — single call, no extra API):**
- `longName`, `sector`, `industry` — company identity
- `longBusinessSummary` — Yahoo Finance description
- `marketCap`, `totalRevenue`, `revenueGrowth` — scale and trajectory
- `grossMargins`, `profitMargins` — margin profile
- `freeCashflow` — cash generation
- `fullTimeEmployees` — operational scale
- `beta` — market volatility character

**LLM task:** Write three paragraphs: (1) what the business does, (2) how it makes money referencing the financial figures, (3) competitive character based on what the numbers suggest. Explain financial terms in plain language for beginners.

**Output format:**
```
[Paragraph 1: What the business does and the markets it serves]
[Paragraph 2: Revenue model, margin profile, and scale with actual figures]
[Paragraph 3: Competitive character — cash generation, growth, volatility]
```

**Implementation notes:**
- Temperature: 0.3
- All financial figures pre-formatted in `data.py` before reaching LLM (e.g. `$451.4B`, `47.9%`)

---

### 5.2 Future Pipeline

**Purpose:** Surface what is coming — near-term events, projects, and news that could move the stock.

**Data inputs:**
- Up to 15 deduplicated news articles from **Alpha Vantage `NEWS_SENTIMENT`** endpoint
  - Filtered to articles where `ticker_sentiment[relevance_score] >= 0.3`
  - Deduplicated by title (same story syndicated across sources removed)
  - Fields passed to LLM per article: `title`, `summary`, `date`, `source`, `overall_sentiment_label`, `topics` (where topic `relevance_score >= 0.5`)
  - Fields used for filtering only (not passed to LLM): `relevance_score`
- Upcoming earnings date from **`yfinance .calendar`**

**LLM task:** Classify each relevant article into one of three buckets. Articles not directly about the company (e.g. ETF comparisons) are excluded by the LLM. If no articles fit a bucket, output "None identified." under that heading.

- **Confirmed Catalysts** — specific events with a known date or confirmed announcement
- **Developing Stories** — ongoing situations without resolution yet
- **Risk Events** — negative developments that could hurt the company

**Output format:**
```
Upcoming Earnings: [date]

Confirmed Catalysts:
- [item]: [plain-English description]

Developing Stories:
- [item]: [plain-English description]

Risk Events:
- [item]: [plain-English description]
```

**Implementation notes:**
- Temperature: 0.2 (lower than Section 1 — classification task benefits from more deterministic output)
- Empty bucket handling: always render all three headings; "None identified." rendered in italic gray in the frontend
- AV free tier: 25 req/day — one call per report generation

---

### 5.3 Evaluation

**Purpose:** Give the user a structured view of the company's financial health, market sentiment, and a quantitative institutional score.

**Data inputs — all from `yfinance`, no additional API key:**
- Valuation ratios: P/E (TTM), P/S (TTM), EV/EBITDA, FCF yield (freeCashflow / marketCap), debt/equity — from `yfinance .info`
- Growth & profitability: revenue growth YoY, gross margin, net margin — from `yfinance .info`
- Price performance: 1W, 1M, 3M, YTD vs. SPY — from `yfinance .history(period="1y")`
- Analyst consensus: rating, avg/high/low price target, # analysts — from `yfinance .info`
- Short interest (% float shorted) — from `yfinance .info`
- News sentiment: aggregated from Alpha Vantage articles already fetched for Section 2 (no extra API call)

**Quantitative model (`evaluator.py` — `InstitutionalStockEvaluator`):**
- Scores the stock 0–100 using 5 factor pillars: Earnings Yield (EBIT/EV, Greenblatt), 12-1 Trailing Momentum (Jegadeesh-Titman), Gross Profitability (GP/Assets, Novy-Marx 2013), Accruals Ratio ((NI − CFO)/Assets, Sloan 1996 — lower is better), Idiosyncratic Volatility (OLS residual vs. S&P 500)
- Sector-shifting weights: factor weights adjust based on detected GICS sector (6 sector configurations + base fallback); Financial Services carries zero gross-profitability weight (banks report no gross profit)
- Missing or unscorable factors (short price history, unreported EBIT/GP, negative EV) are excluded with a visible flag and the remaining weights renormalize — missing data is never silently scored
- Banks/insurers without EBIT fall back to Net Income / Market Cap for earnings yield (flagged)
- Earnings-quality warning: if Sloan accruals > +0.15 (net income far ahead of operating cash flow), status becomes FLAGGED and the composite is capped at 40 — a tilt with a warning banner, not a veto
- Returns: `status` (PASSED / FLAGGED / FAILED), `composite_score`, `regime_applied`, `raw_metrics`, `allocation_weights`, `flags`, `methodology`
- Scores use fixed reference thresholds (not peer-ranked percentiles); this is disclosed in the UI via the `methodology` string
- Data fetched independently by the evaluator via yfinance (financials, balance sheet, cashflow, price history)

**LLM task:** None — Section 3 does not use LLM generation. All output is derived directly from data.

**Output format (rendered as structured UI, not LLM text):**
```
[Quant score badge: PASSED score/100 | FLAGGED capped score + warnings | FAILED]
[Factor metrics row: Earnings Yield | 12-1 Momentum | Gross Profitability | Accruals (Sloan) | Idio Vol]

Valuation:        P/E | P/S | EV/EBITDA | FCF Yield
Growth:           Revenue Growth | Gross Margin | Net Margin | Debt/Equity
Price Performance: 1W / 1M / 3M / YTD vs SPY
Market Sentiment: Analyst Rating | Avg PT | Short Interest | News Sentiment
```

---

## 6. LLM Integration & Prompt Engineering

### 6.1 Model

Use **Gemini 2.5 Flash** (`gemini-2.5-flash`) via the Google GenAI SDK (`google-genai`). Chosen over Claude/Anthropic because it provides a free tier with no credit card required.

> **⚠️ Rate limit note:** Gemini 2.5 Flash free tier is capped at **20 RPD** (requests per day). With 2 LLM calls per report (Sections 1 & 2), this allows ~10 reports/day. For sustained testing, switch to `gemini-2.0-flash` (~1,500 RPD free) — same SDK, 1-line model string change. Model switch is pending as of the last session.

> **Note:** The original spec called for Claude Sonnet 4.6. If the project moves to paid tiers, Claude Sonnet 4.6 remains the preferred alternative — it was the original design target.

> **Note:** Section 3 (Evaluation) does not use LLM. It renders structured data and the quantitative model output directly.

### 6.2 Prompt Architecture

Each section uses a separate, independently-called prompt. This approach:
- Makes sections independently testable
- Allows section-level retries without regenerating the full report
- Lets you swap or update one section's prompt without breaking others

**Prompt structure for each section:**

```
SYSTEM:
You are a professional equity research analyst. Your job is to produce clear,
structured, factual summaries from the data provided. Do not speculate beyond
the data. If data is missing, acknowledge the gap rather than fabricating.
Write for a financially literate but non-expert audience.

USER:
[Section-specific instructions]

DATA:
[Structured data block — passed as a formatted string or JSON]

OUTPUT FORMAT:
[Exact format specification as defined in Section 5 above]
```

### 6.3 Prompt Engineering Guidelines

| Principle | Implementation |
|---|---|
| Ground every claim | All LLM assertions must cite data passed in the prompt. System prompt explicitly forbids fabrication. |
| Format enforcement | Specify exact output format in the prompt. Post-process with a parser that validates expected fields are present. |
| Graceful degradation | If a data field is null/unavailable, pass `"N/A"` and instruct the model to note the gap. |
| Tone consistency | System prompt sets analyst voice. User prompts do not override this. |
| Token efficiency | Pass only the fields each section needs. Don't pass full financial statements if you only need 6 ratios. |
| Hallucination guard | For the Future Pipeline section, explicitly instruct: "Only include events or stories supported by the provided news items and filings. Do not generate hypothetical catalysts." |

### 6.4 Prompt Caching

Anthropic prompt caching is not applicable with the current Gemini implementation. If the project migrates to Claude, enable prompt caching on the system prompt and static instruction blocks — the data block (which changes per request) should not be cached.

---

## 7. Data Layer

### 7.1 Data Sources (Free/Low-Cost Tier)

| Source | Data | API | Status |
|---|---|---|---|
| Yahoo Finance (via `yfinance`) | Company info, financials, calendar, price history, analyst data, short interest | Python library | ✅ Active — Sections 1, 2 & 3 |
| Alpha Vantage | News + sentiment | REST (free tier: 25 req/day) | ✅ Active — Section 2 (sentiment reused in Section 3) |
| Financial Modeling Prep | Ratios, analyst estimates | REST (free tier: 250 req/day) | ❌ Not used — yfinance covers all Section 3 needs |
| SEC EDGAR | 10-K, 10-Q, 8-K full text | EDGAR EFTS REST API (free) | ⬜ Planned — Section 2 enhancement |
| NewsAPI | General news headlines | REST (free tier: 100 req/day) | ⬜ Deferred — AV covers current need |

### 7.2 Data Aggregator Contract

The aggregator layer returns a single `CompanyDataBundle` object per ticker:

```python
@dataclass
class CompanyDataBundle:
    ticker: str
    fetched_at: datetime

    # Section 1 inputs
    company_info: dict          # name, description, sector, industry
    revenue_segments: list[str]

    # Section 2 inputs
    news_headlines: list[dict]  # {title, date, source, url}
    recent_filings: list[dict]  # {type, date, summary_url}
    earnings_date: str | None

    # Section 3 inputs
    financial_ratios: dict      # pe, ps, ev_ebitda, margins, growth
    price_performance: dict     # 1w, 1m, 3m, ytd vs SPX
    analyst_consensus: dict     # rating, avg_pt, buy/hold/sell counts
    short_interest: float | None
    news_sentiment_score: float | None
```

Any field that fails to fetch is set to `None`. The prompt builder handles `None` fields by substituting `"N/A"`.

---

## 8. Frontend

### 8.1 Pages

- `/` — Landing page with ticker search bar
- `/report/[ticker]` — Report page, streamed section by section

### 8.2 UX Flow

1. User enters ticker → client validates format (1–5 uppercase letters)
2. POST `/api/report` with `{ ticker }` → server starts data fetch + LLM generation
3. Sections stream back as they complete (SSE or chunked response)
4. Each section renders as it arrives — user sees the report building live
5. At top of report: ticker, company name, price, last-updated timestamp

### 8.3 Error States

- Invalid ticker → inline validation error before submission
- Data source failure → section renders with `[Data unavailable — [source] did not respond]`
- LLM failure → section renders with `[Report generation failed — retry]` button

---

## 9. Backend API

### 9.1 Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/report` | Trigger full report generation for a ticker |
| GET | `/api/report/{ticker}/status` | Poll generation status (for non-streaming fallback) |
| GET | `/api/health` | Health check |

### 9.2 Report Generation Flow

```
POST /api/report { ticker: "NVDA" }
  1. Validate ticker format
  2. Fetch CompanyDataBundle (parallel calls to all data sources)
  3. Build prompts for Section 1, 2, 3 (independent)
  4. Call Claude API for each section (can be parallelized)
  5. Parse and validate LLM responses
  6. Stream sections to client as they complete
  7. Log generation metadata (ticker, duration, section success/fail flags)
```

---

## 10. Team & Module Ownership

| Module | Owner | Description |
|---|---|---|
| Data Aggregator | Contributor 1 | All third-party data fetching, `CompanyDataBundle` assembly |
| LLM Orchestration | Contributor 2 | Prompt builder, Claude API calls, response parsers |
| Frontend + API | Contributor 3 (you) | Next.js frontend, FastAPI routes, streaming logic |

Each module has a clearly defined interface (the `CompanyDataBundle` dataclass is the contract between the data layer and the LLM layer). Modules are developed and tested independently before integration.

---

## 11. Development Workflow

### Phase 0 — Alignment
- [x] Finalize this spec (all three contributors review and sign off)
- [x] Agree on tech stack (Python/FastAPI backend, Next.js frontend)
- [x] Set up shared repo, branching strategy (feature branches → main), and environment variables management

### Phase 1 — Skeleton ✅ Complete
- [x] Scaffold project structure (`backend/`, `frontend/`)
- [x] `GET /api/health` endpoint returns 200
- [x] Frontend renders a search bar that POSTs to the backend
- [x] End-to-end flow confirmed working

### Phase 2 — Data Layer ✅ Complete
- [x] `fetch_company_info()` — yfinance `.info` (Section 1 fields)
- [x] `fetch_pipeline_data()` — Alpha Vantage NEWS_SENTIMENT + yfinance calendar (Section 2 fields)
- [x] `fetch_evaluation_data()` — yfinance `.info` + price history vs SPY (Section 3 fields)
- [x] `_fetch_price_performance()` — 1W/1M/3M/YTD returns vs SPY from yfinance history
- [x] `_compute_news_sentiment()` — aggregates AV article sentiment labels (reuses Section 2 data)
- [x] `InstitutionalStockEvaluator` (`evaluator.py`) — 5-factor quant model, sector-shifting weights, 0–100 score
- [ ] SEC EDGAR 8-K fetcher (Section 2 enhancement)

### Phase 3 — LLM Layer (Partial)
- [x] `generate_executive_summary()` — Gemini 2.5 Flash, temp 0.3, beginner-friendly tone
- [x] `generate_future_pipeline()` — Gemini 2.5 Flash, temp 0.2, 3-bucket classification
- [x] Gemini API error handling — 503/429 caught and returned as HTTP 503 instead of crashing server
- [x] Section 3 uses no LLM — quant model + structured data only (decision made in session 3)
- [ ] Response validation / retry logic

### Phase 4 — Integration & Streaming (Partial)
- [x] Sections 1 & 2 wired end-to-end through `/api/report`
- [x] Section 3 wired end-to-end through `/api/report`
- [x] All three sections confirmed working for multiple tickers
- [ ] SSE streaming so frontend receives sections progressively as they generate
- [ ] End-to-end test with 5 tickers across different sectors
- [ ] Resolve Gemini RPD limit — switch to higher-quota model (pending)

### Phase 5 — Internal Testing & Refinement
- [ ] All three contributors generate reports for 10–15 tickers
- [ ] Document failures, hallucinations, and data gaps
- [ ] Refine prompts, fix data source issues, improve error states
- [ ] Peer-review prompt quality: are the outputs accurate? analyst-grade?

### Phase 6 — Polish & Formalize
- [ ] Update this spec to reflect changes from internal testing
- [ ] Add logging and basic observability (track which data sources failed, LLM latency per section)
- [ ] Finalize frontend design (typography, layout, colors)
- [ ] Write a CONTRIBUTING.md for onboarding contributors in later phases

---

## 12. Non-Functional Requirements

| Requirement | Target |
|---|---|
| End-to-end report generation time | < 30 seconds (P90) |
| LLM cost per report | < $0.05 per report (at Sonnet pricing) |
| Data source failures handled | Any single source failure must not block report generation |
| Ticker validation | Reject malformed input before any API call |
| API key security | All keys in environment variables, never hardcoded or committed |

---

## 13. Key Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM hallucination (fabricated metrics or events) | Medium | System prompt constraints + grounding data in prompt + human QA during Phase 5 |
| Free-tier API rate limits hit during testing | High | **Hit in session 3:** Gemini 2.5 Flash RPD limit (20/day) exhausted during testing. Fix: switch to `gemini-2.0-flash` (1,500 RPD). Alpha Vantage 25 req/day also a constraint for heavy testing. |
| SEC EDGAR full-text too long for prompt | Medium | Extract only the "Business" section from 10-K, not the full filing |
| LLM output format deviates from spec | Medium | Response parser validates structure; if validation fails, retry once, then fall back to raw output |
| Data staleness (intraday price moves) | Low | Timestamp every `CompanyDataBundle`; display fetch time to user |

---

## 14. Success Criteria for MVP

The MVP is complete when:

1. A user can enter any S&P 500 ticker and receive all three report sections within 30 seconds
2. Each section contains factually grounded content (verified against source data during internal QA)
3. The report handles at least one missing data source gracefully without crashing
4. All three contributors have reviewed and agreed on the output quality
5. The codebase is modular enough that any single module (data, LLM, frontend) can be changed without touching the others

---

*Next step: Distribute this spec to all three contributors for review. Annotate disagreements inline before Phase 0 closes.*

---

## Addendum — Implementation deviations (v0.2, 2026-07-08)

The following decisions supersede the sections above where they conflict:

1. **Single merged LLM call** (supersedes §6.2). Sections 1 and 2 are
   generated in one Gemini request separated by a sentinel and split
   server-side (`llm.generate_report_sections`). Rationale: free-tier quotas
   are request-per-day capped, so halving calls doubles daily report
   capacity. Per-section retry independence was consciously traded away;
   format validation + one full retry (§6.3) compensates.
2. **Model strategy** (supersedes §6.1 rate-limit note). Primary
   `gemini-2.5-flash` with automatic fallback to `gemini-2.0-flash` on
   quota/availability errors. Override via `GEMINI_MODEL`.
3. **Keyless news fallback** (extends §5.2 / §7.1). When Alpha Vantage is
   unavailable, rate-limited, or fully filtered, Section 2 sources headlines
   from Yahoo Finance via `yfinance` (no key). Fallback articles carry no
   sentiment labels; the aggregate news-sentiment metric reports `N/A`
   rather than a fabricated Neutral.
4. **Earnings-date guarantee** (extends §5.2). A known upcoming earnings
   date is deterministically inserted as a Confirmed Catalyst in
   post-processing when the model leaves that bucket empty.
5. **Parallel orchestration** (implements §9.2). Ticker existence is
   validated first (protects quotas), then news / evaluation / quant run
   concurrently and the LLM call starts as soon as news data lands.
6. **One-click launcher** (new). `launch.bat` provisions keys (saved or
   session-only), installs missing dependencies, and starts both servers.
7. **Section 3 remains LLM-free**, rendered as structured UI (unchanged,
   reaffirmed).

## Addendum — Quant model corrections (v0.3, 2026-07-09)

A five-advisor council review of the evaluation math (peer-reviewed,
unanimous verdict) drove the following corrections to `evaluator.py`:

1. **Accruals sign flipped to Sloan (1996) convention.** The ratio was
   previously computed as (CFO − NI)/Assets — the *negative* of Sloan's
   measure — so the gatekeeper rejected high-quality cash converters and
   perfect-scored accrual-inflated earnings. Now (NI − CFO)/Assets: high
   accruals (income not backed by cash) score low, strong cash conversion
   scores high.
2. **Gatekeeper demoted from veto to flag.** Sloan's effect is a mild
   decile tilt and yfinance CFO fields are noisy, so a hard REJECT was
   unjustifiable. High accruals (> +0.15) now return `status: "FLAGGED"`
   with the composite capped at 40 and a visible warning banner.
3. **Missing data is never silently scored.** Momentum with < 230 trading
   days, unreported EBIT/GP, or unscorable earnings yield now exclude the
   factor, renormalize the remaining weights, display `N/A`, and add a flag
   (previously momentum silently defaulted to 0 → a fabricated score of 33).
4. **Edge guards.** Negative enterprise value (cash > market cap) scores
   earnings yield maximal instead of zero; banks without EBIT fall back to
   NI/MktCap (flagged); the total-volatility fallback for a failed OLS is
   flagged; Financial Services carries zero gross-profitability weight.
5. **Honest labeling.** Every response carries a `methodology` disclosure:
   factors are scored against fixed reference thresholds, not peer-ranked
   percentiles.

**Backlog (council-recommended upgrade):** replace fixed anchors with
cross-sectional percentile ranks against a cached S&P 500 factor snapshot
(nightly yfinance pull), displayed as "Xth percentile vs. sector" with
academic citations. *Implemented in v0.4 — see below.*

## Addendum — Cross-sectional percentile ranking (v0.4, 2026-07-09)

The council's remaining recommendation is implemented:

1. **Factor snapshot** (`build_universe.py`). Computes the same five factors
   for all ~503 S&P 500 constituents: two bulk price downloads (momentum,
   idiosyncratic vol) plus threaded per-ticker fundamentals mirroring the
   evaluator's rules (NI/MktCap fallback for banks). Writes
   `universe_snapshot.json` (git-ignored). Resilient to yfinance throttling:
   cooldown retry pass + backfill of still-missing fundamentals from the
   previous snapshot. Constituents bundled in `sp500_constituents.json`
   (Wikipedia-sourced, GICS→yfinance sector mapping for fallback).
2. **Percentile scoring** (`universe.py` + `evaluator.py`). With a fresh
   snapshot (≤30 days), each factor is scored as a midrank percentile
   against the stock's yfinance-sector cohort (min 20 names, else full
   index). Lower-is-better factors (accruals, idio vol) are inverted so 100
   is always good. The composite is the renormalized sector-weighted blend
   of percentiles; the FLAGGED accruals cap still applies. Missing/stale
   snapshot → fixed-threshold fallback, stated in the `methodology` string.
3. **API additions**: `factor_percentiles` (display-key → 0-100 rank) and
   `benchmark` (cohort description with snapshot date), only present in
   percentile mode.
4. **UI**: each factor cell shows "Nth pctile" under the raw value, with a
   benchmark caption and factor pedigree line (Greenblatt · Jegadeesh &
   Titman 1993 · Novy-Marx 2013 · Sloan 1996 · Ang et al. 2006).

Known limits (disclosed by design): yfinance snapshots are not
point-in-time and carry survivorship bias; fundamentals mix statement dates
across the universe. Acceptable for a research tool; noted here rather than
hidden.
