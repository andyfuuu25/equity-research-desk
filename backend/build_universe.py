"""Build the S&P 500 factor-universe snapshot for percentile ranking.

Computes the same five factors the evaluator uses — earnings yield,
12-1 momentum, gross profitability, Sloan accruals, idiosyncratic
volatility — for every S&P 500 constituent, and writes them to
``universe_snapshot.json``. Run it manually or on a schedule (e.g. Windows
Task Scheduler, nightly); the app falls back to fixed-threshold scoring
whenever the snapshot is missing or older than 30 days.

Usage:
    python build_universe.py [--limit N] [--workers N]

Free data only (yfinance). A full run makes ~4 requests per ticker for
fundamentals plus two bulk price downloads; expect 5-15 minutes.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONSTITUENTS_PATH = os.path.join(BASE_DIR, "sp500_constituents.json")
SNAPSHOT_PATH = os.path.join(BASE_DIR, "universe_snapshot.json")

# Wikipedia ships GICS sector names; yfinance uses its own. Cohorts are
# matched on yfinance sectors, so map the GICS names for fallback only.
GICS_TO_YF = {
    "Information Technology": "Technology",
    "Health Care": "Healthcare",
    "Financials": "Financial Services",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials",
    "Energy": "Energy",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Materials": "Basic Materials",
}


def load_constituents(limit=None):
    with open(CONSTITUENTS_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    rows = doc["constituents"][:limit] if limit else doc["constituents"]
    # yfinance wants dashes for class shares (BRK.B -> BRK-B)
    return [(r["symbol"].replace(".", "-"), r["sector"]) for r in rows]


def fetch_row(df, labels):
    for label in labels:
        if label in df.index:
            val = df.loc[label].iloc[0]
            if pd.notna(val):
                return float(val)
    return None


def price_factors(symbols):
    """Momentum and idiosyncratic vol for all symbols from two bulk downloads."""
    closes = yf.download(
        symbols, period="1y", auto_adjust=True, progress=False, threads=True
    )["Close"]
    if isinstance(closes, pd.Series):  # single-symbol runs
        closes = closes.to_frame(symbols[0])
    # SPY, matching the evaluator's market-model benchmark, so snapshot and
    # single-name idiosyncratic vol are computed against the same series.
    bench = yf.download("SPY", period="1y", auto_adjust=True, progress=False)[
        "Close"
    ].squeeze()
    bench_ret = bench.pct_change().dropna()

    out = {}
    for sym in closes.columns:
        series = closes[sym].dropna()
        mom = None
        if len(series) >= 230:
            mom = float(series.iloc[-22] / series.iloc[0] - 1)

        idio = None
        ret = series.pct_change().dropna()
        joined = pd.concat([ret, bench_ret], axis=1, join="inner").dropna()
        if len(joined) >= 60:
            y, x = joined.iloc[:, 0].values, joined.iloc[:, 1].values
            beta = np.cov(x, y)[0, 1] / np.var(x)
            resid = y - (y.mean() - beta * x.mean()) - beta * x
            idio = float(np.sqrt((resid**2).sum() / (len(y) - 2)) * np.sqrt(252))
        out[sym] = {"mom": mom, "idio_vol": idio}
    return out


def fundamental_factors(symbol, gics_sector):
    """Earnings yield, gross profitability, and Sloan accruals for one ticker.

    Mirrors evaluator.py's rules (NI/MktCap fallback for banks, EBIT/EV
    otherwise) so percentile comparisons are like-for-like.
    """
    t = yf.Ticker(symbol)
    try:
        info = t.info
        sector = info.get("sector") or GICS_TO_YF.get(gics_sector, gics_sector)
        market_cap = info.get("marketCap")
        ev = info.get("enterpriseValue") or market_cap

        inc, bal, cf = t.financials, t.balance_sheet, t.cashflow
        ebit = fetch_row(inc, ["EBIT", "Operating Income", "OperatingIncome"])
        gross_profit = fetch_row(inc, ["Gross Profit", "GrossProfit"])
        net_income = fetch_row(inc, ["Net Income", "NetIncome"])
        total_assets = fetch_row(bal, ["Total Assets", "TotalAssets"])
        cfo = fetch_row(
            cf,
            [
                "Operating Cash Flow",
                "Cash Flow From Operating Activities",
                "CashFlowFromOperatingActivities",
            ],
        )

        ey = None
        if ebit is not None and ev and ev > 0:
            ey = ebit / ev
        elif net_income is not None and market_cap and market_cap > 0:
            ey = net_income / market_cap

        gp = None
        if gross_profit is not None and total_assets:
            gp = gross_profit / total_assets

        accruals = None
        if net_income is not None and cfo is not None and total_assets:
            accruals = (net_income - cfo) / total_assets

        return {"sector": sector, "ey": ey, "gp": gp, "accruals": accruals}
    except Exception:
        return {"sector": GICS_TO_YF.get(gics_sector, gics_sector), "ey": None, "gp": None, "accruals": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="build a partial universe (testing)")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    constituents = load_constituents(args.limit)
    symbols = [s for s, _ in constituents]
    print(f"Building factor snapshot for {len(symbols)} constituents...")

    t0 = time.time()
    print("Bulk price download (momentum + idiosyncratic vol)...")
    prices = price_factors(symbols)

    print(f"Fundamentals with {args.workers} workers...")
    factors = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for (sym, _), fund in zip(
            constituents,
            pool.map(lambda c: fundamental_factors(*c), constituents),
        ):
            factors[sym] = {**fund, **prices.get(sym, {"mom": None, "idio_vol": None})}
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(symbols)} ({time.time() - t0:.0f}s)")

    # Rate-limited names come back with no fundamentals at all (ey and
    # accruals both None). Retry them once after a cooldown, gently.
    missing = [
        (sym, gics)
        for sym, gics in constituents
        if factors[sym]["ey"] is None and factors[sym]["accruals"] is None
    ]
    if missing and len(missing) < len(symbols):
        print(f"Retrying {len(missing)} rate-limited names after a 60s cooldown...")
        time.sleep(60)
        with ThreadPoolExecutor(max_workers=3) as pool:
            for (sym, _), fund in zip(
                missing, pool.map(lambda c: fundamental_factors(*c), missing)
            ):
                if fund["ey"] is not None or fund["accruals"] is not None:
                    factors[sym].update(fund)

    # Fundamentals are annual statements — they barely move between runs.
    # Backfill any still-missing values from the previous snapshot so a
    # rate-limited run never degrades coverage.
    if os.path.exists(SNAPSHOT_PATH):
        try:
            with open(SNAPSHOT_PATH, encoding="utf-8") as f:
                previous = json.load(f)["factors"]
            filled = 0
            for sym, cur in factors.items():
                old = previous.get(sym)
                if not old:
                    continue
                for key in ("ey", "gp", "accruals"):
                    if cur[key] is None and old.get(key) is not None:
                        cur[key] = old[key]
                        filled += 1
            if filled:
                print(f"Backfilled {filled} fundamental values from the previous snapshot.")
        except (OSError, ValueError, KeyError):
            pass

    complete = sum(
        1 for f in factors.values() if all(f[k] is not None for k in ("ey", "mom", "gp", "accruals", "idio_vol"))
    )
    snapshot = {
        "as_of": date.today().isoformat(),
        "count": len(factors),
        "complete": complete,
        "factors": factors,
    }
    tmp = SNAPSHOT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)
    os.replace(tmp, SNAPSHOT_PATH)
    print(
        f"Wrote {SNAPSHOT_PATH}: {len(factors)} names, {complete} with all five factors, "
        f"{time.time() - t0:.0f}s total."
    )


if __name__ == "__main__":
    sys.exit(main())
