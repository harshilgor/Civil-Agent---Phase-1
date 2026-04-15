import { create } from "zustand";

export type InteractionMode = "select" | "edit_vertices" | "split" | "merge";

type CanvasState = {
  zoom: number;
  panX: number;
  panY: number;
  layers: Record<string, boolean>;
  mode: InteractionMode;
  setViewport: (z: number, x: number, y: number) => void;
  toggleLayer: (id: string) => void;
  setMode: (m: InteractionMode) => void;
};

export const useCanvasStore = create<CanvasState>((set) => ({
  zoom: 1,
  panX: 0,
  panY: 0,
  layers: {
    image: true,
    rooms: true,
    boundaries: true,
    heatmap: false,
    contested: false,
  },
  mode: "select",
  setViewport: (zoom, panX, panY) => set({ zoom, panX, panY }),
  toggleLayer: (id) =>
    set((s) => ({ layers: { ...s.layers, [id]: !s.layers[id] } })),
  setMode: (mode) => set({ mode }),
}));
