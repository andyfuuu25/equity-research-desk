import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime


def _fmt_billions(value) -> str:
    """Format a raw number into a readable $XB / $XM string."""
    if value is None:
        return "N/A"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _fmt_pct(value) -> str:
    """Format a 0–1 float as a percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def fetch_company_info(ticker: str) -> dict | None:
    stock = yf.Ticker(ticker)
    info = stock.info

    # yfinance returns a minimal dict with just quoteType if the ticker is invalid
    if not info.get("longName") and not info.get("shortName"):
        return None

    return {
        # Identity
        "company": info.get("longName") or info.get("shortName", ticker),
        "ticker": ticker,
        "sector": info.get("sector") or "N/A",
        "industry": info.get("industry") or "N/A",
        "description": info.get("longBusinessSummary") or "No description available.",
        # Scale
        "market_cap": _fmt_billions(info.get("marketCap")),
        "total_revenue": _fmt_billions(info.get("totalRevenue")),
        "free_cashflow": _fmt_billions(info.get("freeCashflow")),
        "full_time_employees": f"{info.get('fullTimeEmployees', 'N/A'):,}" if info.get("fullTimeEmployees") else "N/A",
        # Growth & margins
        "revenue_growth_yoy": _fmt_pct(info.get("revenueGrowth")),
        "gross_margin": _fmt_pct(info.get("grossMargins")),
        "profit_margin": _fmt_pct(info.get("profitMargins")),
        # Market character
        "beta": str(round(info.get("beta"), 2)) if info.get("beta") else "N/A",
    }


def _fmt_date(raw: str) -> str:
    """Convert AV timestamp 'YYYYMMDDTHHMMSS' to readable 'Month D, YYYY'."""
    try:
        from datetime import datetime
        return datetime.strptime(raw[:8], "%Y%m%d").strftime("%B %d, %Y")
    except Exception:
        return raw[:8]


def _cap_summary(summary: str) -> str:
    """Cap runaway summaries only — typical 1–3 sentence blurbs pass through."""
    if len(summary) > 400:
        return summary[:400].rsplit(" ", 1)[0] + "…"
    return summary


def _fetch_yfinance_news(ticker: str) -> list:
    """Keyless fallback news source: Yahoo Finance headlines via yfinance.

    Used when Alpha Vantage is unavailable (no key, quota exhausted, or all
    articles filtered out) so the Future Pipeline section always has material.
    No sentiment labels or topic tags are available from this source.
    """
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []

    articles = []
    for item in raw:
        content = item.get("content") or item  # tolerate old/new yfinance shapes
        title = content.get("title", "")
        if not title:
            continue

        pub = content.get("pubDate") or content.get("displayTime") or ""
        try:
            date = datetime.fromisoformat(pub.replace("Z", "+00:00")).strftime("%B %d, %Y")
        except Exception:
            date = pub[:10] if pub else "Recent"

        provider = content.get("provider") or {}
        articles.append({
            "title": title,
            "summary": _cap_summary(content.get("summary") or content.get("description") or ""),
            "date": date,
            "source": provider.get("displayName", "Yahoo Finance"),
            "sentiment": "Unlabeled",
            "topics": [],
        })

    # Deduplicate by title and cap, mirroring the Alpha Vantage path
    seen = set()
    unique = [a for a in articles if not (a["title"] in seen or seen.add(a["title"]))]
    return unique[:15]


def fetch_pipeline_data(ticker: str) -> dict:
    """
    Fetch Future Pipeline inputs:
    - Upcoming earnings date from yfinance calendar
    - Recent news articles from Alpha Vantage NEWS_SENTIMENT
      filtered to articles where this ticker has relevance_score >= 0.3
    - Falls back to keyless Yahoo Finance news when AV yields nothing
    """
    # --- Earnings date ---
    try:
        stock = yf.Ticker(ticker)
        calendar = stock.calendar or {}
        earnings_dates = calendar.get("Earnings Date", [])
        earnings_date = str(earnings_dates[0]) if earnings_dates else "Not available"
    except Exception:
        earnings_date = "Not available"

    # --- Alpha Vantage news (primary — has sentiment labels and topic tags) ---
    articles = []
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")

    if not api_key:
        return {
            "earnings_date": earnings_date,
            "articles": _fetch_yfinance_news(ticker),
        }

    try:
        url = (
            "https://www.alphavantage.co/query"
            f"?function=NEWS_SENTIMENT&tickers={ticker}&limit=50&apikey={api_key}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        feed = resp.json().get("feed", [])

        for item in feed:
            # Find the relevance score for this specific ticker
            ticker_sentiment = next(
                (ts for ts in item.get("ticker_sentiment", [])
                 if ts.get("ticker", "").upper() == ticker.upper()),
                None,
            )
            if not ticker_sentiment:
                continue
            relevance = float(ticker_sentiment.get("relevance_score", 0))
            if relevance < 0.3:
                continue

            # Keep only high-relevance topic labels
            topics = [
                t["topic"]
                for t in item.get("topics", [])
                if float(t.get("relevance_score", 0)) >= 0.5
            ]

            articles.append({
                "title": item.get("title", ""),
                "summary": _cap_summary(item.get("summary", "")),
                "date": _fmt_date(item.get("time_published", "")),
                "source": item.get("source", ""),
                "sentiment": item.get("overall_sentiment_label", "Neutral"),
                "topics": topics,
            })

        # Deduplicate by title (same story syndicated across sources)
        seen_titles = set()
        unique_articles = []
        for a in articles:
            if a["title"] not in seen_titles:
                seen_titles.add(a["title"])
                unique_articles.append(a)

        # Cap at 15 per spec — full signal for the classifier. Token savings
        # come from the single merged LLM call and summary caps, not article cuts.
        articles = unique_articles[:15]

    except Exception:
        pass  # Fall through to the keyless fallback below

    # AV can come back empty (quota exhausted, transient error, or every
    # article filtered out by relevance) — never ship an empty Section 2
    # when Yahoo Finance has headlines.
    if not articles:
        articles = _fetch_yfinance_news(ticker)

    return {"earnings_date": earnings_date, "articles": articles}


def fetch_price_bundle(ticker: str) -> dict:
    """One download pair (ticker + SPY, 1y daily) → three consumers.

    Returns ``{"performance": ..., "quote": ..., "chart": ...}`` so the
    relative-performance table, the masthead quote, and the price chart all
    share a single pair of yfinance history calls instead of refetching.
    """
    empty = {"performance": {}, "quote": None, "chart": None}
    try:
        stock_hist = yf.Ticker(ticker).history(period="1y")
        spy_hist = yf.Ticker("SPY").history(period="1y")
        if stock_hist.empty:
            return empty
    except Exception:
        return empty

    def calc_return(hist, n_days):
        if len(hist) < n_days + 1:
            return "N/A"
        pct = ((hist["Close"].iloc[-1] / hist["Close"].iloc[-(n_days + 1)]) - 1) * 100
        return f"{pct:+.1f}%"

    def calc_ytd(hist):
        ytd_start = pd.Timestamp(f"{datetime.now().year}-01-01")
        if hist.index.tz is not None:
            ytd_start = ytd_start.tz_localize(hist.index.tz)
        ytd_data = hist[hist.index >= ytd_start]
        if len(ytd_data) < 2:
            return "N/A"
        pct = ((ytd_data["Close"].iloc[-1] / ytd_data["Close"].iloc[0]) - 1) * 100
        return f"{pct:+.1f}%"

    performance = {
        "1w": calc_return(stock_hist, 5),
        "1m": calc_return(stock_hist, 21),
        "3m": calc_return(stock_hist, 63),
        "ytd": calc_ytd(stock_hist),
    }
    if not spy_hist.empty:
        performance.update({
            "spy_1w": calc_return(spy_hist, 5),
            "spy_1m": calc_return(spy_hist, 21),
            "spy_3m": calc_return(spy_hist, 63),
            "spy_ytd": calc_ytd(spy_hist),
        })

    closes = stock_hist["Close"]
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else last
    quote = {
        "price": round(last, 2),
        "change": round(last - prev, 2),
        "change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
    }

    # Daily closes aligned by date; SPY joined on the stock's trading days so
    # the frontend can index both series to a common base for the overlay.
    spy_by_date = {d.date(): float(c) for d, c in zip(spy_hist.index, spy_hist["Close"])}
    points = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "close": round(float(c), 2),
            "spy": round(spy_by_date[d.date()], 2) if d.date() in spy_by_date else None,
        }
        for d, c in zip(stock_hist.index, closes)
    ]

    return {"performance": performance, "quote": quote, "chart": {"points": points}}


def compute_news_sentiment(articles: list) -> str:
    scores = {
        "Bullish": 2, "Somewhat-Bullish": 1, "Neutral": 0,
        "Somewhat-Bearish": -1, "Bearish": -2,
    }
    # Only score articles that carry a real AV sentiment label — the keyless
    # Yahoo fallback tags articles "Unlabeled", which must not read as Neutral.
    labeled = [a for a in articles if a.get("sentiment") in scores]
    if not labeled:
        return "N/A"
    avg = sum(scores[a["sentiment"]] for a in labeled) / len(labeled)
    if avg > 0.4:
        return "Positive"
    if avg < -0.4:
        return "Negative"
    return "Neutral"


def fetch_evaluation_data(
    ticker: str,
    articles: list | None = None,
    price_perf: dict | None = None,
) -> dict:
    """Valuation/growth/sentiment metrics. ``price_perf`` comes from
    fetch_price_bundle()["performance"] — supplied by the caller so the
    price history is downloaded once per report, not once per consumer."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}

    trailing_pe = info.get("trailingPE")
    price_to_sales = info.get("priceToSalesTrailing12Months")
    ev_to_ebitda = info.get("enterpriseToEbitda")
    fcf = info.get("freeCashflow")
    mktcap = info.get("marketCap")
    fcf_yield = (fcf / mktcap * 100) if (fcf and mktcap) else None
    debt_to_equity = info.get("debtToEquity")
    short_float = info.get("shortPercentOfFloat")
    rec_key = info.get("recommendationKey") or "N/A"
    target_mean = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    target_low = info.get("targetLowPrice")
    num_analysts = info.get("numberOfAnalystOpinions")

    price_perf = price_perf or {}

    return {
        "trailing_pe": f"{trailing_pe:.1f}" if trailing_pe else "N/A",
        "price_to_sales": f"{price_to_sales:.1f}" if price_to_sales else "N/A",
        "ev_to_ebitda": f"{ev_to_ebitda:.1f}" if ev_to_ebitda else "N/A",
        "fcf_yield": f"{fcf_yield:.1f}%" if fcf_yield is not None else "N/A",
        "debt_to_equity": f"{debt_to_equity:.1f}" if debt_to_equity else "N/A",
        "revenue_growth": _fmt_pct(info.get("revenueGrowth")),
        "gross_margin": _fmt_pct(info.get("grossMargins")),
        "net_margin": _fmt_pct(info.get("profitMargins")),
        "price_1w": price_perf.get("1w", "N/A"),
        "price_1m": price_perf.get("1m", "N/A"),
        "price_3m": price_perf.get("3m", "N/A"),
        "price_ytd": price_perf.get("ytd", "N/A"),
        "spy_1w": price_perf.get("spy_1w", "N/A"),
        "spy_1m": price_perf.get("spy_1m", "N/A"),
        "spy_3m": price_perf.get("spy_3m", "N/A"),
        "spy_ytd": price_perf.get("spy_ytd", "N/A"),
        "recommendation": rec_key.replace("_", " ").title() if rec_key != "N/A" else "N/A",
        "target_mean": f"${target_mean:.2f}" if target_mean else "N/A",
        "target_high": f"${target_high:.2f}" if target_high else "N/A",
        "target_low": f"${target_low:.2f}" if target_low else "N/A",
        "num_analysts": str(num_analysts) if num_analysts else "N/A",
        "short_float": f"{short_float * 100:.1f}%" if short_float else "N/A",
        "news_sentiment": compute_news_sentiment(articles or []),
    }
