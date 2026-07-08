"use client";

import { useMemo, useRef, useState } from "react";

export interface ChartPoint {
  date: string;
  close: number;
  spy: number | null;
}

interface Props {
  ticker: string;
  points: ChartPoint[];
}

const RANGES = [
  { label: "1M", days: 22 },
  { label: "3M", days: 64 },
  { label: "6M", days: 127 },
  { label: "1Y", days: Infinity },
] as const;

type RangeLabel = (typeof RANGES)[number]["label"];

// Plot geometry (viewBox units; the SVG scales to its container)
const W = 720;
const H = 240;
const PAD = { top: 12, right: 14, bottom: 24, left: 52 };
const PW = W - PAD.left - PAD.right;
const PH = H - PAD.top - PAD.bottom;

/** Round the value axis to clean steps (1/2/2.5/5 × 10^n). */
function niceScale(min: number, max: number, ticks = 4) {
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  const rawStep = span / ticks;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const step =
    [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= rawStep) ?? 10 * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const values: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) values.push(v);
  return { lo, hi, values };
}

const fmtDollar = (v: number) =>
  v >= 1000 ? `$${(v / 1000).toFixed(1)}K` : `$${v.toFixed(v < 10 ? 2 : 0)}`;
const fmtPct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`;
const fmtDateShort = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
const fmtDateLong = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export default function PriceChart({ ticker, points }: Props) {
  const [range, setRange] = useState<RangeLabel>("3M");
  const [overlay, setOverlay] = useState(false);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const sliced = useMemo(() => {
    const days = RANGES.find((r) => r.label === range)!.days;
    return days === Infinity ? points : points.slice(-days);
  }, [points, range]);

  const model = useMemo(() => {
    if (sliced.length < 2) return null;

    // Overlay mode indexes both series to 0% at range start (one axis rule:
    // $ price and SPY level are different scales, so compare % change).
    const baseClose = sliced[0].close;
    const firstSpy = sliced.find((p) => p.spy !== null)?.spy ?? null;

    const stockVals = sliced.map((p) =>
      overlay ? (p.close / baseClose - 1) * 100 : p.close
    );
    const spyVals = overlay
      ? sliced.map((p) =>
          p.spy !== null && firstSpy ? (p.spy / firstSpy - 1) * 100 : null
        )
      : [];

    const all = [...stockVals, ...spyVals.filter((v): v is number => v !== null)];
    const scale = niceScale(Math.min(...all), Math.max(...all));

    const x = (i: number) => PAD.left + (i / (sliced.length - 1)) * PW;
    const y = (v: number) =>
      PAD.top + PH - ((v - scale.lo) / (scale.hi - scale.lo)) * PH;

    const path = (vals: (number | null)[]) =>
      vals
        .map((v, i) =>
          v === null ? "" : `${i === 0 || vals[i - 1] === null ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`
        )
        .join("");

    // Area wash under the stock line (series hue at ~10% opacity)
    const area =
      path(stockVals) +
      `L${x(sliced.length - 1).toFixed(1)},${(PAD.top + PH).toFixed(1)}` +
      `L${PAD.left},${(PAD.top + PH).toFixed(1)}Z`;

    // ~4 x-axis labels, evenly spaced
    const xTickIdx = [0, 1, 2, 3].map((k) =>
      Math.round((k / 3) * (sliced.length - 1))
    );

    return { stockVals, spyVals, scale, x, y, path, area, xTickIdx };
  }, [sliced, overlay]);

  if (!model || sliced.length < 2) return null;

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current!.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * W;
    const frac = (vx - PAD.left) / PW;
    const idx = Math.round(frac * (sliced.length - 1));
    setHoverIdx(Math.max(0, Math.min(sliced.length - 1, idx)));
  }

  const hover = hoverIdx !== null ? sliced[hoverIdx] : null;
  const lastIdx = sliced.length - 1;

  return (
    <section className="rounded-lg border border-line bg-ink-900 px-5 py-4">
      {/* Controls — one row above the plot */}
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setRange(r.label)}
              aria-pressed={range === r.label}
              className={`tnum rounded px-2.5 py-1 font-mono text-xs transition-colors ${
                range === r.label
                  ? "border border-gold-dim bg-ink-700 text-gold"
                  : "border border-line bg-ink-800 text-paper-dim hover:text-paper"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setOverlay(!overlay)}
          aria-pressed={overlay}
          className={`rounded px-2.5 py-1 text-xs transition-colors ${
            overlay
              ? "border border-gold-dim bg-ink-700 text-gold"
              : "border border-line bg-ink-800 text-paper-dim hover:text-paper"
          }`}
        >
          vs S&amp;P 500
        </button>
      </div>

      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="block w-full"
          onPointerMove={onMove}
          onPointerLeave={() => setHoverIdx(null)}
        >
          {/* Gridlines — hairline, recessive */}
          {model.scale.values.map((v) => (
            <g key={v}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={model.y(v)}
                y2={model.y(v)}
                stroke="var(--color-line)"
                strokeWidth="1"
              />
              <text
                x={PAD.left - 8}
                y={model.y(v) + 3}
                textAnchor="end"
                className="tnum"
                fontSize="10"
                fill="var(--color-paper-mute)"
              >
                {overlay ? fmtPct(v) : fmtDollar(v)}
              </text>
            </g>
          ))}

          {/* X-axis date labels */}
          {model.xTickIdx.map((i, k) => (
            <text
              key={i}
              x={model.x(i)}
              y={H - 6}
              textAnchor={k === 0 ? "start" : k === 3 ? "end" : "middle"}
              fontSize="10"
              fill="var(--color-paper-mute)"
            >
              {fmtDateShort(sliced[i].date)}
            </text>
          ))}

          {/* Area wash (price mode only) */}
          {!overlay && (
            <path d={model.area} fill="var(--color-series-stock)" opacity="0.1" />
          )}

          {/* SPY overlay line */}
          {overlay && (
            <path
              d={model.path(model.spyVals)}
              fill="none"
              stroke="var(--color-series-spy)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}

          {/* Stock line */}
          <path
            d={model.path(model.stockVals)}
            fill="none"
            stroke="var(--color-series-stock)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* End dot with surface ring */}
          <circle
            cx={model.x(lastIdx)}
            cy={model.y(model.stockVals[lastIdx])}
            r="4"
            fill="var(--color-series-stock)"
            stroke="var(--color-ink-900)"
            strokeWidth="2"
          />

          {/* Crosshair + hover dots */}
          {hoverIdx !== null && (
            <g>
              <line
                x1={model.x(hoverIdx)}
                x2={model.x(hoverIdx)}
                y1={PAD.top}
                y2={PAD.top + PH}
                stroke="var(--color-line-strong)"
                strokeWidth="1"
              />
              <circle
                cx={model.x(hoverIdx)}
                cy={model.y(model.stockVals[hoverIdx])}
                r="4"
                fill="var(--color-series-stock)"
                stroke="var(--color-ink-900)"
                strokeWidth="2"
              />
              {overlay && model.spyVals[hoverIdx] !== null && (
                <circle
                  cx={model.x(hoverIdx)}
                  cy={model.y(model.spyVals[hoverIdx] as number)}
                  r="4"
                  fill="var(--color-series-spy)"
                  stroke="var(--color-ink-900)"
                  strokeWidth="2"
                />
              )}
            </g>
          )}
        </svg>

        {/* Tooltip — values lead, line keys carry identity */}
        {hover && hoverIdx !== null && (
          <div
            className="pointer-events-none absolute top-2 z-10 rounded border border-line bg-ink-800 px-3 py-2 shadow-lg"
            style={{
              left: `${(model.x(hoverIdx) / W) * 100}%`,
              transform:
                model.x(hoverIdx) > W / 2 ? "translateX(-108%)" : "translateX(10%)",
            }}
          >
            <p className="mb-1 text-[10px] uppercase tracking-wider text-paper-mute">
              {fmtDateLong(hover.date)}
            </p>
            <p className="flex items-center gap-2">
              <span
                className="inline-block h-[2px] w-3"
                style={{ background: "var(--color-series-stock)" }}
              />
              <span className="tnum font-mono text-sm font-semibold text-paper">
                {overlay
                  ? fmtPct(model.stockVals[hoverIdx])
                  : `$${hover.close.toFixed(2)}`}
              </span>
              <span className="text-[11px] text-paper-dim">{ticker}</span>
            </p>
            {overlay && model.spyVals[hoverIdx] !== null && (
              <p className="mt-0.5 flex items-center gap-2">
                <span
                  className="inline-block h-[2px] w-3"
                  style={{ background: "var(--color-series-spy)" }}
                />
                <span className="tnum font-mono text-sm font-semibold text-paper">
                  {fmtPct(model.spyVals[hoverIdx] as number)}
                </span>
                <span className="text-[11px] text-paper-dim">S&amp;P 500</span>
              </p>
            )}
          </div>
        )}
      </div>

      {/* Legend — only when two series are plotted */}
      {overlay && (
        <div className="mt-2 flex items-center gap-4 text-[11px] text-paper-dim">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-[2px] w-4"
              style={{ background: "var(--color-series-stock)" }}
            />
            {ticker}
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-[2px] w-4"
              style={{ background: "var(--color-series-spy)" }}
            />
            S&amp;P 500 (SPY), indexed
          </span>
        </div>
      )}
    </section>
  );
}
