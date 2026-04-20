"use client";

import { create } from "zustand";

export type HistoryEntry = {
  id: string;
  label: string;
  projectId: string;
  timestamp: string;
  system: boolean;
};

type HistoryState = {
  entries: Record<string, HistoryEntry[]>;
  add: (projectId: string, label: string, system?: boolean) => void;
  clear: (projectId: string) => void;
  get: (projectId: string) => HistoryEntry[];
};

export const useHistoryStore = create<HistoryState>((set, get) => ({
  entries: {},
  add: (projectId, label, system = false) =>
    set((s) => {
      const next: HistoryEntry = {
        id: crypto.randomUUID(),
        label,
        projectId,
        timestamp: new Date().toISOString(),
        system,
      };
      return {
        entries: {
          ...s.entries,
          [projectId]: [next, ...(s.entries[projectId] ?? [])].slice(0, 50),
        },
      };
    }),
  clear: (projectId) =>
    set((s) => ({ entries: { ...s.entries, [projectId]: [] } })),
  get: (projectId) => get().entries[projectId] ?? [],
}));
