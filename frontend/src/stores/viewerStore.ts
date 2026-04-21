"use client";

import { create } from "zustand";
import type { LoadCase } from "@/lib/loadsMock";

export type TranscriptLine = { role: "user" | "system"; text: string };

type ViewerState = {
  loadsVisible: boolean;
  loadsPromptOpen: boolean;
  loadCaseFilter: LoadCase | "all";
  transcript: TranscriptLine[];
  setLoadsVisible: (v: boolean) => void;
  toggleLoadsPrompt: () => void;
  /** Opens the prompt, enables vectors, and resets filter to all cases. */
  openLoadsWorkspace: () => void;
  setLoadCaseFilter: (c: LoadCase | "all") => void;
  pushTranscript: (line: TranscriptLine) => void;
  /** Mock interpreter for load visibility and filters. */
  interpretLoadsPrompt: (text: string) => void;
  resetLoadsSession: () => void;
};

const initialTranscript: TranscriptLine[] = [
  {
    role: "system",
    text: "Load interface ready. Example: show dead loads · hide loads · filter wind.",
  },
];

export const useViewerStore = create<ViewerState>((set, get) => ({
  loadsVisible: false,
  loadsPromptOpen: false,
  loadCaseFilter: "all",
  transcript: initialTranscript,
  setLoadsVisible: (v) => set({ loadsVisible: v }),
  toggleLoadsPrompt: () =>
    set((s) => ({ loadsPromptOpen: !s.loadsPromptOpen })),
  setLoadCaseFilter: (c) => set({ loadCaseFilter: c }),
  pushTranscript: (line) =>
    set((s) => ({ transcript: [...s.transcript, line] })),
  openLoadsWorkspace: () =>
    set((s) => ({
      loadsPromptOpen: true,
      loadsVisible: true,
      loadCaseFilter: "all",
      transcript: [
        ...s.transcript,
        {
          role: "system",
          text: "Load workspace open. Catalogue: DL-01 dead · LL-02 live · WN-01 wind (mock).",
        },
      ],
    })),
  interpretLoadsPrompt: (text) => {
    const trimmed = text.trim();
    const lower = trimmed.toLowerCase();

    if (!trimmed) {
      get().pushTranscript({
        role: "system",
        text: "No input. Specify load case or visibility.",
      });
      return;
    }

    get().pushTranscript({ role: "user", text: trimmed });

    if (lower.includes("hide") && lower.includes("load")) {
      set({ loadsVisible: false, loadsPromptOpen: true });
      get().pushTranscript({
        role: "system",
        text: "Load vectors hidden in the 3D scene.",
      });
      return;
    }

    if (
      lower.includes("show") &&
      lower.includes("load") &&
      !lower.includes("dead") &&
      !lower.includes("live") &&
      !lower.includes("wind") &&
      !lower.includes("snow")
    ) {
      set({ loadsVisible: true, loadsPromptOpen: true, loadCaseFilter: "all" });
      get().pushTranscript({
        role: "system",
        text: "All load cases drawn in the viewport.",
      });
      return;
    }

    if (lower.includes("dead")) {
      set({ loadsVisible: true, loadsPromptOpen: true, loadCaseFilter: "dead" });
      get().pushTranscript({
        role: "system",
        text: "Filter set to dead load case only.",
      });
      return;
    }
    if (lower.includes("live")) {
      set({ loadsVisible: true, loadsPromptOpen: true, loadCaseFilter: "live" });
      get().pushTranscript({
        role: "system",
        text: "Filter set to live load case only.",
      });
      return;
    }
    if (lower.includes("wind")) {
      set({ loadsVisible: true, loadsPromptOpen: true, loadCaseFilter: "wind" });
      get().pushTranscript({
        role: "system",
        text: "Filter set to wind load case only.",
      });
      return;
    }
    if (lower.includes("snow")) {
      set({ loadsVisible: true, loadsPromptOpen: true, loadCaseFilter: "snow" });
      get().pushTranscript({
        role: "system",
        text: "Filter set to snow load case only.",
      });
      return;
    }

    if (lower.includes("list") || lower.includes("cases")) {
      get().pushTranscript({
        role: "system",
        text: "Active catalogue: DL-01 dead · LL-02 live · WN-01 wind (mock).",
      });
      return;
    }

    get().pushTranscript({
      role: "system",
      text: "Command not mapped. Try: show loads · hide loads · dead loads · list load cases.",
    });
  },
  resetLoadsSession: () =>
    set({
      loadsVisible: false,
      loadsPromptOpen: false,
      loadCaseFilter: "all",
      transcript: initialTranscript,
    }),
}));
