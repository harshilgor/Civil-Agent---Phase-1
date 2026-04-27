"use client";

import { createJSONStorage, type StateStorage } from "zustand/middleware";

const memoryStorage = new Map<string, string>();

const fallbackStorage: StateStorage = {
  getItem: (name) => memoryStorage.get(name) ?? null,
  setItem: (name, value) => {
    memoryStorage.set(name, value);
  },
  removeItem: (name) => {
    memoryStorage.delete(name);
  },
};

function resolveBrowserStorage(): StateStorage {
  if (typeof window === "undefined") {
    return fallbackStorage;
  }

  try {
    const probeKey = "__civil_agent_storage_probe__";
    window.localStorage.setItem(probeKey, probeKey);
    window.localStorage.removeItem(probeKey);
    return window.localStorage;
  } catch {
    return fallbackStorage;
  }
}

export function createSafeJsonStorage() {
  return createJSONStorage(() => resolveBrowserStorage());
}
