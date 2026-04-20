import type {
  BuildingCode,
  CoreLocation,
  MaterialPreference,
  OccupancyType,
  StructuredInput,
} from "@/types/domain";

type ParseResult = {
  patch: Partial<StructuredInput>;
  filled: (keyof StructuredInput)[];
  assumptions: string[];
};

// Lightweight, deterministic rule-based "LLM" for the input autofill.
// This runs entirely client-side — no network required.
export function parseNaturalLanguage(text: string): ParseResult {
  const src = text.toLowerCase();
  const patch: Partial<StructuredInput> = {};
  const filled: (keyof StructuredInput)[] = [];
  const assumptions: string[] = [];

  // Stories
  const storyMatch = src.match(/(\d{1,3})[-\s]?(?:story|stories|floor|floors|level|levels)/);
  if (storyMatch) {
    patch.stories = Math.min(200, Math.max(1, parseInt(storyMatch[1], 10)));
    filled.push("stories");
  }

  // Dimensions: "40x25m", "40 x 25 m", "40 by 25 metres"
  const dimMatch =
    src.match(/(\d{1,3}(?:\.\d+)?)\s*(?:x|by|\*|×)\s*(\d{1,3}(?:\.\d+)?)\s*m/);
  if (dimMatch) {
    const a = parseFloat(dimMatch[1]);
    const b = parseFloat(dimMatch[2]);
    patch.lengthM = Math.max(a, b);
    patch.widthM = Math.min(a, b);
    filled.push("lengthM", "widthM");
  }

  // Material
  const materialMap: Array<[RegExp, MaterialPreference]> = [
    [/\b(reinforced\s+concrete|rc|r\.c\.|concrete)\b/, "rc"],
    [/\b(structural\s+steel|steel\s+frame|steel)\b/, "steel"],
    [/\b(composite)\b/, "composite"],
    [/\b(clt|glulam|mass\s+timber|timber|wood)\b/, "timber"],
  ];
  for (const [re, value] of materialMap) {
    if (re.test(src)) {
      patch.material = value;
      filled.push("material");
      break;
    }
  }

  // Occupancy
  const occMap: Array<[RegExp, OccupancyType]> = [
    [/\b(office|commercial)\b/, "office"],
    [/\b(residential|apartments?|condo|housing)\b/, "residential"],
    [/\b(mixed[-\s]?use)\b/, "mixed_use"],
    [/\b(retail|shopping|mall)\b/, "retail"],
    [/\b(industrial|warehouse|logistics|factory)\b/, "industrial"],
    [/\b(school|educational|university|college)\b/, "educational"],
    [/\b(hospital|clinic|healthcare|medical)\b/, "healthcare"],
    [/\b(hotel|hospitality|resort)\b/, "hospitality"],
  ];
  for (const [re, value] of occMap) {
    if (re.test(src)) {
      patch.occupancy = value;
      filled.push("occupancy");
      break;
    }
  }

  // Core
  if (/\bno\s+core\b/.test(src)) {
    patch.coreLocation = "none";
    filled.push("coreLocation");
  } else if (/\bcentral\s+core\b|\bcore\s+in\s+the\s+(middle|center|centre)\b/.test(src)) {
    patch.coreLocation = "central";
    filled.push("coreLocation");
  } else if (/\bedge\s+core\b|\bcore\s+on\s+the\s+(north|south|east|west)\b/.test(src)) {
    const m = src.match(/core\s+on\s+the\s+(north|south|east|west)/);
    patch.coreLocation = m ? (`edge_${m[1]}` as CoreLocation) : "edge_north";
    filled.push("coreLocation");
  } else if (/\bcorner\s+core\b/.test(src)) {
    patch.coreLocation = "corner";
    filled.push("coreLocation");
  }

  // Bays
  const bayMatch = src.match(/(\d{1,2}(?:\.\d+)?)\s*m\s*(?:x|by|×)\s*(\d{1,2}(?:\.\d+)?)\s*m\s*(?:bay|grid)/);
  if (bayMatch) {
    patch.preferredBayXM = parseFloat(bayMatch[1]);
    patch.preferredBayYM = parseFloat(bayMatch[2]);
    filled.push("preferredBayXM", "preferredBayYM");
  } else {
    const bayUniform = src.match(/(\d{1,2}(?:\.\d+)?)\s*m\s*bay/);
    if (bayUniform) {
      const v = parseFloat(bayUniform[1]);
      patch.preferredBayXM = v;
      patch.preferredBayYM = v;
      filled.push("preferredBayXM", "preferredBayYM");
    }
  }

  // Location (well-known list)
  const locations: Array<[RegExp, { lat: number; lng: number; seismic: "A" | "B" | "C" | "D" | "E"; wind: number }]> =
    [
      [/san\s+francisco/, { lat: 37.77, lng: -122.42, seismic: "D", wind: 85 }],
      [/los\s+angeles|l\.?a\./, { lat: 34.05, lng: -118.24, seismic: "D", wind: 85 }],
      [/new\s+york|nyc|manhattan/, { lat: 40.71, lng: -74.0, seismic: "B", wind: 115 }],
      [/chicago/, { lat: 41.88, lng: -87.63, seismic: "A", wind: 105 }],
      [/seattle/, { lat: 47.61, lng: -122.33, seismic: "D", wind: 85 }],
      [/miami/, { lat: 25.76, lng: -80.19, seismic: "A", wind: 175 }],
      [/tokyo/, { lat: 35.68, lng: 139.76, seismic: "D", wind: 115 }],
      [/london/, { lat: 51.51, lng: -0.13, seismic: "A", wind: 95 }],
      [/dubai/, { lat: 25.2, lng: 55.27, seismic: "B", wind: 105 }],
      [/mumbai/, { lat: 19.08, lng: 72.88, seismic: "D", wind: 125 }],
    ];
  for (const [re, meta] of locations) {
    if (re.test(src)) {
      const label =
        src.match(/in\s+([a-z\s]+?)(?:,|\.|$)/)?.[1]?.trim() ??
        re.source.split("|")[0].replace(/\\s\+/g, " ");
      patch.locationText = label.replace(/\b\w/g, (c) => c.toUpperCase());
      patch.latitude = meta.lat;
      patch.longitude = meta.lng;
      patch.seismicZone = meta.seismic;
      patch.windSpeedMph = meta.wind;
      filled.push("locationText", "latitude", "longitude", "seismicZone", "windSpeedMph");
      break;
    }
  }

  // Code inference from location
  if (patch.locationText || /\bibc\b/.test(src)) {
    if (/eurocode|europe|uk|london|paris|berlin/.test(src))
      patch.buildingCode = "Eurocode";
    else if (/india|mumbai|delhi|bangalore|bengaluru/.test(src))
      patch.buildingCode = "IS_456";
    else if (/australia|sydney|melbourne/.test(src)) patch.buildingCode = "AS_3600";
    else patch.buildingCode = "IBC_2021";
    filled.push("buildingCode" as keyof StructuredInput);
  }

  // Floor height
  const fhMatch = src.match(/(?:floor[-\s]?to[-\s]?floor|storey\s+height|floor\s+height).{0,8}?(\d{1,2}(?:\.\d+)?)\s*m/);
  if (fhMatch) {
    patch.typicalFloorHeightM = parseFloat(fhMatch[1]);
    filled.push("typicalFloorHeightM");
  } else if (src.match(/\b(typical|standard)\s+office\b/)) {
    assumptions.push("Assumed typical office floor-to-floor of 3.9m.");
  }

  // Minimize/prefer interior columns
  if (/minim\w*\s+(interior\s+)?column/.test(src)) {
    patch.spanPreferences =
      (patch.spanPreferences ?? "") +
      "Minimize interior columns. Prefer longer spans.";
    filled.push("spanPreferences");
  }

  // Building name inference (quoted text or "called X")
  const nameMatch =
    text.match(/"([^"]{2,60})"/) ?? text.match(/called\s+([A-Z][\w\s-]{1,50})/);
  if (nameMatch) {
    patch.buildingName = nameMatch[1].trim();
    filled.push("buildingName");
  }

  return { patch, filled, assumptions };
}

export function defaultStructuredInput(): StructuredInput {
  return {
    buildingName: "",
    description: "",
    lengthM: 40,
    widthM: 25,
    stories: 6,
    typicalFloorHeightM: 3.9,
    roofType: "flat",
    occupancy: "office",
    buildingCode: "IBC_2021" as BuildingCode,
    importanceFactor: "normal",
    locationText: "",
    seismicZone: "B",
    windSpeedMph: 95,
    exposureCategory: "B",
    material: "rc",
    concreteGrade: "C30/37",
    gridType: "regular",
    preferredBayXM: 8,
    preferredBayYM: 8,
    minBayM: 4,
    maxBayM: 15,
    coreLocation: "central",
    coreContains: { elevator: true, stairs: true, mep: false, bathrooms: true },
    noColumnZones: "",
    spanPreferences: "",
  };
}
