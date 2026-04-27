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

export type InputSource = "STRUCTURED" | "IFC" | "DXF" | "IMAGE" | "SIZER";
export type ProjectType = "building_graph" | "wood_framing_sizer";

export const WOOD_FRAMING_SIZER = "wood_framing_sizer" as const;

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

export type SizerLayout = "A" | "B";

export type SizerLoadParameters = {
  dead_load_psf: number;
  live_load_psf: number;
  species: string;
  grade: string;
  deflection_live_limit?: number;
  deflection_total_limit?: number;
  soil_bearing_psf?: number;
  service_condition?: "dry";
  temperature_f?: number;
  incised?: boolean;
  column_height_ft?: number;
  beam_material_preference?: "any" | "sawn" | "glulam" | "lvl_1.9E" | "lvl_2.0E";
};

export type SizerPlanInput = {
  project_name: string;
  dimensions: {
    length_ft: number;
    width_ft: number;
  };
  load_parameters: SizerLoadParameters;
  layouts: Array<{
    name: SizerLayout;
    layout_type: "perimeter_support" | "center_beam";
    joist_span_ft: number;
    joist_spacing_in: number;
    description?: string;
    beam_span_ft?: number;
    beam_total_length_ft?: number;
    beam_tributary_width_ft?: number;
    beam_span_config?: "simple" | "two_span_equal" | "three_span_equal";
  }>;
};

export type SizerTraceValue = {
  name: string;
  value: number | string | boolean;
  unit?: string | null;
  source: string;
  confidence?: string | null;
};

export type SizerCodeCheck = {
  name: string;
  demand: number;
  capacity: number;
  unit: string;
  ratio: number;
  passed: boolean;
  source: string;
  equation: string;
  details?: Record<string, unknown>;
};

export type SizerMaterialSpec = {
  material_type: "sawn_lumber" | "glulam" | "lvl" | "concrete";
  species?: string | null;
  grade?: string | null;
  nominal_size?: string | null;
  actual_width_in?: number | null;
  actual_depth_in?: number | null;
};

export type SizerMemberResult = {
  member_id: string;
  member_type: string;
  selected: boolean;
  material: SizerMaterialSpec;
  span_ft?: number | null;
  length_ft?: number | null;
  spacing_in?: number | null;
  quantity: number;
  trace: {
    member_id: string;
    member_type: string;
    material: SizerMaterialSpec;
    span_ft?: number | null;
    length_ft?: number | null;
    spacing_in?: number | null;
    span_config?: string | null;
    loads: Array<SizerTraceValue & { load_type?: string | null }>;
    section_properties: SizerTraceValue[];
    reference_design_values: SizerTraceValue[];
    adjusted_design_values: SizerTraceValue[];
    adjustment_factors: Array<{
      symbol: string;
      name: string;
      value: number;
      applies_to: string[];
      source: string;
      confidence?: string | null;
      note?: string | null;
    }>;
    checks: SizerCodeCheck[];
    connections?: Record<string, {
      interface: string;
      demand_lb: number;
      product: string;
      allowable_load_lb: number;
      utilisation: number;
      source: string;
      note: string;
      warning?: string | null;
    }>;
    governing_check?: string | null;
    final_utilization: number;
    warning?: string | null;
    passed: boolean;
    assumptions: string[];
  };
};

export type SizerResult = {
  project_name: string;
  layout: SizerLayout;
  members: SizerMemberResult[];
  summary: {
    lumber_volume_ft3: number;
    glulam_volume_ft3: number;
    concrete_volume_ft3: number;
    joist_count: number;
    footing_count: number;
    span_count: number;
    cost_estimate?: {
      lumber_installed_dollars: number;
      concrete_dollars: number;
      hardware_dollars: number;
      total_dollars: number;
      currency: "USD";
    };
  };
  assumptions: Array<{ description: string; source: string }>;
  questions: string[];
};

export type SizerComparisonResult = {
  layout_a: SizerResult;
  layout_b: SizerResult;
  comparison: {
    cost_difference_dollars: number;
    cheaper_layout: SizerLayout;
    lumber_volume_difference_ft3: number;
  };
};

export type SizerProjectData = {
  status: "in_progress" | "complete" | "needs_review";
  selectedLayout: SizerLayout | null;
  inputParams: SizerPlanInput;
  layoutAResult?: SizerResult | null;
  layoutBResult?: SizerResult | null;
  comparisonResult?: SizerComparisonResult["comparison"] | null;
};

export type ProjectV2 = {
  id: string;
  projectType: ProjectType;
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
  sizerProject?: SizerProjectData | null;
};
