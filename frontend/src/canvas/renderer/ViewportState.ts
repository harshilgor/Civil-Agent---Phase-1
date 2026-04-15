export type ViewportState = {
  offsetX: number;
  offsetY: number;
  zoom: number;
  rotation: number;
};

export function defaultViewport(): ViewportState {
  return { offsetX: 0, offsetY: 0, zoom: 1, rotation: 0 };
}
