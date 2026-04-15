import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { getResults } from "@/api/client";
import { FloorplanCanvas } from "@/canvas/FloorplanCanvas";
import { useQuantities } from "@/hooks/useQuantities";
import { InspectorPanel } from "@/panels/InspectorPanel/InspectorPanel";
import { DiagnosticsPanel } from "@/panels/DiagnosticsPanel/DiagnosticsPanel";
import { LayerPanel } from "@/panels/LayerPanel/LayerPanel";
import { QuantityPanel } from "@/panels/QuantityPanel/QuantityPanel";
import { ScalePanel } from "@/panels/ScalePanel/ScalePanel";
import { Toolbar } from "@/toolbar/Toolbar";
import { BOTTOM_BAR_HEIGHT, SIDEBAR_WIDTH } from "./layout";
import { useJobStore } from "@/state/jobStore";

export function ViewerPage() {
  const { jobId } = useParams();
  const results = useJobStore((s) => s.results);
  const setResults = useJobStore((s) => s.setResults);

  useQuantities(results);

  useEffect(() => {
    if (!jobId) return;
    void (async () => {
      try {
        setResults(await getResults(jobId));
      } catch {
        /* ignore */
      }
    })();
  }, [jobId, setResults]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <Toolbar jobId={jobId} />
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <aside style={{ width: SIDEBAR_WIDTH, borderRight: "1px solid #30363d", overflow: "auto" }}>
          <LayerPanel />
          <ScalePanel jobId={jobId} />
          <DiagnosticsPanel />
          <InspectorPanel />
        </aside>
        <main style={{ flex: 1, position: "relative" }}>
          <FloorplanCanvas />
        </main>
      </div>
      <footer style={{ height: BOTTOM_BAR_HEIGHT, borderTop: "1px solid #30363d" }}>
        <QuantityPanel />
      </footer>
      <p style={{ padding: 8 }}>
        <Link to="/">Home</Link>
      </p>
    </div>
  );
}
