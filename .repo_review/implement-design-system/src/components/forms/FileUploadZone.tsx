"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useDropzone } from "react-dropzone";
import { Check, CheckCircle2, Circle, CloudUpload, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { useProjectsStore } from "@/stores/projectsStore";
import { defaultStructuredInput } from "@/lib/graph/nlParser";
import { useHistoryStore } from "@/stores/historyStore";
import type { InputSource, OccupancyType, StructuredInput } from "@/types/domain";

type StageStatus = "pending" | "running" | "done" | "failed" | "warn";

type Stage = {
  id: string;
  label: string;
  status: StageStatus;
  durationMs?: number;
  warning?: string;
};

function guessSource(name: string): InputSource {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "ifc") return "IFC";
  if (ext === "dxf" || ext === "dwg") return "DXF";
  if (["png", "jpg", "jpeg", "pdf"].includes(ext)) return "IMAGE";
  return "STRUCTURED";
}

function stagesFor(source: InputSource): Stage[] {
  if (source === "IMAGE") {
    return [
      { id: "upload", label: "File uploaded", status: "done", durationMs: 200 },
      { id: "preprocess", label: "Preprocessing (deskew, denoise)", status: "pending" },
      { id: "walls", label: "Wall segmentation (U-Net)", status: "pending" },
      { id: "rooms", label: "Room segmentation (SAM 2.1)", status: "pending" },
      { id: "symbols", label: "Symbol detection (YOLOv8)", status: "pending" },
      { id: "ocr", label: "OCR extraction (PaddleOCR + PARSeq)", status: "pending" },
      { id: "vectorize", label: "Vectorization", status: "pending" },
      { id: "grid", label: "Grid inference", status: "pending" },
      { id: "graph", label: "Building Graph construction", status: "pending" },
      { id: "phase2", label: "Phase 2 analysis", status: "pending" },
    ];
  }
  if (source === "IFC" || source === "DXF") {
    return [
      { id: "upload", label: "File uploaded", status: "done", durationMs: 200 },
      { id: "format", label: `Format detected: ${source}`, status: "done", durationMs: 100 },
      { id: "geom", label: "Geometry parsed", status: "pending" },
      { id: "graph", label: "Building Graph construction", status: "pending" },
      { id: "phase2", label: "Phase 2 analysis", status: "pending" },
    ];
  }
  return [];
}

export function FileUploadZone() {
  const router = useRouter();
  const createProject = useProjectsStore((s) => s.createProject);
  const addHistory = useHistoryStore((s) => s.add);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<InputSource>("IFC");
  const [stages, setStages] = useState<Stage[]>([]);
  const [supplement, setSupplement] = useState({
    stories: 6,
    floorHeight: 3.9,
    occupancy: "office" as OccupancyType,
    location: "",
    material: "rc" as StructuredInput["material"],
  });
  const [done, setDone] = useState(false);

  const onDrop = useCallback(
    (accepted: File[]) => {
      const f = accepted[0];
      if (!f) return;
      const src = guessSource(f.name);
      setFile(f);
      setSource(src);
      setStages(stagesFor(src));
      setDone(false);
    },
    [],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxFiles: 1,
    maxSize: 100 * 1024 * 1024,
    accept: {
      "application/octet-stream": [".ifc", ".dxf", ".dwg"],
      "application/pdf": [".pdf"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
    },
  });

  // Drive the simulated pipeline
  useEffect(() => {
    if (!file || stages.length === 0) return;
    const nextIdx = stages.findIndex((s) => s.status === "pending" || s.status === "running");
    if (nextIdx < 0) {
      setDone(true);
      return;
    }
    const current = stages[nextIdx];
    if (current.status === "pending") {
      setStages((s) =>
        s.map((st, i) => (i === nextIdx ? { ...st, status: "running" } : st)),
      );
      return;
    }
    // running → complete after timeout
    const durations: Record<string, number> = {
      preprocess: 1200,
      walls: 2200,
      rooms: 1800,
      symbols: 1400,
      ocr: 1600,
      vectorize: 900,
      grid: 800,
      geom: 3800,
      graph: 1100,
      phase2: 1500,
    };
    const d = durations[current.id] ?? 700;
    const timer = setTimeout(() => {
      setStages((s) =>
        s.map((st, i) =>
          i === nextIdx
            ? {
                ...st,
                status: current.id === "walls" && source === "IMAGE" ? "warn" : "done",
                durationMs: d,
                warning:
                  current.id === "walls" && source === "IMAGE"
                    ? "Wall segmentation confidence: 0.62 — results may need review"
                    : undefined,
              }
            : st,
        ),
      );
    }, d);
    return () => clearTimeout(timer);
  }, [stages, file, source]);

  const progress = useMemo(() => {
    if (stages.length === 0) return 0;
    const completed = stages.filter((s) => s.status === "done" || s.status === "warn").length;
    return completed / stages.length;
  }, [stages]);

  function handleViewGraph() {
    if (!file) return;
    const input: StructuredInput = {
      ...defaultStructuredInput(),
      buildingName: file.name.replace(/\.[^.]+$/, ""),
      stories: supplement.stories,
      typicalFloorHeightM: supplement.floorHeight,
      occupancy: supplement.occupancy,
      locationText: supplement.location,
      material: supplement.material,
    };
    const id = createProject(input);
    addHistory(id, `Imported from ${file.name}`);
    addHistory(id, "Building Graph generated", true);
    toast.success("Imported — Building Graph ready");
    router.push(`/projects/${id}/building-graph`);
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-[820px] px-vs-6 py-vs-6 flex flex-col gap-vs-5">
        <header>
          <h1 className="font-headline text-headline-lg font-medium leading-none">
            Upload floor plan
          </h1>
          <p className="text-body-md text-on-surface-variant mt-vs-1">
            Drop an IFC, DXF/DWG, PDF, or scan. Civil Agent preprocesses it and
            produces a Building Graph.
          </p>
        </header>

        {!file && (
          <div
            {...getRootProps()}
            className={[
              "rounded-sm bg-surface-container-lowest flex flex-col items-center justify-center gap-vs-3 py-vs-16 cursor-pointer tonal-hover",
              isDragActive
                ? "border border-solid border-secondary bg-surface-container-low"
                : "dashed-hairline hover:bg-surface-container-low",
            ].join(" ")}
          >
            <input {...getInputProps()} />
            <CloudUpload
              className="w-8 h-8 text-on-surface-variant"
              strokeWidth={1.25}
            />
            <div className="text-title-md font-medium">
              {isDragActive ? "Drop file here" : "Drag & drop files or click to browse"}
            </div>
            <div className="text-body-sm text-on-surface-variant text-center max-w-[420px]">
              DXF · DWG · IFC · PDF · PNG · JPEG · Maximum file size 100 MB ·
              Multiple files allowed for multi-floor plans.
            </div>
          </div>
        )}

        {file && (
          <div className="border-hairline rounded-sm bg-surface-container-lowest p-vs-4 flex flex-col gap-vs-3">
            <div className="flex items-center justify-between gap-vs-3">
              <div className="flex items-center gap-vs-3 min-w-0">
                <div className="flex flex-col min-w-0">
                  <span className="text-title-sm font-medium truncate">{file.name}</span>
                  <span className="text-body-sm text-on-surface-variant">
                    {(file.size / 1024 / 1024).toFixed(1)} MB · source: {source}
                  </span>
                </div>
              </div>
              {!done ? (
                <div className="flex items-center gap-vs-2">
                  <Loader2
                    className="w-3.5 h-3.5 spin-slow"
                    style={{ color: "var(--fn-blue)" }}
                    strokeWidth={1.5}
                  />
                  <span className="text-body-sm text-on-surface-variant">
                    {Math.round(progress * 100)}%
                  </span>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setFile(null);
                    setStages([]);
                    setDone(false);
                  }}
                  className="text-body-sm text-on-surface-variant hover:text-on-surface inline-flex items-center gap-vs-1"
                >
                  <X className="w-3.5 h-3.5" /> Remove
                </button>
              )}
            </div>

            <div
              className="h-1 rounded-full overflow-hidden"
              style={{ background: "rgba(49,52,41,0.08)" }}
            >
              <div
                className="h-full rounded-full transition-[width] duration-300"
                style={{
                  width: `${Math.round(progress * 100)}%`,
                  background: "var(--fn-blue)",
                }}
              />
            </div>

            <div className="flex flex-col gap-vs-2 mt-vs-2">
              <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
                Processing pipeline
              </div>
              {stages.map((s) => (
                <div key={s.id} className="flex items-start gap-vs-3 text-body-sm">
                  <span className="w-4 h-4 shrink-0 mt-[2px] inline-flex items-center justify-center">
                    {s.status === "done" ? (
                      <CheckCircle2
                        className="w-3.5 h-3.5"
                        style={{ color: "var(--score-strong)" }}
                      />
                    ) : s.status === "warn" ? (
                      <CheckCircle2
                        className="w-3.5 h-3.5"
                        style={{ color: "var(--score-secondary)" }}
                      />
                    ) : s.status === "running" ? (
                      <Loader2
                        className="w-3.5 h-3.5 spin-slow"
                        style={{ color: "var(--fn-blue)" }}
                      />
                    ) : s.status === "failed" ? (
                      <X
                        className="w-3.5 h-3.5"
                        style={{ color: "var(--score-forbidden)" }}
                      />
                    ) : (
                      <Circle
                        className="w-3 h-3"
                        style={{ color: "var(--on-surface-variant)" }}
                      />
                    )}
                  </span>
                  <span className="flex-1">{s.label}</span>
                  <span className="font-mono text-[11px] text-on-surface-variant shrink-0">
                    {s.durationMs
                      ? `${(s.durationMs / 1000).toFixed(1)}s`
                      : s.status === "running"
                        ? "running"
                        : "pending"}
                  </span>
                  {s.warning && (
                    <span
                      className="text-[11px] font-medium"
                      style={{ color: "var(--score-secondary-on)" }}
                    >
                      ⚠ review
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* Supplementary form — shown for image sources (low metadata) */}
            {(source === "IMAGE" || done) && (
              <div className="border-hairline rounded-sm bg-surface-container-low p-vs-3 mt-vs-3 flex flex-col gap-vs-3">
                <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
                  Supplementary information (optional)
                </div>
                <div className="grid grid-cols-2 gap-vs-3">
                  <label className="flex flex-col gap-vs-1 text-body-sm">
                    Number of stories
                    <input
                      type="number"
                      value={supplement.stories}
                      onChange={(e) =>
                        setSupplement((s) => ({
                          ...s,
                          stories: parseInt(e.target.value || "1", 10) || 1,
                        }))
                      }
                      className="h-8 px-vs-2 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary font-mono"
                    />
                  </label>
                  <label className="flex flex-col gap-vs-1 text-body-sm">
                    Floor-to-floor (m)
                    <input
                      type="number"
                      step="0.1"
                      value={supplement.floorHeight}
                      onChange={(e) =>
                        setSupplement((s) => ({
                          ...s,
                          floorHeight: parseFloat(e.target.value || "3.9") || 3.9,
                        }))
                      }
                      className="h-8 px-vs-2 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary font-mono"
                    />
                  </label>
                  <label className="flex flex-col gap-vs-1 text-body-sm">
                    Occupancy
                    <select
                      value={supplement.occupancy}
                      onChange={(e) =>
                        setSupplement((s) => ({
                          ...s,
                          occupancy: e.target.value as OccupancyType,
                        }))
                      }
                      className="h-8 px-vs-2 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary"
                    >
                      {[
                        "office",
                        "residential",
                        "mixed_use",
                        "retail",
                        "industrial",
                        "educational",
                      ].map((o) => (
                        <option key={o} value={o}>
                          {o.replace("_", " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-vs-1 text-body-sm">
                    Location
                    <input
                      value={supplement.location}
                      onChange={(e) =>
                        setSupplement((s) => ({ ...s, location: e.target.value }))
                      }
                      placeholder="e.g. San Francisco, CA"
                      className="h-8 px-vs-2 bg-surface-container-lowest border-hairline rounded-sm outline-none focus:border-secondary"
                    />
                  </label>
                </div>
                <div className="text-body-sm text-on-surface-variant">
                  These help improve analysis if not found in the file.
                </div>
              </div>
            )}

            {done && (
              <button
                type="button"
                onClick={handleViewGraph}
                className="self-end h-10 px-vs-5 rounded-sm bg-on-surface text-on-primary font-headline text-title-sm font-medium hover:opacity-90 pressable inline-flex items-center gap-vs-2"
              >
                <Check className="w-3.5 h-3.5" strokeWidth={1.5} />
                View Building Graph
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
