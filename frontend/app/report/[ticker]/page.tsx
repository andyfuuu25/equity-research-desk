import type { Metadata } from "next";
import Report from "../../../components/Report";

interface PageProps {
  // Next.js 16: params is a Promise and must be awaited.
  params: Promise<{ ticker: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { ticker } = await params;
  const t = decodeURIComponent(ticker).toUpperCase();
  return { title: `${t} — Equity Research Desk` };
}

export default async function ReportPage({ params }: PageProps) {
  const { ticker } = await params;
  return <Report ticker={decodeURIComponent(ticker).toUpperCase()} />;
}
