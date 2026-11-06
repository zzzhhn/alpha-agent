import type { Metadata } from "next";
import localFont from "next/font/local";
import { SessionProvider } from "next-auth/react";
import "./globals.css";

// Keep the workstation's original families without a build-time Google fetch.
// Font sources and OFL licenses live beside these pinned local assets.
const jetbrainsMono = localFont({
  src: "./fonts/JetBrainsMono-variable.ttf",
  variable: "--font-jetbrains-mono",
  display: "swap",
  weight: "400 700",
});

const interTight = localFont({
  src: "./fonts/InterTight-variable.ttf",
  variable: "--font-inter-tight",
  display: "swap",
  weight: "400 700",
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
      lang="zh-CN"
      data-theme="dark"
      suppressHydrationWarning
      className={`${jetbrainsMono.variable} ${interTight.variable}`}
    >
      <body className="font-sans antialiased">
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
