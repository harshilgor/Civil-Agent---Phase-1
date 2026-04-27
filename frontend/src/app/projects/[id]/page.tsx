"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useProjectsStore } from "@/stores/projectsStore";

export default function ProjectIndexPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProjectsStore((s) => s.getProject(id));
  useEffect(() => {
    router.replace(
      project?.projectType === "wood_framing_sizer"
        ? `/projects/${id}/sizer/overview`
        : `/projects/${id}/building-graph`,
    );
  }, [id, project?.projectType, router]);
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-body-sm text-on-surface-variant">Opening project…</div>
    </div>
  );
}
