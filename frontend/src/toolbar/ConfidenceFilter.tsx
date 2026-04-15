export function ConfidenceFilter() {
  return (
    <label>
      Confidence{" "}
      <select defaultValue="all">
        <option value="all">All</option>
        <option value="hide_low">Hide low</option>
        <option value="review">Needs review</option>
      </select>
    </label>
  );
}
