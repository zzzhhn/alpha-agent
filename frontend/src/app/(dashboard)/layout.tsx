"use client";

import { type ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { LocaleProvider } from "@/components/layout/LocaleProvider";

interface DashboardLayoutProps {
  readonly children: ReactNode;
}

export default function DashboardLayout({
  children,
}: DashboardLayoutProps) {
  return (
    <LocaleProvider>
      <div className="grid h-screen grid-cols-[260px_1fr] grid-rows-[48px_1fr]">
        {/* Sidebar spans full height */}
        <div className="row-span-full">
          <Sidebar />
        </div>

        {/* Topbar */}
        <header className="topbar-blur col-start-2 flex items-center justify-between border-b border-border px-6">
          <Breadcrumb />
          <ThemeToggle />
        </header>

        {/* Main content */}
        <main className="col-start-2 overflow-y-auto px-6 py-5 pb-10">
          {children}
        </main>
      </div>
    </LocaleProvider>
  );
}
