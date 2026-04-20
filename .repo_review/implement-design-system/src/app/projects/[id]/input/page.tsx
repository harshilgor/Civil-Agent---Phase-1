"use client";

import { use, useState } from "react";
import { StructuredInputForm } from "@/components/forms/StructuredInputForm";
import { FileUploadZone } from "@/components/forms/FileUploadZone";

type Tab = "structured" | "upload";

export default function EditInputPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [tab, setTab] = useState<Tab>("structured");
  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="border-b-hairline bg-surface px-vs-6 pt-vs-3">
        <div className="mx-auto max-w-[1440px] flex items-center gap-vs-2">
          {(
            [
              ["structured", "Structured form"],
              ["upload", "Replace with file"],
            ] as Array<[Tab, string]>
          ).map(([k, l]) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={[
                "h-9 px-vs-3 rounded-t-sm text-body-md font-medium tonal-hover",
                tab === k
                  ? "bg-surface-container-lowest border-hairline border-b-0 -mb-[0.5px]"
                  : "text-on-surface-variant hover:bg-surface-container-low",
              ].join(" ")}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      {tab === "structured" ? (
        <StructuredInputForm projectId={id} />
      ) : (
        <FileUploadZone />
      )}
    </div>
  );
}
