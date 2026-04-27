"use client";

import { create } from "zustand";

type SizerUiState = {
  sizingInProgress: boolean;
  assumptionsOpen: boolean;
  setSizingInProgress: (value: boolean) => void;
  setAssumptionsOpen: (value: boolean) => void;
};

export const useSizerUiStore = create<SizerUiState>()((set) => ({
  sizingInProgress: false,
  assumptionsOpen: false,
  setSizingInProgress: (value) => set({ sizingInProgress: value }),
  setAssumptionsOpen: (value) => set({ assumptionsOpen: value }),
}));
