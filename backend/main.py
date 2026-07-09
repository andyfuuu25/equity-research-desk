import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from data import (
    fetch_company_info,
    fetch_pipeline_data,
    fetch_evaluation_data,
    fetch_price_bundle,
    compute_news_sentiment,
)
from llm import generate_report_sections
from evaluator import InstitutionalStockEvaluator

_evaluator = InstitutionalStockEvaluator()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class ReportRequest(BaseModel):
    ticker: str


def validate_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t.isalpha() or not (1 <= len(t) <= 5):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    return t


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/report")
async def generate_report(request: ReportRequest):
    ticker = validate_ticker(request.ticker)

    # Validate ticker existence FIRST (one cheap yfinance call) so an invalid
    # ticker never burns the Alpha Vantage daily quota or an LLM request. The
    # raw info dict rides along and feeds the evaluation metrics and the quant
    # model, so .info is fetched exactly once per report.
    company_info = await asyncio.to_thread(fetch_company_info, ticker)
    if company_info is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")
    raw_info = company_info.pop("_info")

    # Remaining fetches are blocking I/O — run them in worker threads, in
    # parallel, so latency is the max of the branches, not their sum (§9.2).
    pipeline_task = asyncio.create_task(asyncio.to_thread(fetch_pipeline_data, ticker))
    price_task = asyncio.create_task(asyncio.to_thread(fetch_price_bundle, ticker))

    # Pure shaping of the already-fetched info — no network, no thread.
    eval_data = fetch_evaluation_data(raw_info)

    # The quant model reuses the shared info dict and the price bundle's close
    # series (its only other needs are the annual statements, fetched inside).
    price_bundle = await price_task
    quant_task = asyncio.create_task(
        asyncio.to_thread(
            _evaluator.evaluate_ticker,
            ticker,
            raw_info,
            price_bundle["_closes"],
            price_bundle["_spy_closes"],
        )
    )

    # The LLM call needs pipeline data — start it the moment that arrives,
    # while the quant branch is still running.
    pipeline_data = await pipeline_task
    llm_task = asyncio.create_task(
        asyncio.to_thread(generate_report_sections, company_info, pipeline_data)
    )

    quant_result = await quant_task
    # News sentiment reuses the already-fetched articles (no extra API call);
    # price performance reuses the bundle's history download.
    eval_data["news_sentiment"] = compute_news_sentiment(pipeline_data["articles"])
    perf = price_bundle["performance"]
    eval_data.update({
        "price_1w": perf.get("1w", "N/A"),
        "price_1m": perf.get("1m", "N/A"),
        "price_3m": perf.get("3m", "N/A"),
        "price_ytd": perf.get("ytd", "N/A"),
        "spy_1w": perf.get("spy_1w", "N/A"),
        "spy_1m": perf.get("spy_1m", "N/A"),
        "spy_3m": perf.get("spy_3m", "N/A"),
        "spy_ytd": perf.get("spy_ytd", "N/A"),
    })

    try:
        # Single Gemini call produces both sections — halves requests/day usage.
        summary, pipeline = await llm_task
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": price_bundle["quote"],
        "chart": price_bundle["chart"],
        "executive_summary": {
            "company": company_info["company"],
            "ticker": ticker,
            "sector": company_info["sector"],
            "industry": company_info["industry"],
            "body": summary,
        },
        "future_pipeline": {
            "earnings_date": pipeline_data["earnings_date"],
            "body": pipeline,
        },
        "evaluation": {
            "metrics": eval_data,
            "quant": quant_result,
        },
    }
