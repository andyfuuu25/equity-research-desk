"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ExecutiveSummary from "./ExecutiveSummary";
import FuturePipeline from "./FuturePipeline";
import Evaluation from "./Evaluation";
import ThemeToggle from "./ThemeToggle";
import PriceChart, { type ChartPoint } from "./PriceChart";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Quote {
  price: number;
  change: number;
  change_pct: number;
}

interface ReportData {
  ticker: string;
  generated_at: string;
  quote: Quote | null;
  chart: { points: ChartPoint[] } | null;
  executive_summary: {
    company: string;
    ticker: string;
    sector: string;
    industry: string;
    body: string;
  };
  future_pipeline: { earnings_date: string; body: string };
  evaluation: Parameters<typeof Evaluation>[0]["data"];
}

type State =
  | { phase: "loading" }
  | { phase: "error"; message: string; retriable: boolean }
  | { phase: "ready"; data: ReportData };

export default function Report({ ticker }: { ticker: string }) {
  const [state, setState] = useState<State>({ phase: "loading" });

  const generate = useCallback(async (signal?: AbortSignal) => {
    setState({ phase: "loading" });
    try {
      const res = await fetch(`${API_BASE}/api/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
        signal,
      });
      if (!res.ok) {
        const detail = await res
          .json()
          .then((j) => j.detail as string)
          .catch(() => `Request failed (${res.status})`);
        setState({
          phase: "error",
          message: detail,
          // 4xx = bad ticker (retry won't help); 5xx = transient upstream issue
          retriable: res.status >= 500,
        });
        return;
      }
      const data = (await res.json()) as ReportData;
      setState({ phase: "ready", data });
    } catch (e) {
      if (signal?.aborted) return;
      setState({
        phase: "error",
        message:
          "Could not reach the research service. Confirm the backend is running.",
        retriable: true,
      });
    }
  }, [ticker]);

  useEffect(() => {
    const controller = new AbortController();
    generate(controller.signal);
    return () => controller.abort();
  }, [generate]);

  return (
    <main className="mx-auto max-w-3xl px-6 pb-24">
      <Masthead
        ticker={ticker}
        company={state.phase === "ready" ? state.data.executive_summary.company : undefined}
        sector={state.phase === "ready" ? state.data.executive_summary.sector : undefined}
        generatedAt={state.phase === "ready" ? state.data.generated_at : undefined}
        quote={state.phase === "ready" ? state.data.quote : null}
      />

      {state.phase === "loading" && <ReportSkeleton />}

      {state.phase === "error" && (
        <div className="mt-16 rounded-lg border border-loss-dim bg-ink-800 px-6 py-8 text-center">
          <p className="text-[11px] uppercase tracking-[0.3em] text-loss">
            Report Unavailable
          </p>
          <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-paper-dim">
            {state.message}
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            {state.retriable && (
              <button
                onClick={() => generate()}
                className="rounded-md border border-gold-dim bg-ink-700 px-5 py-2 text-xs font-semibold uppercase tracking-wider text-gold transition-colors hover:bg-ink-600"
              >
                Retry Generation
              </button>
            )}
            <Link
              href="/"
              className="rounded-md border border-line-strong px-5 py-2 text-xs font-semibold uppercase tracking-wider text-paper-dim transition-colors hover:text-paper"
            >
              New Search
            </Link>
          </div>
        </div>
      )}

      {state.phase === "ready" && (
        <div className="mt-10 space-y-12">
          {state.data.chart && state.data.chart.points.length > 1 && (
            <PriceChart ticker={ticker} points={state.data.chart.points} />
          )}
          <ExecutiveSummary data={state.data.executive_summary} />
          <SectionRule />
          <FuturePipeline data={state.data.future_pipeline} />
          <SectionRule />
          <Evaluation data={state.data.evaluation} />
          <footer className="border-t border-line pt-6 text-[11px] leading-relaxed text-paper-mute">
            Generated {formatTimestamp(state.data.generated_at)} from live
            market data, filings-adjacent news, and a five-factor quantitative
            model. This material is produced by an automated system for
            research purposes only and does not constitute investment advice
            or a recommendation to buy or sell any security.
          </footer>
        </div>
      )}
    </main>
  );
}

function Masthead({
  ticker,
  company,
  sector,
  generatedAt,
  quote,
}: {
  ticker: string;
  company?: string;
  sector?: string;
  generatedAt?: string;
  quote?: Quote | null;
}) {
  const changeTone =
    quote && quote.change > 0
      ? "text-gain"
      : quote && quote.change < 0
      ? "text-loss"
      : "text-paper-dim";

  return (
    <header className="sticky top-0 z-10 -mx-6 border-b border-line bg-ink-950/95 px-6 pb-4 pt-5 backdrop-blur">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <Link
            href="/"
            className="text-[10px] uppercase tracking-[0.3em] text-gold transition-colors hover:text-paper"
          >
            ← Equity Research Desk
          </Link>
          <div className="mt-1 flex items-baseline gap-3">
            <h1 className="tnum font-display text-3xl tracking-tight text-paper">
              {ticker}
            </h1>
            {company && (
              <span className="truncate text-sm text-paper-dim">{company}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-end gap-4">
          {quote && (
            <div className="text-right">
              <p className="text-2xl font-semibold leading-none text-paper">
                ${quote.price.toFixed(2)}
              </p>
              <p className={`tnum mt-1 font-mono text-xs ${changeTone}`}>
                {quote.change >= 0 ? "+" : ""}
                {quote.change.toFixed(2)} ({quote.change_pct >= 0 ? "+" : ""}
                {quote.change_pct.toFixed(2)}%)
              </p>
            </div>
          )}
          <div className="text-right text-[11px] leading-5 text-paper-mute">
            {sector && <p>{sector}</p>}
            {generatedAt && <p className="tnum">{formatTimestamp(generatedAt)}</p>}
          </div>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

function SectionRule() {
  return <div className="masthead-rule w-full" />;
}

function ReportSkeleton() {
  return (
    <div className="mt-10 space-y-12" aria-label="Generating report">
      <p className="text-center text-[11px] uppercase tracking-[0.3em] text-gold">
        Generating research profile — typically 10–30 seconds
      </p>
      {[3, 4, 5].map((rows, s) => (
        <section key={s} className="space-y-3">
          <div className="skeleton h-5 w-44" />
          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="skeleton h-4"
              style={{ width: `${92 - i * 9}%` }}
            />
          ))}
        </section>
      ))}
    </div>
  );
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
