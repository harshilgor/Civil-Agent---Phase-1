import type { Point2D } from "@/api/types";

export function pixelToWorld(p: Point2D, metersPerPixel: number): Point2D {
  return { x: p.x * metersPerPixel, y: p.y * metersPerPixel };
}

export function worldToPixel(p: Point2D, metersPerPixel: number): Point2D {
  const inv = metersPerPixel === 0 ? 0 : 1 / metersPerPixel;
  return { x: p.x * inv, y: p.y * inv };
}
