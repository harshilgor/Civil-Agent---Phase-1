"use client";

import { startTransition, useEffect, useState } from "react";

const empty = {
  surface: "",
  onSurface: "",
  secondary: "",
  fnCoral: "",
  fnBlue: "",
  fnPink: "",
  outline: "",
};

/**
 * Reads resolved CSS custom properties from the document root (no literals in callers).
 */
export function useDesignTokens() {
  const [tokens, setTokens] = useState(empty);

  useEffect(() => {
    queueMicrotask(() => {
      const root = document.documentElement;
      const read = (name: string) =>
        getComputedStyle(root).getPropertyValue(name).trim() || "";

      startTransition(() => {
        setTokens({
          surface: read("--surface"),
          onSurface: read("--on-surface"),
          secondary: read("--secondary"),
          fnCoral: read("--fn-coral"),
          fnBlue: read("--fn-blue"),
          fnPink: read("--fn-pink"),
          outline: read("--outline"),
        });
      });
    });
  }, []);

  return tokens;
}
