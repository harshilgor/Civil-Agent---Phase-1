// Domain types for Civil Agent building + structural graphs.
// All coordinates are in millimetres, matching engineering intake conventions.

export type Point = [number, number];

export type PhaseId = 1 | 2 | 3 | 4 | 5;

export type PhaseStatus =
  | "not_started"
  | "queued"
  | "running"
  | "complete"
  | "failed";

export type PipelineStage =
  | "awaiting_input"
  | "parsing"
  | "graph_building"
  | "phase_2_running"
  | "phase_2_complete"
  | "phase_3_running"
  | "phase_3_complete"
  | "phase_5_running"
  | "phase_5_complete";

export type InputSource = "STRUCTURED" | "IFC" | "DXF" | "IMAGE";

export type ProjectStatus =
  | "COMPLETE"
  | "PROCESSING"
  | "NEEDS_REVIEW"
  | "FAILED";

export type MaterialPreference = "rc" | "steel" | "composite" | "timber";

export type CoreLocation =
  | "central"
  | "edge_north"
  | "edge_south"
  | "edge_east"
  | "edge_west"
  | "corner"
  | "none";

export type OccupancyType =
  | "office"
  | "residential"
  | "mixed_use"
  | "retail"
  | "industrial"
  | "educational"
  | "healthcare"
  | "hospitality";

export type BuildingCode = "IBC_2021" | "Eurocode" | "IS_456" | "AS_3600";

export type StructuredInput = {
  buildingName: string;
  description?: string;
  lengthM: number;
  widthM: number;
  stories: number;
  typicalFloorHeightM: number;
  groundFloorHeightM?: number;
  roofType: "flat" | "pitched" | "barrel";
  occupancy: OccupancyType;
  buildingCode: BuildingCode;
  importanceFactor: "normal" | "essential" | "hazardous";
  locationText: string;
  latitude?: number;
  longitude?: number;
  seismicZone: "A" | "B" | "C" | "D" | "E";
  windSpeedMph: number;
  exposureCategory: "B" | "C" | "D";
  material: MaterialPreference;
  concreteGrade?: string;
  steelGrade?: string;
  gridType: "regular" | "irregular" | "auto";
  preferredBayXM: number;
  preferredBayYM: number;
  minBayM: number;
  maxBayM: number;
  coreLocation: CoreLocation;
  coreContains: {
    elevator: boolean;
    stairs: boolean;
    mep: boolean;
    bathrooms: boolean;
  };
  noColumnZones: string;
  spanPreferences: string;
};

export type GridAxis = { label: string; positionMm: number };

export type Grid = {
  xAxes: GridAxis[]; // horizontal position, vertical line — label letters A,B,C
  yAxes: GridAxis[]; // vertical position, horizontal line — label numbers 1,2,3
};

export type WallType = "structural" | "partition" | "shear";

export type Wall = {
  id: string;
  type: WallType;
  thicknessMm: number;
  heightMm: number;
  start: Point;
  end: Point;
  stories: number[];
  material: string;
  confidence: number;
};

export type OpeningType = "door" | "window";

export type Opening = {
  id: string;
  wallId: string;
  type: OpeningType;
  tAlong: number; // 0..1 along wall
  widthMm: number;
  heightMm: number;
};

export type RoomType =
  | "office"
  | "corridor"
  | "lobby"
  | "bathroom"
  | "stair"
  | "elevator"
  | "mep"
  | "service"
  | "retail"
  | "open_plate";

export type Room = {
  id: string;
  label: string;
  type: RoomType;
  polygon: Point[];
  areaM2: number;
  floor: number;
};

export type Core = {
  id: string;
  label: string;
  polygon: Point[];
  floors: number[];
  contains: { elevator: boolean; stairs: boolean; mep: boolean; bathrooms: boolean };
};

export type SupportClass = "strong" | "secondary" | "weak" | "forbidden";

export type ScoreDecomposition = {
  gridAlignment: number;
  wallSupport: number;
  zoneCompatibility: number;
  perimeterFactor: number;
  tributaryArea: number;
};

export type ColumnCandidate = {
  id: string;
  position: Point;
  gridIntersection: string; // "B-3"
  floor: number;
  score: number;
  classification: SupportClass;
  decomposition: ScoreDecomposition;
  verticalAlignmentGroup: string | null;
  stackedAcrossAllFloors: boolean;
  tributaryAreaM2: number;
};

export type ZoneType =
  | "core"
  | "open_plate"
  | "corridor"
  | "perimeter"
  | "transfer_risk"
  | "high_clearance"
  | "double_height";

export type StructuralZone = {
  id: string;
  type: ZoneType;
  floor: number;
  polygon: Point[];
  areaM2: number;
  perimeterM: number;
  contains?: { elevator: boolean; stairs: boolean; mep: boolean; bathrooms: boolean };
  notes: string[];
};

export type BuildingGraph = {
  projectId: string;
  lengthMm: number;
  widthMm: number;
  perimeter: Point[];
  stories: number;
  storyHeightMm: number;
  groundStoryHeightMm: number;
  buildingCode: BuildingCode;
  grid: Grid;
  walls: Wall[];
  rooms: Room[];
  openings: Opening[];
  columnCandidates: ColumnCandidate[];
  cores: Core[];
  completeness: number;
  confidence: number;
  sectionScores: Record<string, number>;
  missingFields: string[];
  assumptions: string[];
  warnings: string[];
  inputSource: InputSource;
  processingMs: number;
};

export type StructuralGraph = {
  projectId: string;
  zones: StructuralZone[];
  buildingRegularity: "regular" | "irregular" | "complex";
  transferFloors: number[];
  framingDirection: "x" | "y";
  framingConfidence: number;
  maxSpanMm: number;
  minSpanMm: number;
  typicalSpanMm: number;
  spanRegularity: number;
  verticalAlignmentGroups: number;
  verticalAlignmentQuality: number;
  gravitySystemCandidates: GravitySystemCandidate[];
  lateralSystemCandidates: LateralSystemCandidate[];
  constraints: Constraint[];
};

export type GravitySystem =
  | "rc_flat_slab"
  | "rc_beam_slab"
  | "rc_one_way"
  | "rc_two_way"
  | "pt_slab"
  | "steel_beam_column"
  | "steel_composite";

export type GravitySystemCandidate = {
  id: string;
  system: GravitySystem;
  plausibility: number;
  rationale: string;
  limitation: string;
  zones: string[]; // zone ids
};

export type LateralSystem =
  | "rc_core_shear"
  | "rc_moment_frame"
  | "rc_dual"
  | "steel_braced"
  | "steel_moment";

export type LateralSystemCandidate = {
  id: string;
  system: LateralSystem;
  plausibility: number;
  location: string;
  rationale: string;
  symmetryContribution: number;
};

export type ConstraintPriority = "hard" | "soft";
export type ConstraintStatus = "met" | "partial" | "violated";

export type Constraint = {
  id: string;
  type: string;
  priority: ConstraintPriority;
  region: string;
  value: string;
  source: string;
  rationale: string;
  status: ConstraintStatus;
};

export type LoadSummary = {
  deadLoadKnM2: number;
  liveLoadKnM2: number;
  facadeLoadKnM: number;
  windBaseShearX: number;
  windBaseShearY: number;
  seismicBaseShearX: number;
  seismicBaseShearY: number;
  governingCombo: string;
  totalWeightKn: number;
  activeCombinations: string[];
};

export type AnalysisResult = {
  maxUtilization: number;
  maxUtilizationElementId: string;
  membersTotal: number;
  membersPassing: number;
  membersFailing: Array<{ elementId: string; check: string; ratio: number }>;
  maxDriftRatio: string; // "H/320"
  allowableDrift: string; // "H/400"
  driftStatus: "pass" | "fail";
  maxSlabDeflection: string;
  allowableDeflection: string;
  deflectionStatus: "pass" | "fail";
};

export type ProjectV2 = {
  id: string;
  name: string;
  description?: string;
  buildingType: string;
  subtitle: string;
  source: InputSource;
  createdAt: string;
  updatedAt: string;
  status: ProjectStatus;
  phase1Completeness: number;
  phase2Confidence: number;
  phaseStatus: Record<PhaseId, PhaseStatus>;
  pipelineStage: PipelineStage;
  input: StructuredInput;
  buildingGraph: BuildingGraph | null;
  structuralGraph: StructuralGraph | null;
  loadSummary: LoadSummary | null;
  analysis: AnalysisResult | null;
};
