import { useQuantityStore } from "@/state/quantityStore";

export function AreaSummaryTable() {
  const q = useQuantityStore((s) => s.quantities);
  return (
    <table>
      <thead>
        <tr>
          <th>Room</th>
          <th>Area m²</th>
          <th>%</th>
        </tr>
      </thead>
      <tbody>
        {(q?.areas ?? []).map((a) => (
          <tr key={a.roomId}>
            <td>{a.label}</td>
            <td>{a.areaM2.toFixed(2)}</td>
            <td>{a.pctTotal.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
