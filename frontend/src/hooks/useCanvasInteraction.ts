import { useEffect } from "react";
import type { InteractionMode } from "@/state/canvasStore";

/** Wire interaction controllers to canvas mount (stubs). */
export function useCanvasInteraction(_canvas: HTMLCanvasElement | null, _mode: InteractionMode) {
  useEffect(() => {
    return () => undefined;
  }, [_canvas, _mode]);
}
