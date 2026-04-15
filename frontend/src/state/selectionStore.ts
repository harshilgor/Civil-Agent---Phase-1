import { create } from "zustand";

type SelectionState = {
  roomIds: string[];
  wallIds: string[];
  setRooms: (ids: string[]) => void;
  setWalls: (ids: string[]) => void;
};

export const useSelectionStore = create<SelectionState>((set) => ({
  roomIds: [],
  wallIds: [],
  setRooms: (roomIds) => set({ roomIds }),
  setWalls: (wallIds) => set({ wallIds }),
}));
