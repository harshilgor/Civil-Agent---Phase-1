import { AreaSummaryTable } from "./AreaSummaryTable";
import { WallLengthSummary } from "./WallLengthSummary";
import { ZoneBreakdown } from "./ZoneBreakdown";

export function QuantityPanel() {
  return (
    <div style={{ display: "flex", gap: 16, padding: 8, alignItems: "flex-start" }}>
      <AreaSummaryTable />
      <ZoneBreakdown />
      <WallLengthSummary />
    </div>
  );
}
