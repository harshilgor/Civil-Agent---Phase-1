export type LoadCase = "dead" | "live" | "snow" | "wind";

export type StructuralLoad = {
  id: string;
  case: LoadCase;
  name: string;
  magnitudeKN: number;
  origin: [number, number, number];
  direction: [number, number, number];
};

export const defaultStructuralLoads: StructuralLoad[] = [
  {
    id: "DL-01",
    case: "dead",
    name: "Slab self-weight (L1)",
    magnitudeKN: 420.5,
    origin: [0, 3.2, 0],
    direction: [0, -1, 0],
  },
  {
    id: "LL-02",
    case: "live",
    name: "Occupancy patch (corridor)",
    magnitudeKN: 185.0,
    origin: [2.5, 3.2, 1.2],
    direction: [0, -1, 0],
  },
  {
    id: "WN-01",
    case: "wind",
    name: "Windward façade (ULS)",
    magnitudeKN: 96.3,
    origin: [-4, 2, 0],
    direction: [1, 0.12, 0],
  },
];
