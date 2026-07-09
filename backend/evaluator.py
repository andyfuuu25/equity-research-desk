import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf


class InstitutionalStockEvaluator:

    def __init__(self, benchmark_ticker="^GSPC"):
        self.benchmark_ticker = benchmark_ticker
        self.sector_matrix = {
            "Technology": {
                "weights": {"ey": 0.15, "mom": 0.25, "gp": 0.35, "accruals": 0.15, "idio_vol": 0.10},
                "label": "Asset-Light / High-Growth Dynamic",
            },
            "Healthcare": {
                "weights": {"ey": 0.15, "mom": 0.25, "gp": 0.20, "accruals": 0.15, "idio_vol": 0.25},
                "label": "Catalyst & Pipeline Heavy",
            },
            "Consumer Defensive": {
                "weights": {"ey": 0.35, "mom": 0.15, "gp": 0.20, "accruals": 0.20, "idio_vol": 0.10},
                "label": "Defensive / Cash-Flow Consistency",
            },
            "Utilities": {
                "weights": {"ey": 0.40, "mom": 0.10, "gp": 0.15, "accruals": 0.25, "idio_vol": 0.10},
                "label": "Capital-Intensive / Regulated Value",
            },
            "Energy": {
                "weights": {"ey": 0.35, "mom": 0.15, "gp": 0.25, "accruals": 0.10, "idio_vol": 0.15},
                "label": "Cyclical / Capital Efficiency Focus",
            },
            # gp weight is 0: gross profit is not meaningful for banks/insurers
            "Financial Services": {
                "weights": {"ey": 0.35, "mom": 0.30, "gp": 0.00, "accruals": 0.15, "idio_vol": 0.20},
                "label": "Spread-Income / Momentum Alpha",
            },
        }
        self.base_weights = {
            "weights": {"ey": 0.30, "mom": 0.20, "gp": 0.20, "accruals": 0.15, "idio_vol": 0.15},
            "label": "Standard Cross-Sectional Base",
        }

    def _fetch_financial_row(self, df, possible_labels):
        for label in possible_labels:
            if label in df.index:
                val = df.loc[label].iloc[0]
                if pd.notna(val):
                    return float(val)
        return None

    def evaluate_ticker(self, ticker_symbol):
        ticker = yf.Ticker(ticker_symbol)
        try:
            info = ticker.info
            sector = info.get("sector", "Unknown")
            market_cap = info.get("marketCap")
            ev = info.get("enterpriseValue") or market_cap
        except Exception as e:
            return {"status": "FAILED", "reason": f"API Ingestion Error: {str(e)}"}

        inc_stmt = ticker.financials
        bal_sheet = ticker.balance_sheet
        cash_flow = ticker.cashflow

        if inc_stmt.empty or bal_sheet.empty or cash_flow.empty:
            return {"status": "FAILED", "reason": "Incomplete fundamental statements from data vendor."}

        ebit = self._fetch_financial_row(inc_stmt, ["EBIT", "Operating Income", "OperatingIncome"])
        gross_profit = self._fetch_financial_row(inc_stmt, ["Gross Profit", "GrossProfit"])
        net_income = self._fetch_financial_row(inc_stmt, ["Net Income", "NetIncome"])
        total_assets = self._fetch_financial_row(bal_sheet, ["Total Assets", "TotalAssets"])
        cfo = self._fetch_financial_row(
            cash_flow,
            ["Operating Cash Flow", "Cash Flow From Operating Activities", "CashFlowFromOperatingActivities"],
        )

        # EBIT and Gross Profit are optional (banks/insurers don't report
        # them); their factors are excluded and weights renormalize.
        missing_fields = [
            k for k, v in {
                "Net Income": net_income, "Total Assets": total_assets, "CFO": cfo,
            }.items() if v is None
        ]
        if missing_fields:
            return {"status": "FAILED", "reason": f"Missing accounting variables: {missing_fields}"}

        try:
            hist_stock = ticker.history(period="1y")["Close"]
            hist_bench = yf.Ticker(self.benchmark_ticker).history(period="1y")["Close"]
            combined_returns = pd.concat(
                [hist_stock.pct_change(), hist_bench.pct_change()], axis=1, join="inner"
            ).dropna()
            combined_returns.columns = ["Stock", "Market"]
        except Exception as e:
            return {"status": "FAILED", "reason": f"Historical pricing failure: {str(e)}"}

        flags = []

        # Earnings yield (Greenblatt). Negative EV means cash exceeds market
        # cap — the cheapest configuration possible, not a data failure.
        # Banks report no EBIT, so fall back to NI / market cap there.
        if ebit is None and market_cap and market_cap > 0:
            earnings_yield = net_income / market_cap
            ey_score = float(np.clip(earnings_yield / 0.15, 0, 1) * 100)
            flags.append(
                "EBIT not reported (typical for financials): earnings yield computed as net income / market cap."
            )
        elif ebit is not None and ev and ev > 0:
            earnings_yield = ebit / ev
            ey_score = float(np.clip(earnings_yield / 0.15, 0, 1) * 100)
        elif ebit is not None and ebit > 0:
            earnings_yield = None
            ey_score = 100.0
            flags.append(
                "Negative enterprise value (cash exceeds market cap): earnings yield scored maximal."
            )
        else:
            earnings_yield = None
            ey_score = None
            flags.append("Earnings yield unscorable: factor excluded and weights renormalized.")

        # 12-1 momentum (Jegadeesh-Titman): the ~11-month return from t-12m to
        # t-1m. A short window is a different factor, so score N/A instead.
        if len(hist_stock) >= 230:
            momentum_12_1 = (hist_stock.iloc[-22] / hist_stock.iloc[0]) - 1
            mom_score = float(np.clip((momentum_12_1 + 0.2) / 0.6, 0, 1) * 100)
        else:
            momentum_12_1 = None
            mom_score = None
            flags.append(
                "Momentum N/A: fewer than 230 trading days of history; factor excluded and weights renormalized."
            )

        if gross_profit is not None:
            gross_profitability = gross_profit / total_assets
            gp_score = float(np.clip(gross_profitability / 0.6, 0, 1) * 100)
        else:
            gross_profitability = None
            gp_score = None
            config_gp = self.sector_matrix.get(sector, self.base_weights)["weights"]["gp"]
            if config_gp > 0:
                flags.append(
                    "Gross profit not reported: profitability factor excluded and weights renormalized."
                )

        # Accruals per Sloan (1996): (NI - CFO) / assets. High accruals mean
        # earnings are not backed by cash and predict underperformance.
        accruals_ratio = (net_income - cfo) / total_assets
        acc_score = float(np.clip((0.15 - accruals_ratio) / 0.2, 0, 1) * 100)

        try:
            Y = combined_returns["Stock"]
            X = sm.add_constant(combined_returns["Market"])
            ols_model = sm.OLS(Y, X).fit()
            idiosyncratic_vol = np.sqrt(ols_model.ssr / (len(Y) - 2)) * np.sqrt(252)
        except Exception:
            idiosyncratic_vol = combined_returns["Stock"].std() * np.sqrt(252)
            flags.append(
                "Market-model regression unavailable: total volatility substituted for idiosyncratic volatility (conservative)."
            )
        idio_score = float(np.clip((0.40 - idiosyncratic_vol) / 0.30, 0, 1) * 100)

        config = self.sector_matrix.get(sector, self.base_weights)
        weights = config["weights"]
        regime_label = config["label"]

        # Composite over available factors only; weights renormalize so a
        # missing factor never silently drags the score.
        factor_scores = {
            "ey": ey_score,
            "mom": mom_score,
            "gp": gp_score,
            "accruals": acc_score,
            "idio_vol": idio_score,
        }
        scored = {k: v for k, v in factor_scores.items() if v is not None and weights[k] > 0}
        weight_sum = sum(weights[k] for k in scored)
        if not scored or weight_sum == 0:
            return {"status": "FAILED", "reason": "No scorable factors for this ticker."}
        weighted_score = sum(weights[k] * v for k, v in scored.items()) / weight_sum

        # High-accruals warning (Sloan's effect is a tilt, not a veto):
        # cap the composite and surface the flag instead of rejecting.
        status = "PASSED"
        if accruals_ratio > 0.15:
            status = "FLAGGED"
            weighted_score = min(weighted_score, 40.0)
            flags.append(
                f"Earnings-quality warning: accruals ratio {accruals_ratio:+.4f} — net income exceeds operating cash flow "
                "by more than 15% of total assets (Sloan 1996). Composite capped at 40."
            )

        def _fmt(v):
            return round(v, 4) if v is not None else "N/A"

        return {
            "status": status,
            "sector": sector,
            "regime_applied": regime_label,
            "composite_score": round(weighted_score, 2),
            "allocation_weights": weights,
            "flags": flags,
            "methodology": (
                "Factors scored against fixed reference thresholds, not peer-ranked. "
                "Accruals follow Sloan (1996): lower is better."
            ),
            "raw_metrics": {
                "Earnings Yield (EBIT/EV)": _fmt(earnings_yield),
                "12-1 Trailing Momentum": _fmt(momentum_12_1),
                "Gross Profitability (GP/Assets)": _fmt(gross_profitability),
                "Accruals Ratio (Sloan)": _fmt(accruals_ratio),
                "Idiosyncratic Volatility (Annualized)": _fmt(idiosyncratic_vol),
            },
        }
