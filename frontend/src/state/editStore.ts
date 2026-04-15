import { create } from "zustand";

type EditState = {
  past: unknown[];
  future: unknown[];
  push: (snapshot: unknown) => void;
  undo: () => void;
  redo: () => void;
};

export const useEditStore = create<EditState>((set, get) => ({
  past: [],
  future: [],
  push: (snapshot) => set((s) => ({ past: [...s.past, snapshot], future: [] })),
  undo: () => {
    const { past, future } = get();
    if (!past.length) return;
    const prev = past[past.length - 1];
    set({ past: past.slice(0, -1), future: [prev, ...future] });
  },
  redo: () => {
    const { past, future } = get();
    if (!future.length) return;
    const next = future[0];
    set({ past: [...past, next], future: future.slice(1) });
  },
}));
