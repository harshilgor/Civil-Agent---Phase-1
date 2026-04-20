import type { Config } from "tailwindcss";

/**
 * Tailwind v4 reads tokens from `src/app/globals.css` (`@theme` block).
 * This file keeps the default content globs discoverable for tooling.
 */
const config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
} satisfies Config;

export default config;
