"use client";

import { use } from "react";
import { notFound } from "next/navigation";
import { ViewHeader } from "@/components/layout/ViewHeader";
import { useProjectsStore } from "@/stores/projectsStore";
import { formatRel } from "@/lib/format";

export default function MetadataPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const project = useProjectsStore((s) => s.getProject(id));
  if (!project) notFound();
  const g = project.buildingGraph;
  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ViewHeader
        title="Metadata"
        projectName={project.name}
        subtitle="Project and pipeline metadata"
      />
      <div className="flex-1 min-h-0 overflow-y-auto bg-surface">
        <div className="max-w-[720px] px-vs-6 py-vs-6 flex flex-col gap-vs-6">
          <Section title="Identifiers">
            <Row k="Project ID" v={project.id} mono />
            <Row k="Status" v={project.status} />
            <Row k="Source" v={project.source} />
            <Row k="Pipeline stage" v={project.pipelineStage.replace(/_/g, " ")} />
            <Row k="Created" v={`${formatRel(project.createdAt)} (${new Date(project.createdAt).toLocaleString()})`} />
            <Row k="Updated" v={`${formatRel(project.updatedAt)} (${new Date(project.updatedAt).toLocaleString()})`} />
          </Section>
          <Section title="Phases">
            {([1, 2, 3, 4, 5] as const).map((p) => (
              <Row key={p} k={`Phase ${p}`} v={project.phaseStatus[p].replace(/_/g, " ")} />
            ))}
          </Section>
          {g && (
            <Section title="Graph statistics">
              <Row k="Completeness" v={`${Math.round(g.completeness * 100)}%`} />
              <Row k="Confidence" v={`${Math.round(g.confidence * 100)}%`} />
              <Row k="Walls" v={`${g.walls.length}`} />
              <Row k="Rooms" v={`${g.rooms.length}`} />
              <Row k="Openings" v={`${g.openings.length}`} />
              <Row k="Cores" v={`${g.cores.length}`} />
              <Row k="Column candidates" v={`${g.columnCandidates.length}`} />
              <Row k="Processing time" v={`${g.processingMs} ms`} />
              <Row k="Missing fields" v={g.missingFields.length ? g.missingFields.join(", ") : "None"} />
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-title-sm pb-vs-2 mb-vs-2 border-b-hairline">{title}</h2>
      <dl className="flex flex-col gap-vs-1">{children}</dl>
    </section>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-vs-4 py-vs-1">
      <dt className="w-[160px] shrink-0 text-body-sm text-on-surface-variant">{k}</dt>
      <dd className={mono ? "font-mono text-[11px]" : "text-body-md"}>{v}</dd>
    </div>
  );
}
