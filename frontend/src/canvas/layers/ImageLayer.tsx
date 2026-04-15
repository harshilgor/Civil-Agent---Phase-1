import { useJobStore } from "@/state/jobStore";

export function ImageLayer() {
  const metadata = useJobStore((s) => s.results?.metadata ?? {});
  const rawImageUrl = typeof metadata.image_url === "string" ? metadata.image_url : null;
  const imageUrl =
    rawImageUrl && rawImageUrl.startsWith("/")
      ? `${import.meta.env.VITE_API_URL ?? ""}${rawImageUrl}`
      : rawImageUrl;
  if (!imageUrl) {
    return (
      <div style={{ position: "absolute", inset: 0, opacity: 0.6, padding: 12 }}>
        Image unavailable
      </div>
    );
  }
  return (
    <img
      src={imageUrl}
      alt="floor plan"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        objectFit: "contain",
        opacity: 0.75,
      }}
    />
  );
}
