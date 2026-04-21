"use client";

import { Canvas } from "@react-three/fiber";
import { Grid, OrbitControls, PerspectiveCamera, Text } from "@react-three/drei";
import { useEffect, useMemo, useState } from "react";
import type { BuildingGraph, StructuralGraph, StructuralZone, SupportClass } from "@/types/domain";
import { useCanvasStore, type OverlayMode } from "@/stores/canvasStore";
import { useSelectionStore } from "@/stores/selectionStore";

type Props = {
  graph: BuildingGraph;
  structural?: StructuralGraph | null;
  overlayMode?: OverlayMode;
  supportFilter?: Record<SupportClass, boolean>;
  onCursor?: (pt: { x: number; y: number; z: number } | null) => void;
};

const MM_TO_M = 0.001;

export function ModelCanvas3D({
  graph,
  structural,
  overlayMode = "none",
  supportFilter,
  onCursor,
}: Props) {
  const L = graph.lengthMm * MM_TO_M;
  const W = graph.widthMm * MM_TO_M;
  const H = graph.storyHeightMm * MM_TO_M;
  const stories = graph.stories;
  const totalH = H * stories;

  const layers = useCanvasStore((s) => s.layers);
  const floor = useCanvasStore((s) => s.floor);
  const [sliceY, setSliceY] = useState(totalH + 0.5);

  useEffect(() => {
    setSliceY(totalH + 0.5);
  }, [totalH]);

  return (
    <div className="relative w-full h-full">
      <Canvas
        shadows
        dpr={[1, 2]}
        gl={{ antialias: true, preserveDrawingBuffer: false }}
        onPointerLeave={() => onCursor?.(null)}
      >
        <color attach="background" args={["#fbf9f2"]} />
        <PerspectiveCamera
          makeDefault
          position={[L * 1.2, totalH * 1.2 + 6, W * 1.5]}
          fov={42}
        />
        <ambientLight intensity={0.55} />
        <directionalLight
          position={[L / 2 + 30, 60, W / 2 + 30]}
          intensity={0.8}
          castShadow
          shadow-mapSize={[1024, 1024]}
        />
        {layers.grid && (
          <Grid
            position={[L / 2, 0, W / 2]}
            args={[L * 2, W * 2]}
            cellSize={1}
            cellThickness={0.4}
            cellColor="#b4b2a9"
            sectionSize={Math.max(4, L / Math.max(1, graph.grid.xAxes.length - 1))}
            sectionThickness={0.8}
            sectionColor="#888780"
            fadeDistance={80}
            fadeStrength={1}
            followCamera={false}
            infiniteGrid
          />
        )}

        {/* Slabs + walls per story */}
        {Array.from({ length: stories }).map((_, i) => {
          const floorNum = i + 1;
          const showThisFloor = floor === "all" || floor === floorNum;
          const yBase = i * H;
          if (yBase > sliceY) return null;
          return (
            <group
              key={i}
              position={[0, yBase, 0]}
              visible={showThisFloor}
            >
              {/* Slab */}
              <mesh
                position={[L / 2, 0.05, W / 2]}
                receiveShadow
              >
                <boxGeometry args={[L, 0.1, W]} />
                <meshStandardMaterial
                  color={floor === floorNum ? "#efeee3" : "#f5f4eb"}
                  transparent
                  opacity={
                    floor === "all" || floor === floorNum ? 0.95 : 0.18
                  }
                />
              </mesh>
              {/* Walls */}
              {layers.walls && (
                <WallsLayer3D
                  graph={graph}
                  storyHeight={H}
                  dim={floor !== "all" && floor !== floorNum}
                />
              )}
              {/* Cores */}
              {layers.cores && (
                <CoresLayer3D
                  graph={graph}
                  storyHeight={H}
                  dim={floor !== "all" && floor !== floorNum}
                />
              )}
              {/* Columns */}
              {layers.columns && (
                <ColumnsLayer3D
                  graph={graph}
                  floor={floorNum}
                  overlayMode={overlayMode}
                  supportFilter={supportFilter}
                  storyHeight={H}
                  dim={floor !== "all" && floor !== floorNum}
                />
              )}
              {/* Zones overlay */}
              {overlayMode === "zones" && structural && (
                <ZonesLayer3D
                  zones={structural.zones.filter((z) => z.floor === floorNum)}
                  yOffset={0.12}
                />
              )}
              {/* Floor label */}
              {floor === "all" && (
                <Text
                  position={[-1.5, 0.5, W / 2]}
                  rotation={[0, Math.PI / 2, 0]}
                  fontSize={0.35}
                  color="#5e6054"
                >
                  Floor {floorNum}
                </Text>
              )}
            </group>
          );
        })}

        {/* Top roof plane */}
        <mesh position={[L / 2, totalH, W / 2]}>
          <boxGeometry args={[L, 0.08, W]} />
          <meshStandardMaterial color="#e3e4d4" transparent opacity={0.5} />
        </mesh>

        {overlayMode === "load_paths" && (
          <LoadPathsLayer3D graph={graph} storyHeight={H} stories={stories} />
        )}

        <OrbitControls
          target={[L / 2, totalH / 2, W / 2]}
          enableDamping
          dampingFactor={0.1}
          minDistance={3}
          maxDistance={200}
        />
      </Canvas>
      {/* Floor slice slider (left edge) */}
      <div className="absolute left-vs-3 top-1/2 -translate-y-1/2 z-20 w-10 h-[50%] flex flex-col items-center gap-vs-2">
        <div className="text-[10px] font-mono text-on-surface-variant">
          {sliceY.toFixed(1)}m
        </div>
        <input
          type="range"
          min={0}
          max={totalH + 1}
          step={0.1}
          value={sliceY}
          onChange={(e) => setSliceY(parseFloat(e.target.value))}
          aria-label="Floor slice"
          className="h-full"
          style={{
            writingMode: "vertical-lr" as const,
            direction: "rtl",
            width: 20,
          }}
        />
        <div className="text-[10px] font-mono text-on-surface-variant">Slice</div>
      </div>
    </div>
  );
}

function WallsLayer3D({
  graph,
  storyHeight,
  dim,
}: {
  graph: BuildingGraph;
  storyHeight: number;
  dim: boolean;
}) {
  const select = useSelectionStore((s) => s.select);
  const sel = useSelectionStore((s) => s.selection);
  return (
    <group>
      {graph.walls.map((w) => {
        const s: [number, number] = [w.start[0] * MM_TO_M, w.start[1] * MM_TO_M];
        const e: [number, number] = [w.end[0] * MM_TO_M, w.end[1] * MM_TO_M];
        const dx = e[0] - s[0];
        const dy = e[1] - s[1];
        const length = Math.hypot(dx, dy);
        if (length < 0.05) return null;
        const cx = (s[0] + e[0]) / 2;
        const cy = (s[1] + e[1]) / 2;
        const angle = Math.atan2(dy, dx);
        const thickness = Math.max(0.12, w.thicknessMm * MM_TO_M);
        const height = storyHeight * 0.95;
        const color =
          w.type === "structural"
            ? "#888780"
            : w.type === "shear"
              ? "#444441"
              : "#d3d1c7";
        const selected = sel.kind === "wall" && sel.id === w.id;
        return (
          <mesh
            key={w.id}
            position={[cx, height / 2 + 0.05, cy]}
            rotation={[0, -angle, 0]}
            onClick={(ev) => {
              ev.stopPropagation();
              select("wall", w.id);
            }}
            castShadow
          >
            <boxGeometry args={[length, height, thickness]} />
            <meshStandardMaterial
              color={selected ? "#006a6a" : color}
              transparent
              opacity={dim ? 0.15 : 0.96}
            />
          </mesh>
        );
      })}
    </group>
  );
}

function CoresLayer3D({
  graph,
  storyHeight,
  dim,
}: {
  graph: BuildingGraph;
  storyHeight: number;
  dim: boolean;
}) {
  return (
    <group>
      {graph.cores.map((c) => {
        const minX = Math.min(...c.polygon.map((p) => p[0])) * MM_TO_M;
        const maxX = Math.max(...c.polygon.map((p) => p[0])) * MM_TO_M;
        const minY = Math.min(...c.polygon.map((p) => p[1])) * MM_TO_M;
        const maxY = Math.max(...c.polygon.map((p) => p[1])) * MM_TO_M;
        const w = maxX - minX;
        const d = maxY - minY;
        return (
          <mesh
            key={c.id}
            position={[minX + w / 2, storyHeight / 2 + 0.05, minY + d / 2]}
          >
            <boxGeometry args={[w, storyHeight * 0.98, d]} />
            <meshStandardMaterial
              color="#006a6a"
              transparent
              opacity={dim ? 0.08 : 0.2}
            />
          </mesh>
        );
      })}
    </group>
  );
}

function ColumnsLayer3D({
  graph,
  floor,
  overlayMode,
  supportFilter,
  storyHeight,
  dim,
}: {
  graph: BuildingGraph;
  floor: number;
  overlayMode: OverlayMode;
  supportFilter?: Record<SupportClass, boolean>;
  storyHeight: number;
  dim: boolean;
}) {
  const select = useSelectionStore((s) => s.select);
  const sel = useSelectionStore((s) => s.selection);
  const showScore = overlayMode === "supports";
  const cols = useMemo(
    () => graph.columnCandidates.filter((c) => c.floor === floor),
    [graph.columnCandidates, floor],
  );
  return (
    <group>
      {cols.map((c) => {
        if (supportFilter && !supportFilter[c.classification]) return null;
        const hex = showScore ? SCORE_HEX[c.classification] : "#5e6054";
        const selected = sel.kind === "column" && sel.id === c.id;
        const size = 0.38;
        return (
          <mesh
            key={c.id}
            position={[c.position[0] * MM_TO_M, storyHeight / 2 + 0.05, c.position[1] * MM_TO_M]}
            onClick={(ev) => {
              ev.stopPropagation();
              select("column", c.id);
            }}
            castShadow
          >
            <boxGeometry args={[size, storyHeight * 0.9, size]} />
            <meshStandardMaterial
              color={selected ? "#006a6a" : hex}
              transparent
              opacity={
                dim
                  ? 0.12
                  : c.classification === "forbidden"
                    ? 0.3
                    : c.classification === "weak"
                      ? 0.55
                      : 0.9
              }
            />
          </mesh>
        );
      })}
    </group>
  );
}

const SCORE_HEX: Record<SupportClass, string> = {
  strong: "#4a7c59",
  secondary: "#b8842b",
  weak: "#c2615b",
  forbidden: "#9f403d",
};

function ZonesLayer3D({
  zones,
  yOffset,
}: {
  zones: StructuralZone[];
  yOffset: number;
}) {
  return (
    <group>
      {zones.map((z) => {
        const minX = Math.min(...z.polygon.map((p) => p[0])) * MM_TO_M;
        const maxX = Math.max(...z.polygon.map((p) => p[0])) * MM_TO_M;
        const minY = Math.min(...z.polygon.map((p) => p[1])) * MM_TO_M;
        const maxY = Math.max(...z.polygon.map((p) => p[1])) * MM_TO_M;
        const w = maxX - minX;
        const d = maxY - minY;
        const hex = ZONE_HEX[z.type];
        return (
          <group key={z.id}>
            <mesh position={[minX + w / 2, yOffset, minY + d / 2]}>
              <boxGeometry args={[w, 0.02, d]} />
              <meshBasicMaterial color={hex} transparent opacity={0.22} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

const ZONE_HEX: Record<StructuralZone["type"], string> = {
  core: "#006a6a",
  open_plate: "#6a4c93",
  corridor: "#b5548c",
  perimeter: "#3c6e91",
  transfer_risk: "#c2615b",
  high_clearance: "#b8842b",
  double_height: "#9f403d",
};

function LoadPathsLayer3D({
  graph,
  storyHeight,
  stories,
}: {
  graph: BuildingGraph;
  storyHeight: number;
  stories: number;
}) {
  // Vertical gravity arrows through columns; color gradient green → red
  return (
    <group>
      {graph.columnCandidates
        .filter((c) => c.floor === 1 && c.classification !== "forbidden")
        .map((c) => {
          const x = c.position[0] * MM_TO_M;
          const z = c.position[1] * MM_TO_M;
          const totalH = storyHeight * stories;
          return (
            <group key={`lp-${c.id}`}>
              {Array.from({ length: stories }).map((_, i) => {
                const yTop = storyHeight * (stories - i);
                const ratio = (i + 1) / stories;
                const hex = ratio < 0.4 ? "#97C459" : ratio < 0.7 ? "#EF9F27" : "#D85A30";
                return (
                  <mesh
                    key={i}
                    position={[x, yTop - storyHeight / 2, z]}
                  >
                    <cylinderGeometry args={[0.08 + ratio * 0.12, 0.08 + (ratio - 0.1) * 0.12, storyHeight, 12]} />
                    <meshBasicMaterial color={hex} transparent opacity={0.6} />
                  </mesh>
                );
              })}
            </group>
          );
        })}
    </group>
  );
}
