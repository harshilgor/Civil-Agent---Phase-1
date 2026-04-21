"use client";

import { create } from "zustand";

export type ElementKind =
  | "wall"
  | "room"
  | "column"
  | "core"
  | "zone"
  | "opening"
  | "none";

export type Selection = {
  kind: ElementKind;
  id: string | null;
};

type SelectionState = {
  selection: Selection;
  hover: Selection;
  select: (kind: ElementKind, id: string) => void;
  clear: () => void;
  setHover: (kind: ElementKind, id: string | null) => void;
};

export const useSelectionStore = create<SelectionState>((set) => ({
  selection: { kind: "none", id: null },
  hover: { kind: "none", id: null },
  select: (kind, id) => set({ selection: { kind, id } }),
  clear: () => set({ selection: { kind: "none", id: null } }),
  setHover: (kind, id) => set({ hover: { kind, id } }),
}));
