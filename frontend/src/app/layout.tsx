import type { Metadata } from "next";
import { JetBrains_Mono, Inter_Tight } from "next/font/google";
import "./globals.css";

// Workstation aesthetic (Variation C) — fonts are self-hosted by Next.js
// and exposed as CSS vars (--font-jetbrains-mono / --font-inter-tight). The
// tailwind.config maps `font-tm-mono` / `font-tm-sans` to these vars; nothing
// in Stage 1 actually applies them yet. Stage 2 (workstation shell) opts in.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "AlphaCore - Quantitative Research & Decision System",
  description:
    "AlphaCore quantitative trading dashboard for real-time pipeline monitoring, alpha signal generation, and portfolio management.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh"
      data-theme="dark"
      suppressHydrationWarning
      className={`${jetbrainsMono.variable} ${interTight.variable}`}
    >
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
