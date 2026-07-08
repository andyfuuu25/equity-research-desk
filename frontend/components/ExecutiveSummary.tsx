interface SummaryData {
  company: string;
  ticker: string;
  sector: string;
  industry: string;
  body: string;
}

interface Props {
  data: SummaryData;
}

export default function ExecutiveSummary({ data }: Props) {
  // Split the LLM body into paragraphs for clean rendering
  const paragraphs = data.body
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <section>
      <header className="mb-5">
        <p className="text-[10px] uppercase tracking-[0.3em] text-gold">
          Section 01
        </p>
        <h2 className="mt-1 font-display text-2xl tracking-tight text-paper">
          Executive Summary
        </h2>
        <p className="mt-1 text-xs text-paper-mute">
          {data.company} · {data.sector} / {data.industry}
        </p>
      </header>

      <div className="space-y-4 text-[15px] leading-7 text-paper-dim">
        {paragraphs.map((para, i) => (
          <p key={i} className={i === 0 ? "text-paper" : undefined}>
            {para}
          </p>
        ))}
      </div>
    </section>
  );
}
