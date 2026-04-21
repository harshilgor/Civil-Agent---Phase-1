import type {
  BuildingGraph,
  ColumnCandidate,
  Core,
  Grid,
  GridAxis,
  Opening,
  Point,
  Room,
  ScoreDecomposition,
  StructuredInput,
  SupportClass,
  Wall,
} from "@/types/domain";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

function classifyScore(score: number): SupportClass {
  if (score >= 0.8) return "strong";
  if (score >= 0.5) return "secondary";
  if (score >= 0.2) return "weak";
  return "forbidden";
}

function round(v: number, n = 2) {
  return Math.round(v * 10 ** n) / 10 ** n;
}

function axisLabelsX(count: number): string[] {
  return Array.from({ length: count }, (_, i) => LETTERS[i] ?? `X${i + 1}`);
}

function axisLabelsY(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `${i + 1}`);
}

function coreRect(
  input: StructuredInput,
  lengthMm: number,
  widthMm: number,
): { polygon: Point[]; center: Point } | null {
  if (input.coreLocation === "none") return null;
  const coreLMm = Math.min(lengthMm * 0.28, 12000);
  const coreWMm = Math.min(widthMm * 0.28, 10000);
  let cx = lengthMm / 2;
  let cy = widthMm / 2;
  switch (input.coreLocation) {
    case "edge_north":
      cy = widthMm - coreWMm / 2 - 1000;
      break;
    case "edge_south":
      cy = coreWMm / 2 + 1000;
      break;
    case "edge_east":
      cx = lengthMm - coreLMm / 2 - 1000;
      break;
    case "edge_west":
      cx = coreLMm / 2 + 1000;
      break;
    case "corner":
      cx = coreLMm / 2 + 1000;
      cy = coreWMm / 2 + 1000;
      break;
  }
  const polygon: Point[] = [
    [cx - coreLMm / 2, cy - coreWMm / 2],
    [cx + coreLMm / 2, cy - coreWMm / 2],
    [cx + coreLMm / 2, cy + coreWMm / 2],
    [cx - coreLMm / 2, cy + coreWMm / 2],
  ];
  return { polygon, center: [cx, cy] };
}

function pointInRect(p: Point, rect: Point[]): boolean {
  if (rect.length !== 4) return false;
  const [a, , c] = rect;
  const xMin = Math.min(a[0], c[0]);
  const xMax = Math.max(a[0], c[0]);
  const yMin = Math.min(a[1], c[1]);
  const yMax = Math.max(a[1], c[1]);
  return p[0] >= xMin && p[0] <= xMax && p[1] >= yMin && p[1] <= yMax;
}

function nearestPerimeterDistance(p: Point, l: number, w: number): number {
  return Math.min(p[0], p[1], l - p[0], w - p[1]);
}

export function generateBuildingGraph(
  projectId: string,
  input: StructuredInput,
): BuildingGraph {
  const lengthMm = input.lengthM * 1000;
  const widthMm = input.widthM * 1000;
  const bayXMm = Math.max(3000, input.preferredBayXM * 1000);
  const bayYMm = Math.max(3000, input.preferredBayYM * 1000);

  // Determine grid lines
  const xCount = Math.max(2, Math.round(lengthMm / bayXMm) + 1);
  const yCount = Math.max(2, Math.round(widthMm / bayYMm) + 1);
  const xStep = lengthMm / (xCount - 1);
  const yStep = widthMm / (yCount - 1);
  const xLabels = axisLabelsX(xCount);
  const yLabels = axisLabelsY(yCount);

  const xAxes: GridAxis[] = xLabels.map((l, i) => ({
    label: l,
    positionMm: Math.round(i * xStep),
  }));
  const yAxes: GridAxis[] = yLabels.map((l, i) => ({
    label: l,
    positionMm: Math.round(i * yStep),
  }));

  const grid: Grid = { xAxes, yAxes };
  const storyHeightMm = Math.round(input.typicalFloorHeightM * 1000);
  const groundHeightMm = Math.round(
    (input.groundFloorHeightM ?? input.typicalFloorHeightM) * 1000,
  );

  // Perimeter (clockwise)
  const perimeter: Point[] = [
    [0, 0],
    [lengthMm, 0],
    [lengthMm, widthMm],
    [0, widthMm],
  ];

  // Core
  const core = coreRect(input, lengthMm, widthMm);
  const cores: Core[] = core
    ? [
        {
          id: "CORE_01",
          label: "Core",
          polygon: core.polygon,
          floors: Array.from({ length: input.stories }, (_, i) => i + 1),
          contains: { ...input.coreContains },
        },
      ]
    : [];

  // Walls: perimeter structural walls
  const wallThicknessStructural = 300;
  const wallThicknessPartition = 150;
  const storyList = Array.from({ length: input.stories }, (_, i) => i + 1);
  const walls: Wall[] = [];
  const addWall = (
    idx: number,
    start: Point,
    end: Point,
    type: "structural" | "partition" | "shear",
  ) => {
    walls.push({
      id: `W-${String(walls.length + 1).padStart(2, "0")}`,
      type,
      thicknessMm:
        type === "partition" ? wallThicknessPartition : wallThicknessStructural,
      heightMm: storyHeightMm,
      start,
      end,
      stories: storyList,
      material: input.material === "rc" ? "RC" : input.material.toUpperCase(),
      confidence: 0.92 - (type === "partition" ? 0.08 : 0) - idx * 0.002,
    });
  };
  // Perimeter walls
  for (let i = 0; i < perimeter.length; i++) {
    const a = perimeter[i];
    const b = perimeter[(i + 1) % perimeter.length];
    addWall(i, a, b, "structural");
  }
  // Core walls (shear)
  if (core) {
    const cp = core.polygon;
    for (let i = 0; i < cp.length; i++) {
      walls.push({
        id: `W-${String(walls.length + 1).padStart(2, "0")}`,
        type: "shear",
        thicknessMm: 400,
        heightMm: storyHeightMm,
        start: cp[i],
        end: cp[(i + 1) % cp.length],
        stories: storyList,
        material: input.material === "rc" ? "RC" : "RC",
        confidence: 0.95,
      });
    }
  }
  // Interior partition walls along mid X grid line (typical office fit-out)
  if (xAxes.length > 2) {
    const midX = xAxes[Math.floor(xAxes.length / 2)].positionMm;
    walls.push({
      id: `W-${String(walls.length + 1).padStart(2, "0")}`,
      type: "partition",
      thicknessMm: wallThicknessPartition,
      heightMm: storyHeightMm,
      start: [midX, 0],
      end: [midX, widthMm],
      stories: storyList,
      material: "GYP",
      confidence: 0.82,
    });
  }

  // Rooms — partition by grid sections
  const rooms: Room[] = [];
  let rIdx = 1;
  for (let xi = 0; xi < xAxes.length - 1; xi++) {
    for (let yi = 0; yi < yAxes.length - 1; yi++) {
      const x0 = xAxes[xi].positionMm;
      const x1 = xAxes[xi + 1].positionMm;
      const y0 = yAxes[yi].positionMm;
      const y1 = yAxes[yi + 1].positionMm;
      const poly: Point[] = [
        [x0, y0],
        [x1, y0],
        [x1, y1],
        [x0, y1],
      ];
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      const inCore = core ? pointInRect([cx, cy], core.polygon) : false;
      const areaM2 = round(((x1 - x0) * (y1 - y0)) / 1_000_000, 1);
      let type: Room["type"] = "open_plate";
      let label = `Office ${rIdx}`;
      if (inCore) {
        type = "service";
        label = "Core services";
      } else if (yi === 0 && xi === Math.floor((xAxes.length - 1) / 2)) {
        type = "lobby";
        label = "Lobby";
      } else if (
        input.occupancy === "office" ||
        input.occupancy === "mixed_use"
      ) {
        type = "office";
      } else if (input.occupancy === "residential") {
        type = "open_plate";
        label = `Unit ${rIdx}`;
      }
      rooms.push({
        id: `R-${String(rIdx).padStart(2, "0")}`,
        label,
        type,
        polygon: poly,
        areaM2,
        floor: 1,
      });
      rIdx++;
    }
  }

  // Openings — doors on perimeter walls at ground floor (mock)
  const openings: Opening[] = [];
  for (let i = 0; i < Math.min(walls.length, 4); i++) {
    openings.push({
      id: `O-${String(i + 1).padStart(2, "0")}`,
      wallId: walls[i].id,
      type: i === 0 ? "door" : "window",
      tAlong: 0.4 + (i % 3) * 0.15,
      widthMm: i === 0 ? 1800 : 1500,
      heightMm: i === 0 ? 2400 : 1500,
    });
  }

  // Column candidates at every grid intersection
  const candidates: ColumnCandidate[] = [];
  const stackedGroups = new Map<string, number>();

  for (let xi = 0; xi < xAxes.length; xi++) {
    for (let yi = 0; yi < yAxes.length; yi++) {
      for (let f = 1; f <= input.stories; f++) {
        const pos: Point = [xAxes[xi].positionMm, yAxes[yi].positionMm];
        const gridLabel = `${xAxes[xi].label}-${yAxes[yi].label}`;
        const stackKey = gridLabel;
        stackedGroups.set(stackKey, (stackedGroups.get(stackKey) ?? 0) + 1);

        const inCore = core ? pointInRect(pos, core.polygon) : false;
        const perimDist = nearestPerimeterDistance(pos, lengthMm, widthMm);
        const isOnPerimeter = perimDist < 10;

        const decomposition: ScoreDecomposition = {
          gridAlignment: 1.0,
          wallSupport:
            isOnPerimeter ? 1.0 : xi > 0 && xi < xAxes.length - 1 ? 0.9 : 0.85,
          zoneCompatibility: inCore ? 0.05 : 0.85,
          perimeterFactor: isOnPerimeter ? 1.0 : 0.9,
          tributaryArea: Math.min(
            1,
            ((xStep * yStep) / 1_000_000 / 80) * 0.9 + 0.05,
          ),
        };

        // Simple weighted mean
        const weights = {
          gridAlignment: 0.2,
          wallSupport: 0.25,
          zoneCompatibility: 0.25,
          perimeterFactor: 0.15,
          tributaryArea: 0.15,
        };
        let rawScore = 0;
        (Object.keys(weights) as Array<keyof ScoreDecomposition>).forEach(
          (k) => {
            rawScore += decomposition[k] * weights[k];
          },
        );
        // Core candidates flat-forbidden
        if (inCore) rawScore = 0.12;
        const score = round(rawScore, 3);

        candidates.push({
          id: `C-${gridLabel}-F${f}`,
          position: pos,
          gridIntersection: gridLabel,
          floor: f,
          score,
          classification: classifyScore(score),
          decomposition,
          verticalAlignmentGroup: `VA-${String(xi * 10 + yi).padStart(3, "0")}`,
          stackedAcrossAllFloors: true,
          tributaryAreaM2: round((xStep * yStep) / 1_000_000, 1),
        });
      }
    }
  }

  // Completeness scoring
  const sectionScores: Record<string, number> = {
    project_info: 1.0,
    stories: 1.0,
    grid: 1.0,
    walls: 0.92,
    rooms: rooms.length >= 4 ? 0.86 : 0.7,
    openings: openings.length >= 2 ? 1.0 : 0.7,
    columns: 1.0,
    cores: cores.length > 0 ? 1.0 : 0.65,
    facade: 1.0,
  };
  const completeness = round(
    Object.values(sectionScores).reduce((a, b) => a + b, 0) /
      Object.keys(sectionScores).length,
    2,
  );
  const confidence = round(
    candidates.reduce((a, b) => a + b.score, 0) / Math.max(1, candidates.length),
    2,
  );

  const assumptions: string[] = [
    `${input.gridType === "regular" ? "Regular" : "Mixed"} grid assumed from bay preferences (${input.preferredBayXM}m × ${input.preferredBayYM}m).`,
    cores.length
      ? `Core set to ${input.coreLocation.replace("_", " ")} based on user input.`
      : `No core specified — using perimeter-frame assumption.`,
    `Partition walls assumed for non-grid interior walls.`,
  ];
  const warnings: string[] = [];
  if (sectionScores.rooms < 0.8)
    warnings.push("Some rooms missing labels or types.");
  if (!cores.length)
    warnings.push("No core — lateral system may rely on moment frames.");

  return {
    projectId,
    lengthMm,
    widthMm,
    perimeter,
    stories: input.stories,
    storyHeightMm,
    groundStoryHeightMm: groundHeightMm,
    buildingCode: input.buildingCode,
    grid,
    walls,
    rooms,
    openings,
    columnCandidates: candidates,
    cores,
    completeness,
    confidence,
    sectionScores,
    missingFields:
      sectionScores.rooms < 0.8 ? ["rooms[3].label", "rooms[7].type"] : [],
    assumptions,
    warnings,
    inputSource: "STRUCTURED",
    processingMs: 1200 + Math.floor(Math.random() * 400),
  };
}
