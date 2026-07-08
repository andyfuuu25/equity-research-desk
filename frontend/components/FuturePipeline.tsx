interface PipelineData {
  earnings_date: string;
  body: string;
}

interface Props {
  data: PipelineData;
}

/** Visual accent per classification bucket — institutional colour semantics. */
const BUCKET_ACCENTS: Record<string, string> = {
  "Confirmed Catalysts:": "border-gain-dim text-gain",
  "Developing Stories:": "border-gold-dim text-gold",
  "Risk Events:": "border-loss-dim text-loss",
};

export default function FuturePipeline({ data }: Props) {
  if (!data) return null;

  const lines = data.body
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  return (
    <section>
      <header className="mb-5">
        <p className="text-[10px] uppercase tracking-[0.3em] text-gold">
          Section 02
        </p>
        <h2 className="mt-1 font-display text-2xl tracking-tight text-paper">
          Future Pipeline
        </h2>
        <p className="tnum mt-1 text-xs text-paper-mute">
          Upcoming earnings: {data.earnings_date}
        </p>
      </header>

      <div className="space-y-1 text-sm">
        {lines.map((line, i) => {
          // Skip the duplicated earnings line — already shown in the header
          if (line.startsWith("Upcoming Earnings:")) return null;

          const isHeading = !line.startsWith("-") && line.endsWith(":");
          const isBullet = line.startsWith("-");

          if (isHeading) {
            const accent =
              BUCKET_ACCENTS[line] ?? "border-line-strong text-paper";
            return (
              <p
                key={i}
                className={`mt-5 border-l-2 pl-3 text-xs font-semibold uppercase tracking-[0.2em] first:mt-0 ${accent}`}
              >
                {line.replace(/:$/, "")}
              </p>
            );
          }

          if (isBullet) {
            return (
              <p key={i} className="pl-5 leading-relaxed text-paper-dim">
                <span className="mr-2 text-paper-mute">▪</span>
                {line.replace(/^-\s*/, "")}
              </p>
            );
          }

          // "None identified." and any other prose
          return (
            <p key={i} className="pl-5 text-sm italic text-paper-mute">
              {line}
            </p>
          );
        })}
      </div>
    </section>
  );
}
