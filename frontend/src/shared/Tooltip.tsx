import type { ReactNode } from "react";

export function Tooltip({ children, title }: { children: ReactNode; title: string }) {
  return <span title={title}>{children}</span>;
}
