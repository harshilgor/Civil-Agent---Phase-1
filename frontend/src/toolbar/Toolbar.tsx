import { ModeSwitcher } from "./ModeSwitcher";
import { UndoRedo } from "./UndoRedo";
import { ExportButton } from "./ExportButton";
import { ConfidenceFilter } from "./ConfidenceFilter";

export function Toolbar({ jobId }: { jobId?: string }) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "8px 12px",
        borderBottom: "1px solid #30363d",
      }}
    >
      <strong>Civil Agent</strong>
      <ModeSwitcher />
      <UndoRedo />
      <ExportButton jobId={jobId} />
      <ConfidenceFilter />
    </header>
  );
}
