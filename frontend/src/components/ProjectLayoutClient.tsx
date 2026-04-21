"use client";

import { use, useEffect, useMemo, useSyncExternalStore } from "react";
import { notFound, useRouter } from "next/navigation";
import { useProjectsStore } from "@/stores/projectsStore";

export function ProjectLayoutClient({
  children,
  params,
}: {
  children: React.ReactNode;
  params?: { id: string };
}) {
  const router = useRouter();

  // Hydration-safe snapshot to avoid SSR/notFound flicker before zustand persist rehydrates
  const hydrated = useSyncExternalStore(
    (l) => useProjectsStore.subscribe(l),
    () => useProjectsStore.getState()._hydrated,
    () => false,
  );
  const getProject = useProjectsStore((s) => s.getProject);
  const id = params?.id;
  const exists = useMemo(() => (id ? !!getProject(id) : false), [id, getProject, hydrated]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (hydrated && id && !exists) {
      // route to a dedicated 404 in this segment
    }
  }, [hydrated, id, exists]);

  if (!hydrated && id) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-body-sm text-on-surface-variant">Loading project…</div>
      </div>
    );
  }
  if (hydrated && id && !exists) notFound();

  return <>{children}</>;
}

// Client wrapper that receives Next.js 15-style async params
export function ProjectLayoutAsync({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const resolved = use(params);
  return <ProjectLayoutClient params={resolved}>{children}</ProjectLayoutClient>;
}
