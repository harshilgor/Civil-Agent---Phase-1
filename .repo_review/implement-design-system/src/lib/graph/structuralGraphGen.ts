import type {
  BuildingGraph,
  Constraint,
  GravitySystemCandidate,
  LateralSystemCandidate,
  Point,
  StructuralGraph,
  StructuralZone,
  StructuredInput,
  ZoneType,
} from "@/types/domain";

function round(v: number, n = 2) {
  return Math.round(v * 10 ** n) / 10 ** n;
}

function polyArea(polygon: Point[]): number {
  let a = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x1, y1] = polygon[i];
    const [x2, y2] = polygon[(i + 1) % polygon.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

function polyPerimeter(polygon: Point[]): number {
  let p = 0;
  for (let i = 0; i < polygon.length; i++) {
    const [x1, y1] = polygon[i];
    const [x2, y2] = polygon[(i + 1) % polygon.length];
    p += Math.hypot(x2 - x1, y2 - y1);
  }
  return p;
}

export function generateStructuralGraph(
  graph: BuildingGraph,
  input: StructuredInput,
): StructuralGraph {
  const zones: StructuralZone[] = [];
  const floors = Array.from({ length: graph.stories }, (_, i) => i + 1);

  // For each floor, derive zones:
  //  - Core -> 'core'
  //  - Perimeter band (4m deep) -> 'perimeter'
  //  - Corridor band (mid-X or mid-Y) -> 'corridor'
  //  - Remaining -> 'open_plate'
  //  - Floor 1 -> mark one open area as 'transfer_risk'
  const perimeterBandMm = 4000;

  for (const floor of floors) {
    // Core zone
    if (graph.cores.length > 0) {
      const c = graph.cores[0];
      zones.push({
        id: `Z-CORE-F${floor}`,
        type: "core",
        floor,
        polygon: c.polygon,
        areaM2: round(polyArea(c.polygon) / 1_000_000, 1),
        perimeterM: round(polyPerimeter(c.polygon) / 1000, 1),
        contains: c.contains,
        notes: ["Elevator shaft", "Stairwell", "Vertical service risers"],
      });
    }

    // Perimeter zone (outer band only — represented as outer polygon minus inner)
    const { lengthMm, widthMm } = graph;
    const innerPerim: Point[] = [
      [perimeterBandMm, perimeterBandMm],
      [lengthMm - perimeterBandMm, perimeterBandMm],
      [lengthMm - perimeterBandMm, widthMm - perimeterBandMm],
      [perimeterBandMm, widthMm - perimeterBandMm],
    ];
    zones.push({
      id: `Z-PER-F${floor}`,
      type: "perimeter",
      floor,
      polygon: graph.perimeter, // renderer handles donut
      areaM2: round(
        (polyArea(graph.perimeter) - polyArea(innerPerim)) / 1_000_000,
        1,
      ),
      perimeterM: round(polyPerimeter(graph.perimeter) / 1000, 1),
      notes: ["Facade-adjacent band", "Window-wall support zone"],
    });

    // Corridor zone: strip along X through middle Y
    const corridorHalfMm = 1500;
    const corridor: Point[] = [
      [0, widthMm / 2 - corridorHalfMm],
      [lengthMm, widthMm / 2 - corridorHalfMm],
      [lengthMm, widthMm / 2 + corridorHalfMm],
      [0, widthMm / 2 + corridorHalfMm],
    ];
    zones.push({
      id: `Z-COR-F${floor}`,
      type: "corridor",
      floor,
      polygon: corridor,
      areaM2: round(polyArea(corridor) / 1_000_000, 1),
      perimeterM: round(polyPerimeter(corridor) / 1000, 1),
      notes: ["Primary circulation band", "No columns permitted"],
    });

    // Open plate — rest of floor inside perimeter band, excluding core/corridor
    zones.push({
      id: `Z-OP-F${floor}`,
      type: "open_plate",
      floor,
      polygon: innerPerim,
      areaM2: round(polyArea(innerPerim) / 1_000_000, 1),
      perimeterM: round(polyPerimeter(innerPerim) / 1000, 1),
      notes: ["Typical open workspace", "Supports flat-slab or beam-slab"],
    });

    // Transfer risk on floor 1 (lobby floor)
    if (floor === 1) {
      const transfer: Point[] = [
        [lengthMm * 0.35, widthMm * 0.1],
        [lengthMm * 0.65, widthMm * 0.1],
        [lengthMm * 0.65, widthMm * 0.32],
        [lengthMm * 0.35, widthMm * 0.32],
      ];
      zones.push({
        id: `Z-TR-F${floor}`,
        type: "transfer_risk",
        floor,
        polygon: transfer,
        areaM2: round(polyArea(transfer) / 1_000_000, 1),
        perimeterM: round(polyPerimeter(transfer) / 1000, 1),
        notes: ["Double-height lobby", "Transfer beam likely required"],
      });
    }
  }

  const bayX =
    graph.grid.xAxes.length > 1
      ? graph.grid.xAxes[1].positionMm - graph.grid.xAxes[0].positionMm
      : 8000;
  const bayY =
    graph.grid.yAxes.length > 1
      ? graph.grid.yAxes[1].positionMm - graph.grid.yAxes[0].positionMm
      : 8000;
  const maxBay = Math.max(bayX, bayY);
  const minBay = Math.min(bayX, bayY);
  const typical = round((bayX + bayY) / 2, 0);
  const spanRegularity = round(1 - Math.abs(bayX - bayY) / Math.max(bayX, bayY), 3);
  const framingDirection: "x" | "y" = bayY > bayX ? "y" : "x";

  // Gravity system candidates (ranked by plausibility for input.material)
  const gravity: GravitySystemCandidate[] = [];
  if (input.material === "rc") {
    gravity.push({
      id: "gs-rc-flat",
      system: "rc_flat_slab",
      plausibility: maxBay <= 9500 ? 0.92 : 0.65,
      rationale: `Spans ${round(bayX / 1000, 1)}×${round(bayY / 1000, 1)}m within flat-slab range. Regular grid supports two-way action.`,
      limitation:
        maxBay > 8500 ? "May need drop panels at columns due to long span." : "None.",
      zones: zones.filter((z) => z.type === "open_plate").map((z) => z.id),
    });
    gravity.push({
      id: "gs-rc-beam-slab",
      system: "rc_beam_slab",
      plausibility: 0.84,
      rationale:
        "Beam-slab works for irregular bays and long spans. Higher structural depth.",
      limitation: "Drops floor-to-floor clearance by ~350mm per story.",
      zones: zones.filter((z) => z.type === "open_plate").map((z) => z.id),
    });
    gravity.push({
      id: "gs-pt-slab",
      system: "pt_slab",
      plausibility: maxBay >= 9000 ? 0.78 : 0.55,
      rationale: "Post-tensioned slab optimises for long spans with thin slabs.",
      limitation: "Requires specialist contractor and tight QA/QC.",
      zones: zones.filter((z) => z.type === "open_plate").map((z) => z.id),
    });
  } else if (input.material === "steel") {
    gravity.push({
      id: "gs-steel-beam-col",
      system: "steel_beam_column",
      plausibility: 0.9,
      rationale: "Steel frame well-suited to long spans and seismic ductility.",
      limitation: "Fire protection adds cost; fabrication lead times longer.",
      zones: zones.filter((z) => z.type === "open_plate").map((z) => z.id),
    });
    gravity.push({
      id: "gs-steel-composite",
      system: "steel_composite",
      plausibility: 0.86,
      rationale: "Composite deck with shear studs reduces steel tonnage.",
      limitation: "Requires continuous slab placement and QC.",
      zones: zones.filter((z) => z.type === "open_plate").map((z) => z.id),
    });
  } else {
    gravity.push({
      id: "gs-rc-flat",
      system: "rc_flat_slab",
      plausibility: 0.72,
      rationale: "Hybrid material suggests RC slab with steel framing possible.",
      limitation: "Material interface requires careful detailing.",
      zones: zones.filter((z) => z.type === "open_plate").map((z) => z.id),
    });
  }

  // Lateral system candidates
  const lateral: LateralSystemCandidate[] = [];
  if (graph.cores.length > 0) {
    lateral.push({
      id: "ls-core-shear",
      system: "rc_core_shear",
      plausibility: 0.9,
      location: "Central core (elevator + stairs)",
      rationale:
        "Core walls provide 2-way lateral resistance. Sufficient plan symmetry.",
      symmetryContribution: 0.88,
    });
  }
  lateral.push({
    id: "ls-moment-frame",
    system: input.material === "steel" ? "steel_moment" : "rc_moment_frame",
    plausibility: graph.cores.length ? 0.65 : 0.82,
    location: "Perimeter frames",
    rationale:
      "Perimeter moment frames provide torsional resistance and architectural flexibility.",
    symmetryContribution: 0.8,
  });

  // Constraint package
  const constraints: Constraint[] = [];
  if (graph.cores.length) {
    constraints.push({
      id: "con-1",
      type: "No support zone",
      priority: "hard",
      region: "Elevator shaft",
      value: "—",
      source: "Structural zoner",
      rationale: "Elevator shaft requires clear opening.",
      status: "met",
    });
  }
  constraints.push({
    id: "con-2",
    type: "Max span limit",
    priority: "hard",
    region: "Global",
    value: "12,000 mm",
    source: "Span mapper",
    rationale: "No RC system supports spans >12m without transfer.",
    status: maxBay > 12000 ? "violated" : "met",
  });
  constraints.push({
    id: "con-3",
    type: "Corridor clearance",
    priority: "hard",
    region: "Corridor C-1",
    value: "1m band",
    source: "Structural zoner",
    rationale: "No columns in primary circulation.",
    status: "met",
  });
  constraints.push({
    id: "con-4",
    type: "Vertical alignment",
    priority: "soft",
    region: "VA-Group 07",
    value: "—",
    source: "Vertical continuity",
    rationale: "Maintain column stack across all stories.",
    status: "met",
  });

  return {
    projectId: graph.projectId,
    zones,
    buildingRegularity: spanRegularity > 0.9 ? "regular" : "irregular",
    transferFloors: [1],
    framingDirection,
    framingConfidence: 0.88,
    maxSpanMm: maxBay,
    minSpanMm: minBay,
    typicalSpanMm: typical,
    spanRegularity,
    verticalAlignmentGroups: graph.grid.xAxes.length * graph.grid.yAxes.length,
    verticalAlignmentQuality: 1.0,
    gravitySystemCandidates: gravity.sort((a, b) => b.plausibility - a.plausibility),
    lateralSystemCandidates: lateral.sort(
      (a, b) => b.plausibility - a.plausibility,
    ),
    constraints,
  };
}

// Phase 3 mock load summary
export function generateLoadSummary(
  graph: BuildingGraph,
  input: StructuredInput,
) {
  const floorArea = (graph.lengthMm * graph.widthMm) / 1_000_000;
  const liveLoad =
    input.occupancy === "residential"
      ? 1.92
      : input.occupancy === "retail"
        ? 4.8
        : input.occupancy === "industrial"
          ? 12.0
          : 2.4;
  const deadLoad = input.material === "steel" ? 5.5 : 8.5;
  const facadeLoad = 3.2;
  const totalWeight = Math.round(
    (deadLoad + liveLoad * 0.4) * floorArea * graph.stories,
  );
  const windX = Math.round(totalWeight * 0.029);
  const windY = Math.round(totalWeight * 0.023);
  const seismicBase = Math.round(
    totalWeight *
      (input.seismicZone === "D" || input.seismicZone === "E"
        ? 0.05
        : input.seismicZone === "C"
          ? 0.035
          : 0.02),
  );
  return {
    deadLoadKnM2: deadLoad,
    liveLoadKnM2: liveLoad,
    facadeLoadKnM: facadeLoad,
    windBaseShearX: windX,
    windBaseShearY: windY,
    seismicBaseShearX: seismicBase,
    seismicBaseShearY: seismicBase,
    governingCombo: "1.2D + 1.0L + 1.0E",
    totalWeightKn: totalWeight,
    activeCombinations: [
      "1.4D",
      "1.2D + 1.6L",
      "1.2D + 1.0L + 1.0W",
      "1.2D + 1.0L + 1.0E",
      "0.9D + 1.0E",
    ],
  };
}

// Phase 5 mock analysis
export function generateAnalysis(graph: BuildingGraph) {
  const members = graph.columnCandidates.filter(
    (c) => c.classification !== "forbidden",
  );
  const membersTotal = members.length + graph.walls.length;
  const failing = members
    .filter((c) => c.score < 0.4)
    .slice(0, 3)
    .map((c, i) => ({
      elementId: c.id,
      check: i === 0 ? "axial" : "shear",
      ratio: round(1 + Math.random() * 0.08, 2),
    }));
  return {
    maxUtilization: 0.87,
    maxUtilizationElementId: members[0]?.id ?? "C-A1-F1",
    membersTotal,
    membersPassing: membersTotal - failing.length,
    membersFailing: failing,
    maxDriftRatio: "H/320",
    allowableDrift: "H/400",
    driftStatus: "fail" as const,
    maxSlabDeflection: "L/280",
    allowableDeflection: "L/360",
    deflectionStatus: "fail" as const,
  };
}

function round2(v: number, n = 2) {
  return Math.round(v * 10 ** n) / 10 ** n;
}
void round2;
