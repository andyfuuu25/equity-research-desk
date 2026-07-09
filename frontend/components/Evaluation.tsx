interface EvaluationMetrics {
  trailing_pe: string;
  price_to_sales: string;
  ev_to_ebitda: string;
  fcf_yield: string;
  debt_to_equity: string;
  revenue_growth: string;
  gross_margin: string;
  net_margin: string;
  price_1w: string;
  price_1m: string;
  price_3m: string;
  price_ytd: string;
  spy_1w: string;
  spy_1m: string;
  spy_3m: string;
  spy_ytd: string;
  recommendation: string;
  target_mean: string;
  target_high: string;
  target_low: string;
  num_analysts: string;
  short_float: string;
  news_sentiment: string;
}

interface QuantResult {
  status: "PASSED" | "FLAGGED" | "FAILED";
  sector?: string;
  regime_applied?: string;
  composite_score?: number;
  allocation_weights?: Record<string, number>;
  raw_metrics?: Record<string, number | string>;
  factor_percentiles?: Record<string, number>;
  benchmark?: string;
  flags?: string[];
  methodology?: string;
  reason?: string;
}

/** 1 -> "1st", 82 -> "82nd", etc. */
function ordinal(n: number) {
  const rem10 = n % 10;
  const rem100 = n % 100;
  if (rem10 === 1 && rem100 !== 11) return `${n}st`;
  if (rem10 === 2 && rem100 !== 12) return `${n}nd`;
  if (rem10 === 3 && rem100 !== 13) return `${n}rd`;
  return `${n}th`;
}

const FACTOR_SOURCES: Record<string, string> = {
  "Earnings Yield (EBIT/EV)": "Greenblatt",
  "12-1 Trailing Momentum": "Jegadeesh & Titman 1993",
  "Gross Profitability (GP/Assets)": "Novy-Marx 2013",
  "Accruals Ratio (Sloan)": "Sloan 1996",
  "Idiosyncratic Volatility (Annualized)": "Ang et al. 2006",
};

interface EvaluationData {
  metrics: EvaluationMetrics;
  quant: QuantResult;
}

interface Props {
  data: EvaluationData;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-paper-mute">
        {label}
      </p>
      <p className="tnum mt-1 font-mono text-sm text-paper">{value}</p>
    </div>
  );
}

function MetricGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-ink-900 px-5 py-4">
      <p className="mb-4 text-[10px] font-semibold uppercase tracking-[0.25em] text-gold">
        {title}
      </p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        {children}
      </div>
    </div>
  );
}

function PerfCell({
  label,
  stock,
  spy,
}: {
  label: string;
  stock: string;
  spy: string;
}) {
  const tone = (v: string) =>
    v.startsWith("+")
      ? "text-gain"
      : v.startsWith("-")
      ? "text-loss"
      : "text-paper-dim";
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-paper-mute">
        {label}
      </p>
      <p className={`tnum mt-1 font-mono text-sm font-medium ${tone(stock)}`}>
        {stock}
      </p>
      <p className="tnum mt-0.5 font-mono text-[11px] text-paper-mute">
        SPY {spy}
      </p>
    </div>
  );
}

function QuantBadge({ quant }: { quant: QuantResult }) {
  const frame =
    quant.status === "PASSED"
      ? "border-gain-dim"
      : quant.status === "FLAGGED"
      ? "border-gold-dim"
      : "border-line-strong";
  const statusTone =
    quant.status === "PASSED"
      ? "text-gain"
      : quant.status === "FLAGGED"
      ? "text-gold"
      : "text-paper-mute";

  return (
    <div className={`rounded-lg border bg-ink-900 px-5 py-4 ${frame}`}>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.25em] text-paper-mute">
            Institutional Quant Model
          </p>
          <p className={`mt-1 text-sm font-semibold ${statusTone}`}>
            {quant.status === "PASSED" && (quant.regime_applied ?? "Passed")}
            {quant.status === "FLAGGED" &&
              `${quant.regime_applied ?? "Scored"} — Earnings Quality Flag`}
            {quant.status === "FAILED" && "Insufficient data for scoring"}
          </p>
          {quant.status === "FAILED" && quant.reason && (
            <p className="mt-1 max-w-md text-xs leading-relaxed text-paper-dim">
              {quant.reason}
            </p>
          )}
        </div>
        {quant.status !== "FAILED" && quant.composite_score !== undefined && (
          <div className="shrink-0 text-right">
            <p className={`tnum font-mono text-4xl font-bold ${statusTone}`}>
              {quant.composite_score}
            </p>
            <p className="text-[10px] uppercase tracking-widest text-paper-mute">
              Composite / 100
            </p>
          </div>
        )}
      </div>

      {quant.flags && quant.flags.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-line pt-3">
          {quant.flags.map((f) => (
            <li key={f} className="text-xs leading-relaxed text-gold">
              ⚠ {f}
            </li>
          ))}
        </ul>
      )}

      {quant.raw_metrics && (
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-5">
          {Object.entries(quant.raw_metrics).map(([key, val]) => {
            const pct = quant.factor_percentiles?.[key];
            return (
              <div key={key} title={FACTOR_SOURCES[key]}>
                <p className="text-[10px] uppercase leading-tight tracking-wider text-paper-mute">
                  {key
                    .replace(" (EBIT/EV)", "")
                    .replace(" (GP/Assets)", "")
                    .replace(" (Annualized)", "")}
                </p>
                <p className="tnum mt-1 font-mono text-sm text-paper">{val}</p>
                {pct !== undefined && (
                  <p className="tnum mt-0.5 font-mono text-[11px] font-semibold text-gold">
                    {ordinal(pct)} pctile
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {quant.benchmark && (
        <p className="mt-3 text-[11px] leading-relaxed text-paper-dim">
          Percentiles vs. {quant.benchmark} (100 = best). Factor pedigree:{" "}
          {Object.values(FACTOR_SOURCES).join(" · ")}.
        </p>
      )}

      {quant.methodology && (
        <p className="mt-2 text-[11px] leading-relaxed text-paper-mute">
          {quant.methodology}
        </p>
      )}
    </div>
  );
}

/** Horizontal bar showing where the average PT sits inside the analyst range. */
function TargetRange({ m }: { m: EvaluationMetrics }) {
  const parse = (s: string) => {
    const n = Number(s.replace(/[$,]/g, ""));
    return Number.isFinite(n) ? n : null;
  };
  const low = parse(m.target_low);
  const high = parse(m.target_high);
  const mean = parse(m.target_mean);
  if (low === null || high === null || mean === null || high <= low) return null;

  const pct = Math.min(100, Math.max(0, ((mean - low) / (high - low)) * 100));

  return (
    <div className="mt-4 border-t border-line pt-4">
      <div className="flex justify-between text-[10px] uppercase tracking-widest text-paper-mute">
        <span className="tnum">Low {m.target_low}</span>
        <span className="tnum text-paper-dim">Avg {m.target_mean}</span>
        <span className="tnum">High {m.target_high}</span>
      </div>
      <div className="relative mt-2 h-1 rounded bg-ink-600">
        <div
          className="absolute -top-[3px] h-[10px] w-[3px] rounded-sm bg-gold"
          style={{ left: `calc(${pct}% - 1px)` }}
        />
      </div>
    </div>
  );
}

export default function Evaluation({ data }: Props) {
  if (!data) return null;
  const { metrics: m, quant } = data;

  return (
    <section>
      <header className="mb-5">
        <p className="text-[10px] uppercase tracking-[0.3em] text-gold">
          Section 03
        </p>
        <h2 className="mt-1 font-display text-2xl tracking-tight text-paper">
          Evaluation
        </h2>
        <p className="mt-1 text-xs text-paper-mute">
          Financial health, valuation, and quantitative scoring
        </p>
      </header>

      <div className="space-y-4">
        <QuantBadge quant={quant} />

        <MetricGroup title="Valuation">
          <Metric label="P/E (TTM)" value={m.trailing_pe} />
          <Metric label="P/S (TTM)" value={m.price_to_sales} />
          <Metric label="EV/EBITDA" value={m.ev_to_ebitda} />
          <Metric label="FCF Yield" value={m.fcf_yield} />
        </MetricGroup>

        <MetricGroup title="Growth & Profitability">
          <Metric label="Revenue Growth" value={m.revenue_growth} />
          <Metric label="Gross Margin" value={m.gross_margin} />
          <Metric label="Net Margin" value={m.net_margin} />
          <Metric label="Debt / Equity" value={m.debt_to_equity} />
        </MetricGroup>

        <MetricGroup title="Price Performance vs S&P 500">
          <PerfCell label="1 Week" stock={m.price_1w} spy={m.spy_1w} />
          <PerfCell label="1 Month" stock={m.price_1m} spy={m.spy_1m} />
          <PerfCell label="3 Months" stock={m.price_3m} spy={m.spy_3m} />
          <PerfCell label="YTD" stock={m.price_ytd} spy={m.spy_ytd} />
        </MetricGroup>

        <div className="rounded-lg border border-line bg-ink-900 px-5 py-4">
          <p className="mb-4 text-[10px] font-semibold uppercase tracking-[0.25em] text-gold">
            Market Sentiment
          </p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
            <Metric label="Analyst Rating" value={m.recommendation} />
            <Metric
              label={`Avg PT (${m.num_analysts} analysts)`}
              value={m.target_mean}
            />
            <Metric label="Short Interest" value={m.short_float} />
            <Metric label="News Sentiment" value={m.news_sentiment} />
          </div>
          <TargetRange m={m} />
        </div>
      </div>
    </section>
  );
}
