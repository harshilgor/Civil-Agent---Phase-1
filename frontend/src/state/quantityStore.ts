import { create } from "zustand";

export type QuantitySnapshot = {
  areas: { roomId: string; label: string; areaM2: number; pctTotal: number }[];
  wallLengthM: number;
};

type QState = {
  quantities: QuantitySnapshot | null;
  setQuantities: (q: QuantitySnapshot | null) => void;
};

export const useQuantityStore = create<QState>((set) => ({
  quantities: null,
  setQuantities: (quantities) => set({ quantities }),
}));
