"use client";

import { use, useState } from "react";
import { notFound, useRouter } from "next/navigation";
import { Copy, Download, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { useProjectsStore } from "@/stores/projectsStore";
import { formatRel } from "@/lib/format";

export default function SettingsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));
  const rename = useProjectsStore((s) => s.renameProject);
  const duplicate = useProjectsStore((s) => s.duplicateProject);
  const del = useProjectsStore((s) => s.deleteProject);
  const [name, setName] = useState(project?.name ?? "");
  const [confirming, setConfirming] = useState(false);

  if (!project) notFound();

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Settings"
        projectName={project.name}
        subtitle="Project metadata & preferences"
      />
      <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
        <div className="max-w-[640px] px-vs-6 py-vs-6 flex flex-col gap-vs-6">
          <section className="flex flex-col gap-vs-3">
            <SectionTitle>Project</SectionTitle>
            <Field label="Name">
              <div className="flex items-center gap-vs-2">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="flex-1 h-8 px-vs-2 border-hairline rounded-sm bg-surface text-body-md outline-none focus:border-secondary"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (name.trim()) {
                      rename(project.id, name.trim());
                      toast.success("Project renamed.");
                    }
                  }}
                  className="h-8 px-vs-3 rounded-sm bg-on-surface text-on-primary text-body-sm font-medium pressable"
                >
                  Save
                </button>
              </div>
            </Field>
            <Field label="Project ID">
              <span className="font-mono text-[11px] text-on-surface-variant">
                {project.id}
              </span>
            </Field>
            <Field label="Source">
              <span className="font-mono text-[11px] text-on-surface-variant">
                {project.source}
              </span>
            </Field>
            <Field label="Created">
              <span className="text-body-sm text-on-surface-variant">
                {formatRel(project.createdAt)}
              </span>
            </Field>
            <Field label="Updated">
              <span className="text-body-sm text-on-surface-variant">
                {formatRel(project.updatedAt)}
              </span>
            </Field>
          </section>

          <section className="flex flex-col gap-vs-3">
            <SectionTitle>Defaults</SectionTitle>
            <Field label="Building code">
              <span>{project.input.buildingCode.replace("_", " ")}</span>
            </Field>
            <Field label="Location">
              <span>{project.input.locationText}</span>
            </Field>
            <Field label="Seismic zone">
              <span>Zone {project.input.seismicZone}</span>
            </Field>
            <Field label="Units">
              <span>Metric (mm, m)</span>
            </Field>
            <button
              type="button"
              onClick={() => router.push(`/projects/${project.id}/input`)}
              className="self-start h-8 px-vs-3 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
            >
              Edit inputs →
            </button>
          </section>

          <section className="flex flex-col gap-vs-3">
            <SectionTitle>Data</SectionTitle>
            <div className="flex flex-wrap gap-vs-2">
              <button
                type="button"
                onClick={() => {
                  const newId = duplicate(project.id);
                  if (newId) {
                    toast.success("Project duplicated.");
                    router.push(`/projects/${newId}/building-graph`);
                  }
                }}
                className="inline-flex items-center gap-vs-1 h-8 px-vs-3 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
              >
                <Copy className="w-3 h-3" strokeWidth={1.5} />
                Duplicate project
              </button>
              <button
                type="button"
                onClick={() => router.push(`/projects/${project.id}/summary`)}
                className="inline-flex items-center gap-vs-1 h-8 px-vs-3 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
              >
                <Download className="w-3 h-3" strokeWidth={1.5} />
                Export handoff
              </button>
            </div>
          </section>

          <section className="flex flex-col gap-vs-3">
            <SectionTitle>Danger zone</SectionTitle>
            {confirming ? (
              <div className="p-vs-3 border-hairline rounded-sm bg-surface-container-low flex items-center gap-vs-2">
                <span className="flex-1 text-body-sm">Delete project permanently?</span>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  className="h-7 px-vs-3 rounded-sm border-hairline text-body-sm"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    del(project.id);
                    toast.success("Project deleted.");
                    router.push("/");
                  }}
                  className="h-7 px-vs-3 rounded-sm text-body-sm font-medium text-on-primary"
                  style={{ background: "var(--score-forbidden)" }}
                >
                  Delete
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="self-start inline-flex items-center gap-vs-1 h-8 px-vs-3 rounded-sm border-hairline hover:bg-surface-container-low text-body-sm"
                style={{ color: "var(--score-forbidden)" }}
              >
                <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                Delete project
              </button>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-title-sm pb-vs-2 border-b-hairline">{children}</h2>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-vs-4 py-vs-1">
      <span className="w-[140px] shrink-0 text-body-sm text-on-surface-variant">
        {label}
      </span>
      <div className="flex-1 text-body-md">{children}</div>
    </div>
  );
}
