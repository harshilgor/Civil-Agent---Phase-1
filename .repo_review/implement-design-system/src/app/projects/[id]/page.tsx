"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ProjectIndexPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/projects/${id}/building-graph`);
  }, [id, router]);
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-body-sm text-on-surface-variant">Opening project…</div>
    </div>
  );
}
