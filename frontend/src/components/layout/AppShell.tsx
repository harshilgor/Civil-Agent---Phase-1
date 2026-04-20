"use client";

import { ReactNode } from "react";
import { Toaster } from "sonner";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";

export function AppShell({
  children,
  cursor,
}: {
  children: ReactNode;
  cursor?: { x?: number; y?: number; z?: number } | null;
}) {
  return (
    <div className="h-screen w-screen flex flex-col bg-surface text-on-surface overflow-hidden">
      <TopBar />
      <div className="flex-1 flex min-h-0">
        <Sidebar />
        <main className="flex-1 min-w-0 flex flex-col">{children}</main>
      </div>
      <StatusBar cursor={cursor} />
      <Toaster
        position="top-right"
        theme="light"
        closeButton
        toastOptions={{
          className:
            "!bg-surface-container-lowest !text-on-surface !border-hairline !font-sans",
        }}
      />
    </div>
  );
}
