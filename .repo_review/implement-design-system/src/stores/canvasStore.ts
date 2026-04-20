"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ViewMode = "2d" | "3d";
export type OverlayMode = "none" | "zones" | "supports" | "load_paths" | "utilization";

export type LayerKey =
  | "walls"
  | "grid"
  | "rooms"
  | "columns"
  | "cores"
  | "openings"
  | "dimensions";

type CanvasState = {
  viewMode: ViewMode;
  overlayMode: OverlayMode;
  zoom: number;
  panX: number;
  panY: number;
  floor: number | "all";
  layers: Record<LayerKey, boolean>;
  rightPanelCollapsed: boolean;
  sidebarCollapsed: boolean;
  setViewMode: (m: ViewMode) => void;
  setOverlayMode: (m: OverlayMode) => void;
  setZoom: (z: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  setPan: (x: number, y: number) => void;
  resetView: () => void;
  setFloor: (f: number | "all") => void;
  toggleLayer: (k: LayerKey) => void;
  toggleRightPanel: () => void;
  toggleSidebar: () => void;
};

export const useCanvasStore = create<CanvasState>()(
  persist(
    (set) => ({
      viewMode: "2d",
      overlayMode: "none",
      zoom: 1,
      panX: 0,
      panY: 0,
      floor: 1,
      layers: {
        walls: true,
        grid: true,
        rooms: true,
        columns: true,
        cores: true,
        openings: false,
        dimensions: false,
      },
      rightPanelCollapsed: false,
      sidebarCollapsed: false,
      setViewMode: (m) => set({ viewMode: m }),
      setOverlayMode: (m) => set({ overlayMode: m }),
      setZoom: (zoom) => set({ zoom: Math.min(4, Math.max(0.2, zoom)) }),
      zoomIn: () =>
        set((s) => ({ zoom: Math.min(4, Math.round(s.zoom * 1.2 * 100) / 100) })),
      zoomOut: () =>
        set((s) => ({ zoom: Math.max(0.2, Math.round((s.zoom / 1.2) * 100) / 100) })),
      setPan: (panX, panY) => set({ panX, panY }),
      resetView: () => set({ zoom: 1, panX: 0, panY: 0 }),
      setFloor: (floor) => set({ floor }),
      toggleLayer: (k) =>
        set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
      toggleRightPanel: () =>
        set((s) => ({ rightPanelCollapsed: !s.rightPanelCollapsed })),
      toggleSidebar: () =>
        set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    {
      name: "civil-agent-canvas",
      partialize: (s) => ({
        viewMode: s.viewMode,
        overlayMode: s.overlayMode,
        layers: s.layers,
        rightPanelCollapsed: s.rightPanelCollapsed,
        sidebarCollapsed: s.sidebarCollapsed,
      }),
    },
  ),
);
