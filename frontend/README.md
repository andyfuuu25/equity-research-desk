# Frontend — Equity Research Desk

Next.js 16 (App Router, Turbopack) + React 19 + Tailwind CSS v4.

See the [root README](../README.md) for full setup, configuration, and
architecture. Short version:

```bash
npm install
npm run dev     # http://localhost:3000 (expects the backend on :8000)
```

## Layout

```
app/
├─ layout.tsx               # Root layout + design tokens (globals.css)
├─ page.tsx                 # Landing page: ticker search
└─ report/[ticker]/page.tsx # Report route (async params, Next 16)
components/
├─ Report.tsx               # Client shell: fetch, skeletons, error states
├─ ExecutiveSummary.tsx     # Section 01
├─ FuturePipeline.tsx       # Section 02 (bucket-coded catalysts)
├─ Evaluation.tsx           # Section 03 (quant badge, metrics, PT range)
├─ PriceChart.tsx           # 1Y price chart: range toggles, SPY overlay, crosshair
└─ ThemeToggle.tsx          # Light/dark switch (persisted in localStorage)
```

Set `NEXT_PUBLIC_API_URL` to point at a non-default backend address.
