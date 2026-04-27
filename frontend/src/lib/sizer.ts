import type {
  ProjectV2,
  SizerComparisonResult,
  SizerLayout,
  SizerMemberResult,
  SizerPlanInput,
  SizerResult,
} from "@/types/domain";
import { sizerApiV1Url } from "@/lib/api";

export type SizerFormInput = {
  projectName: string;
  roomLengthFt: number;
  roomWidthFt: number;
  deadLoadPsf: number;
  liveLoadPsf: number;
  species: string;
  grade: string;
  layout: SizerLayout;
  beamMaterialPreference: "any" | "sawn" | "glulam" | "lvl_1.9E";
};

export function buildSizerPlan(input: SizerFormInput): SizerPlanInput {
  const length = input.roomLengthFt;
  const width = input.roomWidthFt;
  return {
    project_name: input.projectName.trim(),
    dimensions: {
      length_ft: length,
      width_ft: width,
    },
    load_parameters: {
      dead_load_psf: input.deadLoadPsf,
      live_load_psf: input.liveLoadPsf,
      species: input.species,
      grade: input.grade,
      deflection_live_limit: 360,
      deflection_total_limit: 240,
      soil_bearing_psf: 1500,
      service_condition: "dry",
      temperature_f: 70,
      incised: false,
      column_height_ft: 3,
      beam_material_preference: input.beamMaterialPreference,
    },
    layouts: [
      {
        name: "A",
        layout_type: "perimeter_support",
        joist_span_ft: width,
        joist_spacing_in: 16,
        description: "Joists span the room width and bear on perimeter supports.",
      },
      {
        name: "B",
        layout_type: "center_beam",
        joist_span_ft: width / 2,
        joist_spacing_in: 16,
        beam_span_ft: length / 2,
        beam_total_length_ft: length,
        beam_tributary_width_ft: width / 2,
        beam_span_config: "two_span_equal",
        description: "A center beam creates two joist bays and one midpoint column.",
      },
    ],
  };
}

export async function sizeSizerLayout(
  plan: SizerPlanInput,
  layout: SizerLayout,
): Promise<SizerResult> {
  return postSizer<SizerResult>("/size", { ...plan, layout }, 10_000);
}

export async function compareSizerLayouts(
  plan: SizerPlanInput,
): Promise<SizerComparisonResult> {
  return postSizer<SizerComparisonResult>("/size/compare", plan, 10_000);
}

export async function exportSizerPdf(result: SizerResult): Promise<Blob> {
  const response = await fetch(sizerApiV1Url("/export/pdf"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(result),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.blob();
}

async function postSizer<T>(path: string, body: unknown, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const id = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(sizerApiV1Url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(
        sizerHttpError(response.status, message) ||
          extractError(message) ||
          `Sizer API returned HTTP ${response.status}`,
      );
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Sizing timed out after 10 seconds.");
    }
    throw error;
  } finally {
    window.clearTimeout(id);
  }
}

function extractError(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: { error?: { message?: string } } };
    return parsed.detail?.error?.message ?? raw;
  } catch {
    return raw;
  }
}

function sizerHttpError(status: number, raw: string): string {
  if (status === 404 && raw.includes("DNS_HOSTNAME_RESOLVED_PRIVATE")) {
    return "Sizer API is not reachable from Vercel. Deploy the sizer API to a public URL and set SIZER_BACKEND_PROXY_URL on the frontend project.";
  }
  if (status === 404) {
    return "Sizer API proxy is not configured for this deployment. Set SIZER_BACKEND_PROXY_URL on Vercel and redeploy.";
  }
  return "";
}

export function getSelectedSizerResult(project: ProjectV2): SizerResult | null {
  const sizer = project.sizerProject;
  if (!sizer) return null;
  if (sizer.selectedLayout === "A") return sizer.layoutAResult ?? null;
  if (sizer.selectedLayout === "B") return sizer.layoutBResult ?? null;
  return sizer.layoutBResult ?? sizer.layoutAResult ?? null;
}

export function countSizerMembers(result: SizerResult | null): number {
  if (!result) return 0;
  return result.members.reduce((sum, member) => sum + (member.quantity || 1), 0);
}

export function materialLabel(member: SizerMemberResult): string {
  const parts = [
    member.material.nominal_size,
    shortMaterialType(member.material.material_type),
    member.material.species === "Douglas Fir-Larch" ? "DF-L" : member.material.species,
    member.material.grade,
  ].filter(Boolean);
  return parts.join(" ");
}

export function shortMaterialType(type: string): string {
  if (type === "sawn_lumber") return "Sawn";
  if (type === "glulam") return "Glulam";
  if (type === "lvl") return "LVL";
  if (type === "concrete") return "";
  return type.replace(/_/g, " ");
}

export function memberTitle(member: SizerMemberResult): string {
  if (member.member_type === "joist") return `Floor joists (${member.quantity})`;
  if (member.member_type === "beam") return "Centre beam";
  if (member.member_type === "column") return "Column";
  if (member.member_type === "spread_footing") return member.member_id.includes("MID") ? "Spread ftg - mid" : "Spread ftg - end";
  if (member.member_type === "strip_footing") return member.member_id.includes("SHORT") ? "Strip ftg - short" : "Strip ftg - long";
  return member.member_id;
}

export function governingCheck(member: SizerMemberResult): string {
  const raw = member.trace.governing_check ?? "governing";
  return raw.charAt(0).toUpperCase() + raw.slice(1).replace(/_/g, " ");
}

export function formatRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

export function formatMoney(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "$0";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatNumber(value: number | string | boolean | null | undefined): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  if (value == null) return "-";
  return String(value);
}

export function boardFeet(result: SizerResult | null): number {
  if (!result) return 0;
  return Math.round((result.summary.lumber_volume_ft3 + result.summary.glulam_volume_ft3) * 12);
}

export function governingMaterial(project: ProjectV2): string {
  const input = project.sizerProject?.inputParams;
  if (!input) return "DF-L No. 2";
  const species = input.load_parameters.species === "Douglas Fir-Larch" ? "DF-L" : input.load_parameters.species;
  return `${species} ${input.load_parameters.grade}`;
}

export function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
