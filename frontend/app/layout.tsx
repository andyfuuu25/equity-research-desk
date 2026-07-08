import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Equity Research Desk",
  description:
    "On-demand, analyst-grade company profiles for US-listed equities — live data, quantitative scoring, and structured research sections.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning: data-theme is set pre-paint by the inline
    // script below, so the server-rendered attribute intentionally differs.
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-ink-950 text-paper">
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`,
          }}
        />
        {children}
      </body>
    </html>
  );
}
