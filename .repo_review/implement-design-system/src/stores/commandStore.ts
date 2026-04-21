"use client";

import { create } from "zustand";

export type CommandResponseKind = "info" | "success" | "warning" | "error";

export type CommandEntry = {
  id: string;
  command: string;
  response: string;
  kind: CommandResponseKind;
  timestamp: string;
};

type CommandState = {
  history: CommandEntry[];
  open: boolean;
  pending: boolean;
  latest: CommandEntry | null;
  setOpen: (v: boolean) => void;
  setPending: (v: boolean) => void;
  addEntry: (e: Omit<CommandEntry, "id" | "timestamp">) => void;
  clearLatest: () => void;
};

export const useCommandStore = create<CommandState>((set) => ({
  history: [],
  open: false,
  pending: false,
  latest: null,
  setOpen: (v) => set({ open: v }),
  setPending: (v) => set({ pending: v }),
  addEntry: (e) =>
    set((s) => {
      const entry: CommandEntry = {
        ...e,
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
      };
      return { history: [entry, ...s.history].slice(0, 100), latest: entry };
    }),
  clearLatest: () => set({ latest: null }),
}));
