import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="zh" data-theme="dark" suppressHydrationWarning>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
