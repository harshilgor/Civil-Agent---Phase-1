import { describe, expect, it } from "vitest";
import { pixelToWorld } from "@/canvas/utils/coordinate_transform";

describe("coordinate_transform", () => {
  it("scales pixels to meters", () => {
    expect(pixelToWorld({ x: 100, y: 200 }, 0.01)).toEqual({ x: 1, y: 2 });
  });
});
