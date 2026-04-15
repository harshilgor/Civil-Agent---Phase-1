import { DecisionLogView } from "./DecisionLogView";

export function DiagnosticsPanel() {
  return (
    <div style={{ padding: 12 }}>
      <h3>Diagnostics</h3>
      <DecisionLogView />
    </div>
  );
}
