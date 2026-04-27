"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { buildSizerPlan, sizeSizerLayout, type SizerFormInput } from "@/lib/sizer";
import { useProjectsStore } from "@/stores/projectsStore";
import { useSizerUiStore } from "@/stores/sizerUiStore";
import type { SizerLayout } from "@/types/domain";

type Errors = Partial<Record<keyof SizerFormInput | "api", string>>;

const inputClass =
  "h-9 w-full px-vs-3 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary text-body-md";
const numberClass = `${inputClass} font-mono`;
const labelClass =
  "text-[10px] uppercase tracking-[0.12em] font-mono text-on-surface-variant";

export default function NewSizerProjectPage() {
  const router = useRouter();
  const createSizerProject = useProjectsStore((s) => s.createSizerProject);
  const setSizingInProgress = useSizerUiStore((s) => s.setSizingInProgress);
  const [input, setInput] = useState<SizerFormInput>({
    projectName: "Kitchen addition - 24 Temple Drive",
    roomLengthFt: 24,
    roomWidthFt: 16,
    deadLoadPsf: 15,
    liveLoadPsf: 40,
    species: "Douglas Fir-Larch",
    grade: "No. 2",
    layout: "B",
    beamMaterialPreference: "any",
  });
  const [errors, setErrors] = useState<Errors>({});
  const [loading, setLoading] = useState(false);

  const plan = useMemo(() => buildSizerPlan(input), [input]);

  function patch(patchValue: Partial<SizerFormInput>) {
    setInput((current) => ({ ...current, ...patchValue }));
    setErrors((current) => ({ ...current, api: undefined }));
  }

  async function submit() {
    const nextErrors = validate(input);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setLoading(true);
    setSizingInProgress(true);
    try {
      const result = await sizeSizerLayout(plan, input.layout);
      const id = createSizerProject({
        inputParams: plan,
        selectedLayout: input.layout,
        result,
      });
      toast.success("Wood framing sized.");
      router.push(`/projects/${id}/sizer/overview`);
    } catch (error) {
      setErrors({
        api: error instanceof Error ? error.message : "The sizing run failed.",
      });
    } finally {
      setLoading(false);
      setSizingInProgress(false);
    }
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
      <div className="mx-auto max-w-[760px] px-vs-8 py-vs-6 flex flex-col gap-vs-6">
        <header className="flex flex-col gap-vs-1">
          <h1 className="font-headline text-headline-lg font-medium leading-none">
            Wood Framing - Sizer
          </h1>
          <p className="text-body-md text-on-surface-variant">
            Residential gravity sizing for joists, beams, columns, and footings.
          </p>
        </header>

        <FormSection title="Project">
          <Field label="Project name" error={errors.projectName}>
            <input
              value={input.projectName}
              onChange={(e) => patch({ projectName: e.target.value })}
              className={inputClass}
            />
          </Field>
        </FormSection>

        <FormSection title="Geometry">
          <Field label="Room length (ft)" error={errors.roomLengthFt}>
            <input
              type="number"
              value={input.roomLengthFt}
              onChange={(e) => patch({ roomLengthFt: Number(e.target.value) })}
              min={4}
              max={60}
              step={0.5}
              className={numberClass}
            />
          </Field>
          <Field label="Room width (ft)" error={errors.roomWidthFt}>
            <input
              type="number"
              value={input.roomWidthFt}
              onChange={(e) => patch({ roomWidthFt: Number(e.target.value) })}
              min={4}
              max={60}
              step={0.5}
              className={numberClass}
            />
          </Field>
        </FormSection>

        <FormSection title="Loads">
          <Field label="Dead load (psf)" error={errors.deadLoadPsf} hint="Floor assembly weight. Default 15 psf.">
            <input
              type="number"
              value={input.deadLoadPsf}
              onChange={(e) => patch({ deadLoadPsf: Number(e.target.value) })}
              min={5}
              max={50}
              step={1}
              className={numberClass}
            />
          </Field>
          <Field label="Live load (psf)" error={errors.liveLoadPsf} hint="ASCE 7-22 Table 4.3-1 residential occupancy.">
            <input
              type="number"
              value={input.liveLoadPsf}
              onChange={(e) => patch({ liveLoadPsf: Number(e.target.value) })}
              min={20}
              max={100}
              step={1}
              className={numberClass}
            />
          </Field>
        </FormSection>

        <FormSection title="Material">
          <Field label="Species">
            <select
              value={input.species}
              onChange={(e) => patch({ species: e.target.value })}
              className={inputClass}
            >
              <option>Douglas Fir-Larch</option>
              <option>Southern Pine</option>
            </select>
          </Field>
          <Field label="Grade">
            <select
              value={input.grade}
              onChange={(e) => patch({ grade: e.target.value })}
              className={inputClass}
            >
              <option>No. 2</option>
              <option>No. 1</option>
              <option>Select Structural</option>
            </select>
          </Field>
        </FormSection>

        <FormSection title="Layout">
          <LayoutChoice
            value="A"
            selected={input.layout}
            title="Layout A - Perimeter support"
            description="Joists span full width. Continuous footings on all sides. No interior beam."
            onSelect={(layout) => patch({ layout })}
          />
          <LayoutChoice
            value="B"
            selected={input.layout}
            title="Layout B - Centre beam"
            description="A beam divides the room into two bays. Shorter joists. Spread footings under beam ends and column."
            onSelect={(layout) => patch({ layout })}
          />
          {input.layout === "B" && (
            <Field label="Beam material preference">
              <select
                value={input.beamMaterialPreference}
                onChange={(e) =>
                  patch({
                    beamMaterialPreference: e.target.value as SizerFormInput["beamMaterialPreference"],
                  })
                }
                className={inputClass}
              >
                <option value="any">Any - engine selects cheapest</option>
                <option value="sawn">Sawn lumber</option>
                <option value="glulam">Glulam</option>
                <option value="lvl_1.9E">LVL 1.9E</option>
              </select>
            </Field>
          )}
        </FormSection>

        {errors.api && (
          <div className="border-hairline rounded-sm bg-surface-container-low px-vs-3 py-vs-2 text-body-sm text-error">
            {errors.api}
          </div>
        )}

        <div className="flex items-center justify-between pt-vs-3 border-t-hairline">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="h-10 px-vs-4 rounded-sm text-body-md hover:bg-surface-container-low"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={loading}
            className="h-10 px-vs-5 rounded-sm bg-on-surface text-on-primary font-headline text-title-sm font-medium hover:opacity-90 pressable inline-flex items-center gap-vs-2 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 spin-slow" strokeWidth={1.5} />
            ) : (
              <ArrowRight className="w-4 h-4" strokeWidth={1.5} />
            )}
            {loading ? "Sizing..." : "Size framing"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-vs-4">
      <div className="flex items-center gap-vs-3">
        <div className="text-[10px] uppercase tracking-[0.12em] font-mono text-on-surface-variant">
          {title}
        </div>
        <div className="flex-1 border-t-hairline" />
      </div>
      {children}
    </section>
  );
}

function Field({
  label,
  children,
  hint,
  error,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
  error?: string;
}) {
  return (
    <label className="flex flex-col gap-vs-1">
      <span className={labelClass}>{label}</span>
      {children}
      {hint && <span className="text-body-sm text-on-surface-variant/80">{hint}</span>}
      {error && <span className="text-body-sm text-error">{error}</span>}
    </label>
  );
}

function LayoutChoice({
  value,
  selected,
  title,
  description,
  onSelect,
}: {
  value: SizerLayout;
  selected: SizerLayout;
  title: string;
  description: string;
  onSelect: (value: SizerLayout) => void;
}) {
  const active = value === selected;
  return (
    <button
      type="button"
      onClick={() => onSelect(value)}
      className={[
        "w-full border-hairline rounded-sm bg-surface-container-lowest px-vs-3 py-vs-3 text-left flex gap-vs-3 tonal-hover hover:bg-surface-container-low",
        active ? "outline outline-1 outline-offset-2 outline-secondary" : "",
      ].join(" ")}
    >
      <span
        className="mt-[2px] w-3.5 h-3.5 rounded-full border-hairline shrink-0"
        style={{ background: active ? "var(--on-surface)" : "transparent" }}
      />
      <span className="flex flex-col gap-vs-1">
        <span className="font-headline text-title-sm font-medium">{title}</span>
        <span className="text-body-sm text-on-surface-variant max-w-[560px]">
          {description}
        </span>
      </span>
    </button>
  );
}

function validate(input: SizerFormInput): Errors {
  const errors: Errors = {};
  if (!input.projectName.trim()) errors.projectName = "Project name is required.";
  if (input.roomLengthFt < 4 || input.roomLengthFt > 60) {
    errors.roomLengthFt = "Room length must be between 4 ft and 60 ft.";
  }
  if (input.roomWidthFt < 4 || input.roomWidthFt > 60) {
    errors.roomWidthFt = "Room width must be between 4 ft and 60 ft.";
  }
  if (input.deadLoadPsf < 5 || input.deadLoadPsf > 50) {
    errors.deadLoadPsf = "Dead load must be between 5 psf and 50 psf.";
  }
  if (input.liveLoadPsf < 20 || input.liveLoadPsf > 100) {
    errors.liveLoadPsf = "Live load must be between 20 psf and 100 psf.";
  }
  return errors;
}
