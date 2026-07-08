"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import ThemeToggle from "../components/ThemeToggle";

const QUICK_PICKS = ["NVDA", "AAPL", "MSFT", "JPM", "XOM", "LLY"];

export default function Landing() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(raw: string) {
    const t = raw.trim().toUpperCase();
    if (!/^[A-Z]{1,5}$/.test(t)) {
      setError("Enter a valid US ticker — 1 to 5 letters.");
      return;
    }
    setError(null);
    router.push(`/report/${t}`);
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6">
      <div className="fixed right-5 top-5">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-xl text-center">
        {/* Masthead */}
        <h1 className="font-display text-5xl tracking-tight text-paper">
          Equity Research Desk
        </h1>
        <div className="masthead-rule mx-auto mt-6 w-48" />
        <p className="mx-auto mt-6 max-w-md text-sm leading-relaxed text-paper-dim">
          Enter a US-listed ticker to generate a live research profile —
          executive summary, forward catalysts, and a quantitative
          institutional evaluation.
        </p>

        {/* Search */}
        <form
          className="mx-auto mt-10 flex max-w-md items-stretch gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit(ticker);
          }}
        >
          <input
            autoFocus
            value={ticker}
            onChange={(e) => {
              setTicker(e.target.value.toUpperCase());
              if (error) setError(null);
            }}
            placeholder="NVDA"
            maxLength={5}
            aria-label="Stock ticker"
            className="tnum w-full rounded-md border border-line-strong bg-ink-800 px-4 py-3 font-mono text-lg uppercase tracking-widest text-paper placeholder:text-paper-mute focus:border-gold focus:outline-none"
          />
          <button
            type="submit"
            className="shrink-0 rounded-md border border-gold-dim bg-ink-700 px-6 font-sans text-sm font-semibold uppercase tracking-wider text-gold transition-colors hover:bg-ink-600"
          >
            Generate
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-loss">{error}</p>}

        {/* Quick picks */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
          <span className="text-[11px] uppercase tracking-widest text-paper-mute">
            Coverage
          </span>
          {QUICK_PICKS.map((t) => (
            <button
              key={t}
              onClick={() => submit(t)}
              className="tnum rounded border border-line bg-ink-800 px-3 py-1 font-mono text-xs text-paper-dim transition-colors hover:border-gold-dim hover:text-gold"
            >
              {t}
            </button>
          ))}
        </div>

        <p className="mt-16 text-[11px] leading-relaxed text-paper-mute">
          Profiles are generated on demand from live market data and news.
          For research purposes only — not investment advice.
        </p>
      </div>
    </main>
  );
}
