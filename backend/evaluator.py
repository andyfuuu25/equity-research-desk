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
            "Financial Services": {
                "weights": {"ey": 0.30, "mom": 0.30, "gp": 0.10, "accruals": 0.10, "idio_vol": 0.20},
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
            ev = info.get("enterpriseValue") or info.get("marketCap")
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

        missing_fields = [
            k for k, v in {
                "EBIT": ebit, "Gross Profit": gross_profit, "Net Income": net_income,
                "Total Assets": total_assets, "CFO": cfo, "EV": ev,
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

        earnings_yield = ebit / ev if ev > 0 else 0

        if len(hist_stock) > 22:
            momentum_12_1 = (hist_stock.iloc[-22] / hist_stock.iloc[0]) - 1
        else:
            momentum_12_1 = 0

        gross_profitability = gross_profit / total_assets
        accruals_ratio = (cfo - net_income) / total_assets

        try:
            Y = combined_returns["Stock"]
            X = sm.add_constant(combined_returns["Market"])
            ols_model = sm.OLS(Y, X).fit()
            idiosyncratic_vol = np.sqrt(ols_model.ssr / (len(Y) - 2)) * np.sqrt(252)
        except Exception:
            idiosyncratic_vol = combined_returns["Stock"].std() * np.sqrt(252)

        if accruals_ratio > 0.15:
            return {
                "status": "REJECTED",
                "sector": sector,
                "reason": f"Failed Accruals Hygiene Gatekeeper. Accruals Ratio of {accruals_ratio:.4f} exceeds threshold (+0.15). Earnings quality compromised.",
                "raw_metrics": {
                    "Earnings Yield (EBIT/EV)": round(earnings_yield, 4),
                    "12-1 Trailing Momentum": round(momentum_12_1, 4),
                    "Gross Profitability (GP/Assets)": round(gross_profitability, 4),
                    "Accruals Ratio": round(accruals_ratio, 4),
                    "Idiosyncratic Volatility (Annualized)": round(idiosyncratic_vol, 4),
                },
            }

        config = self.sector_matrix.get(sector, self.base_weights)
        weights = config["weights"]
        regime_label = config["label"]

        ey_score = np.clip(earnings_yield / 0.15, 0, 1) * 100
        mom_score = np.clip((momentum_12_1 + 0.2) / 0.6, 0, 1) * 100
        gp_score = np.clip(gross_profitability / 0.6, 0, 1) * 100
        acc_score = np.clip((0.15 - accruals_ratio) / 0.2, 0, 1) * 100
        idio_score = np.clip((0.40 - idiosyncratic_vol) / 0.30, 0, 1) * 100

        weighted_score = (
            weights["ey"] * ey_score
            + weights["mom"] * mom_score
            + weights["gp"] * gp_score
            + weights["accruals"] * acc_score
            + weights["idio_vol"] * idio_score
        )

        return {
            "status": "PASSED",
            "sector": sector,
            "regime_applied": regime_label,
            "composite_score": round(weighted_score, 2),
            "allocation_weights": weights,
            "raw_metrics": {
                "Earnings Yield (EBIT/EV)": round(earnings_yield, 4),
                "12-1 Trailing Momentum": round(momentum_12_1, 4),
                "Gross Profitability (GP/Assets)": round(gross_profitability, 4),
                "Accruals Ratio": round(accruals_ratio, 4),
                "Idiosyncratic Volatility (Annualized)": round(idiosyncratic_vol, 4),
            },
        }
