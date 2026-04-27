"use client";

import { use } from "react";
import { SizerProjectScreen } from "@/components/sizer/SizerProjectScreen";

export default function SizerSettingsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <SizerProjectScreen projectId={id} view="settings" />;
}
