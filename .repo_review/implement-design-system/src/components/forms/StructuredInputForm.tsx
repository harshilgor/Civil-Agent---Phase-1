"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { FormField, FormSection } from "./FormField";
import { PlanPreview } from "./PlanPreview";
import { defaultStructuredInput, parseNaturalLanguage } from "@/lib/graph/nlParser";
import type {
  BuildingCode,
  CoreLocation,
  MaterialPreference,
  OccupancyType,
  StructuredInput,
} from "@/types/domain";
import { useProjectsStore } from "@/stores/projectsStore";
import { useHistoryStore } from "@/stores/historyStore";

export function StructuredInputForm({
  projectId,
  onSubmit,
}: {
  projectId?: string;
  onSubmit?: (id: string) => void;
}) {
  const router = useRouter();
  const getProject = useProjectsStore((s) => s.getProject);
  const createProject = useProjectsStore((s) => s.createProject);
  const updateInput = useProjectsStore((s) => s.updateInput);
  const regenerateGraph = useProjectsStore((s) => s.regenerateGraph);
  const addHistory = useHistoryStore((s) => s.add);

  const existing = projectId ? getProject(projectId) : null;
  const [input, setInput] = useState<StructuredInput>(
    existing?.input ?? defaultStructuredInput(),
  );
  const [nlText, setNlText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [flashedFields, setFlashedFields] = useState<Set<keyof StructuredInput>>(
    new Set(),
  );
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    geometry: true,
    classification: false,
    location: false,
    material: false,
    grid: false,
    core: false,
  });

  function patch(p: Partial<StructuredInput>) {
    setInput((s) => ({ ...s, ...p }));
  }

  async function handleParse() {
    if (!nlText.trim()) return;
    setParsing(true);
    await new Promise((r) => setTimeout(r, 600));
    const result = parseNaturalLanguage(nlText);
    patch(result.patch);
    setAssumptions(result.assumptions);
    setFlashedFields(new Set(result.filled));
    setParsing(false);
    toast.success(`Auto-filled ${result.filled.length} fields`);
    // Clear flash after animation
    setTimeout(() => setFlashedFields(new Set()), 1500);
  }

  function handleGenerate() {
    if (!input.buildingName.trim()) {
      toast.error("Give your project a name first.");
      return;
    }
    if (projectId) {
      updateInput(projectId, input);
      regenerateGraph(projectId);
      addHistory(projectId, "Updated input parameters");
      toast.success("Project inputs updated");
      onSubmit?.(projectId);
      router.push(`/projects/${projectId}/building-graph`);
      return;
    }
    const id = createProject(input);
    addHistory(id, "Project created");
    addHistory(id, "Building Graph generated", true);
    toast.success("Project created — Building Graph ready");
    onSubmit?.(id);
    router.push(`/projects/${id}/building-graph`);
  }

  function handleCancel() {
    router.push("/");
  }

  return (
    <div className="flex-1 min-h-0 overflow-hidden flex">
      {/* Form column */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        <div className="mx-auto max-w-[880px] px-vs-8 py-vs-6 flex flex-col gap-vs-5">
          <header className="flex flex-col gap-vs-1">
            <h1 className="font-headline text-headline-lg font-medium leading-none">
              {existing ? "Edit inputs" : "New project"}
            </h1>
            <p className="text-body-md text-on-surface-variant">
              Describe the building in plain English or fill in the structured
              form. A live plan preview updates as you type.
            </p>
          </header>

          {/* Natural language input */}
          <div className="border-hairline rounded-sm bg-surface-container-lowest p-vs-4 flex flex-col gap-vs-2">
            <div className="flex items-center gap-vs-2">
              <Sparkles
                className="w-3.5 h-3.5"
                style={{ color: "var(--fn-blue)" }}
                strokeWidth={1.5}
              />
              <span className="text-body-sm font-medium">
                Describe your building in plain English
              </span>
            </div>
            <textarea
              value={nlText}
              onChange={(e) => setNlText(e.target.value)}
              rows={3}
              placeholder={`e.g., "8-story RC office in San Francisco, 40x25m, minimize interior columns, central core"`}
              className="w-full bg-surface text-body-md font-sans border-hairline rounded-sm px-vs-3 py-vs-2 outline-none focus:border-secondary resize-none"
            />
            <div className="flex items-center justify-between">
              <span className="text-body-sm text-on-surface-variant">
                Parses dimensions, stories, material, core, occupancy, location, and
                more.
              </span>
              <button
                type="button"
                onClick={handleParse}
                disabled={parsing || !nlText.trim()}
                className="h-8 px-vs-3 inline-flex items-center gap-vs-2 rounded-sm bg-on-surface text-on-primary text-body-md font-medium disabled:opacity-40 hover:opacity-90 pressable"
              >
                {parsing ? (
                  <Loader2 className="w-3.5 h-3.5 spin-slow" strokeWidth={1.5} />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />
                )}
                {parsing ? "Parsing…" : "Parse"}
              </button>
            </div>
            {assumptions.length > 0 && (
              <div className="mt-vs-2 border-t-hairline pt-vs-2">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant mb-vs-1">
                  Assumptions made
                </div>
                <ul className="list-disc list-inside text-body-sm text-on-surface-variant">
                  {assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="flex items-center gap-vs-3 text-body-sm text-on-surface-variant">
            <div className="flex-1 border-t-hairline" />
            or fill in manually
            <div className="flex-1 border-t-hairline" />
          </div>

          {/* Section 1: Geometry */}
          <FormSection
            title="Building geometry"
            index={1}
            expanded={openSections.geometry}
            onToggle={() =>
              setOpenSections((o) => ({ ...o, geometry: !o.geometry }))
            }
          >
            <FormField label="Building name" flashed={flashedFields.has("buildingName")}>
              <TextInput
                value={input.buildingName}
                onChange={(v) => patch({ buildingName: v })}
                placeholder="e.g. Helix Tower"
              />
            </FormField>
            <div className="grid grid-cols-2 gap-vs-3">
              <FormField label="Length (m)" flashed={flashedFields.has("lengthM")}>
                <NumberInput
                  value={input.lengthM}
                  onChange={(v) => patch({ lengthM: v })}
                  min={5}
                  max={500}
                  step={0.5}
                />
              </FormField>
              <FormField label="Width (m)" flashed={flashedFields.has("widthM")}>
                <NumberInput
                  value={input.widthM}
                  onChange={(v) => patch({ widthM: v })}
                  min={5}
                  max={500}
                  step={0.5}
                />
              </FormField>
            </div>
            <div className="grid grid-cols-3 gap-vs-3">
              <FormField label="Stories" flashed={flashedFields.has("stories")}>
                <NumberInput
                  value={input.stories}
                  onChange={(v) => patch({ stories: Math.round(v) })}
                  min={1}
                  max={200}
                  step={1}
                />
              </FormField>
              <FormField
                label="Floor height (m)"
                flashed={flashedFields.has("typicalFloorHeightM")}
              >
                <NumberInput
                  value={input.typicalFloorHeightM}
                  onChange={(v) => patch({ typicalFloorHeightM: v })}
                  min={2.4}
                  max={20}
                  step={0.1}
                />
              </FormField>
              <FormField label="Roof type">
                <Select
                  value={input.roofType}
                  onChange={(v) => patch({ roofType: v as "flat" | "pitched" | "barrel" })}
                  options={[
                    { value: "flat", label: "Flat" },
                    { value: "pitched", label: "Pitched" },
                    { value: "barrel", label: "Barrel" },
                  ]}
                />
              </FormField>
            </div>
          </FormSection>

          {/* Section 2: Classification */}
          <FormSection
            title="Classification"
            index={2}
            expanded={openSections.classification}
            onToggle={() =>
              setOpenSections((o) => ({ ...o, classification: !o.classification }))
            }
          >
            <div className="grid grid-cols-2 gap-vs-3">
              <FormField label="Occupancy" flashed={flashedFields.has("occupancy")}>
                <Select
                  value={input.occupancy}
                  onChange={(v) => patch({ occupancy: v as OccupancyType })}
                  options={[
                    { value: "office", label: "Office" },
                    { value: "residential", label: "Residential" },
                    { value: "mixed_use", label: "Mixed-use" },
                    { value: "retail", label: "Retail" },
                    { value: "industrial", label: "Industrial" },
                    { value: "educational", label: "Educational" },
                    { value: "healthcare", label: "Healthcare" },
                    { value: "hospitality", label: "Hospitality" },
                  ]}
                />
              </FormField>
              <FormField label="Building code" flashed={flashedFields.has("buildingCode")}>
                <Select
                  value={input.buildingCode}
                  onChange={(v) => patch({ buildingCode: v as BuildingCode })}
                  options={[
                    { value: "IBC_2021", label: "IBC 2021" },
                    { value: "Eurocode", label: "Eurocode" },
                    { value: "IS_456", label: "IS 456" },
                    { value: "AS_3600", label: "AS 3600" },
                  ]}
                />
              </FormField>
              <FormField label="Importance factor">
                <Select
                  value={input.importanceFactor}
                  onChange={(v) =>
                    patch({ importanceFactor: v as "normal" | "essential" | "hazardous" })
                  }
                  options={[
                    { value: "normal", label: "Normal" },
                    { value: "essential", label: "Essential" },
                    { value: "hazardous", label: "Hazardous" },
                  ]}
                />
              </FormField>
            </div>
          </FormSection>

          {/* Section 3: Location */}
          <FormSection
            title="Location"
            index={3}
            expanded={openSections.location}
            onToggle={() =>
              setOpenSections((o) => ({ ...o, location: !o.location }))
            }
          >
            <FormField
              label="Location (city, country)"
              flashed={flashedFields.has("locationText")}
            >
              <TextInput
                value={input.locationText}
                onChange={(v) => patch({ locationText: v })}
                placeholder="e.g. San Francisco, CA"
              />
            </FormField>
            <div className="grid grid-cols-3 gap-vs-3">
              <FormField label="Seismic zone" flashed={flashedFields.has("seismicZone")}>
                <Select
                  value={input.seismicZone}
                  onChange={(v) => patch({ seismicZone: v as StructuredInput["seismicZone"] })}
                  options={[
                    { value: "A", label: "A" },
                    { value: "B", label: "B" },
                    { value: "C", label: "C" },
                    { value: "D", label: "D" },
                    { value: "E", label: "E" },
                  ]}
                />
              </FormField>
              <FormField
                label="Wind speed (mph)"
                flashed={flashedFields.has("windSpeedMph")}
              >
                <NumberInput
                  value={input.windSpeedMph}
                  onChange={(v) => patch({ windSpeedMph: v })}
                  min={40}
                  max={250}
                  step={5}
                />
              </FormField>
              <FormField label="Exposure category">
                <Select
                  value={input.exposureCategory}
                  onChange={(v) =>
                    patch({ exposureCategory: v as "B" | "C" | "D" })
                  }
                  options={[
                    { value: "B", label: "B" },
                    { value: "C", label: "C" },
                    { value: "D", label: "D" },
                  ]}
                />
              </FormField>
            </div>
          </FormSection>

          {/* Section 4: Material & Structure */}
          <FormSection
            title="Material & structure"
            index={4}
            expanded={openSections.material}
            onToggle={() =>
              setOpenSections((o) => ({ ...o, material: !o.material }))
            }
          >
            <FormField label="Material" flashed={flashedFields.has("material")}>
              <Segmented
                value={input.material}
                onChange={(v) => patch({ material: v as MaterialPreference })}
                options={[
                  { value: "rc", label: "Reinforced concrete" },
                  { value: "steel", label: "Structural steel" },
                  { value: "composite", label: "Composite" },
                  { value: "timber", label: "Timber" },
                ]}
              />
            </FormField>
            {input.material === "rc" && (
              <FormField label="Concrete grade">
                <Select
                  value={input.concreteGrade ?? "C30/37"}
                  onChange={(v) => patch({ concreteGrade: v })}
                  options={["C20/25", "C25/30", "C30/37", "C35/45", "C40/50"].map((g) => ({
                    value: g,
                    label: g,
                  }))}
                />
              </FormField>
            )}
            {input.material === "steel" && (
              <FormField label="Steel grade">
                <Select
                  value={input.steelGrade ?? "S355"}
                  onChange={(v) => patch({ steelGrade: v })}
                  options={["S235", "S275", "S355", "S420", "S460"].map((g) => ({
                    value: g,
                    label: g,
                  }))}
                />
              </FormField>
            )}
          </FormSection>

          {/* Section 5: Grid */}
          <FormSection
            title="Grid preferences"
            index={5}
            expanded={openSections.grid}
            onToggle={() => setOpenSections((o) => ({ ...o, grid: !o.grid }))}
          >
            <FormField label="Grid type">
              <Segmented
                value={input.gridType}
                onChange={(v) => patch({ gridType: v as "regular" | "irregular" | "auto" })}
                options={[
                  { value: "regular", label: "Regular" },
                  { value: "irregular", label: "Irregular" },
                  { value: "auto", label: "Auto-detect" },
                ]}
              />
            </FormField>
            <div className="grid grid-cols-2 gap-vs-3">
              <FormField
                label="Bay X (m)"
                flashed={flashedFields.has("preferredBayXM")}
              >
                <NumberInput
                  value={input.preferredBayXM}
                  onChange={(v) => patch({ preferredBayXM: v })}
                  min={3}
                  max={20}
                  step={0.5}
                />
              </FormField>
              <FormField
                label="Bay Y (m)"
                flashed={flashedFields.has("preferredBayYM")}
              >
                <NumberInput
                  value={input.preferredBayYM}
                  onChange={(v) => patch({ preferredBayYM: v })}
                  min={3}
                  max={20}
                  step={0.5}
                />
              </FormField>
              <FormField label="Min bay (m)">
                <NumberInput
                  value={input.minBayM}
                  onChange={(v) => patch({ minBayM: v })}
                  min={2}
                  max={10}
                  step={0.5}
                />
              </FormField>
              <FormField label="Max bay (m)">
                <NumberInput
                  value={input.maxBayM}
                  onChange={(v) => patch({ maxBayM: v })}
                  min={6}
                  max={20}
                  step={0.5}
                />
              </FormField>
            </div>
          </FormSection>

          {/* Section 6: Core */}
          <FormSection
            title="Core & constraints"
            index={6}
            expanded={openSections.core}
            onToggle={() => setOpenSections((o) => ({ ...o, core: !o.core }))}
          >
            <FormField label="Core location" flashed={flashedFields.has("coreLocation")}>
              <Segmented
                value={input.coreLocation}
                onChange={(v) => patch({ coreLocation: v as CoreLocation })}
                options={[
                  { value: "central", label: "Central" },
                  { value: "edge_north", label: "Edge-N" },
                  { value: "edge_south", label: "Edge-S" },
                  { value: "edge_east", label: "Edge-E" },
                  { value: "edge_west", label: "Edge-W" },
                  { value: "corner", label: "Corner" },
                  { value: "none", label: "None" },
                ]}
                wrap
              />
            </FormField>
            <FormField label="Core contains">
              <div className="flex flex-wrap gap-vs-2">
                {(
                  [
                    ["elevator", "Elevator"],
                    ["stairs", "Stairs"],
                    ["mep", "MEP"],
                    ["bathrooms", "Bathrooms"],
                  ] as const
                ).map(([key, label]) => (
                  <label
                    key={key}
                    className="inline-flex items-center gap-vs-2 h-8 px-vs-3 rounded-sm border-hairline bg-surface-container-lowest cursor-pointer hover:bg-surface-container-low"
                  >
                    <input
                      type="checkbox"
                      className="accent-[var(--secondary)]"
                      checked={input.coreContains[key]}
                      onChange={(e) =>
                        patch({
                          coreContains: {
                            ...input.coreContains,
                            [key]: e.target.checked,
                          },
                        })
                      }
                    />
                    <span className="text-body-sm">{label}</span>
                  </label>
                ))}
              </div>
            </FormField>
            <FormField
              label="No-column zones"
              flashed={flashedFields.has("noColumnZones")}
              hint="Free-form description of areas that must be column-free."
            >
              <textarea
                value={input.noColumnZones}
                onChange={(e) => patch({ noColumnZones: e.target.value })}
                rows={2}
                placeholder="e.g. No columns in main lobby area, or within 2m of south facade."
                className="w-full bg-surface-container-lowest text-body-md border-hairline rounded-sm px-vs-3 py-vs-2 outline-none focus:border-secondary resize-none"
              />
            </FormField>
            <FormField
              label="Span preferences"
              flashed={flashedFields.has("spanPreferences")}
            >
              <textarea
                value={input.spanPreferences}
                onChange={(e) => patch({ spanPreferences: e.target.value })}
                rows={2}
                placeholder="e.g. Prefer 8-10m spans in office areas; allow up to 12m in lobby."
                className="w-full bg-surface-container-lowest text-body-md border-hairline rounded-sm px-vs-3 py-vs-2 outline-none focus:border-secondary resize-none"
              />
            </FormField>
          </FormSection>

          <div className="flex items-center justify-between pt-vs-3 pb-vs-4 sticky bottom-0 bg-surface">
            <button
              type="button"
              onClick={handleCancel}
              className="h-10 px-vs-4 rounded-sm text-body-md hover:bg-surface-container-low"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleGenerate}
              className="h-10 px-vs-5 rounded-sm bg-on-surface text-on-primary font-headline text-title-sm font-medium hover:opacity-90 pressable"
            >
              {existing ? "Save inputs" : "Generate building graph"}
            </button>
          </div>
        </div>
      </div>

      {/* Live preview column */}
      <div className="w-[460px] shrink-0 border-l-hairline bg-surface-container-low p-vs-5 hidden lg:flex flex-col gap-vs-3">
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          Live plan preview
        </div>
        <PlanPreview input={input} />
      </div>
    </div>
  );
}

// Reusable tiny inputs -----------------------

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="h-8 px-vs-3 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary text-body-md font-sans"
    />
  );
}

function NumberInput({
  value,
  onChange,
  min,
  max,
  step,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => {
        const v = parseFloat(e.target.value);
        if (!Number.isNaN(v)) onChange(v);
      }}
      min={min}
      max={max}
      step={step}
      className="h-8 px-vs-3 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary font-mono text-body-md"
    />
  );
}

function Select<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="h-8 px-vs-2 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary text-body-md"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
  wrap,
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
  wrap?: boolean;
}) {
  return (
    <div
      className={[
        "inline-flex border-hairline rounded-sm bg-surface-container-lowest overflow-hidden",
        wrap ? "flex-wrap" : "",
      ].join(" ")}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={[
            "h-8 px-vs-3 text-body-sm border-l-hairline first:border-l-0 tonal-hover",
            o.value === value
              ? "bg-on-surface text-on-primary font-medium"
              : "hover:bg-surface-container-low",
          ].join(" ")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
