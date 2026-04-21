"use client";

import { useMemo } from "react";
import type { StructuredInput } from "@/types/domain";

export function PlanPreview({ input }: { input: StructuredInput }) {
  const { svg, elevation } = useMemo(() => buildPreview(input), [input]);

  return (
    <div className="flex flex-col gap-vs-3 h-full">
      <div className="border-hairline rounded-sm bg-surface-container-lowest p-vs-4 flex-1 flex items-center justify-center min-h-[280px]">
        {svg}
      </div>
      <div className="border-hairline rounded-sm bg-surface-container-lowest p-vs-3 flex items-center justify-between gap-vs-3">
        <div className="text-[10px] uppercase tracking-[0.12em] text-on-surface-variant">
          Elevation
        </div>
        <div className="flex-1 flex justify-center">{elevation}</div>
        <div className="font-mono text-[11px] text-on-surface-variant">
          {input.stories} × {input.typicalFloorHeightM.toFixed(1)}m ={" "}
          {(input.stories * input.typicalFloorHeightM).toFixed(1)}m
        </div>
      </div>
    </div>
  );
}

function buildPreview(input: StructuredInput) {
  const L = Math.max(10, input.lengthM);
  const W = Math.max(6, input.widthM);
  const view = 600;
  const vh = 380;
  const margin = 48;
  const maxW = view - margin * 2;
  const maxH = vh - margin * 2;
  const scale = Math.min(maxW / L, maxH / W);
  const drawL = L * scale;
  const drawW = W * scale;
  const x0 = (view - drawL) / 2;
  const y0 = (vh - drawW) / 2;

  const bayX = Math.max(3, input.preferredBayXM);
  const bayY = Math.max(3, input.preferredBayYM);
  const nx = Math.max(2, Math.round(L / bayX) + 1);
  const ny = Math.max(2, Math.round(W / bayY) + 1);

  // Grid
  const verticalLines: React.ReactElement[] = [];
  const horizontalLines: React.ReactElement[] = [];
  for (let i = 0; i < nx; i++) {
    const px = x0 + (i * drawL) / (nx - 1);
    verticalLines.push(
      <line
        key={`vx${i}`}
        x1={px}
        x2={px}
        y1={y0 - 16}
        y2={y0 + drawW + 16}
        stroke="rgba(49,52,41,0.25)"
        strokeDasharray="2 3"
        strokeWidth={0.5}
      />,
    );
    // label
    const label = String.fromCharCode(65 + i);
    verticalLines.push(
      <circle
        key={`vxc${i}`}
        cx={px}
        cy={y0 - 22}
        r={7}
        fill="var(--surface-container-lowest)"
        stroke="rgba(49,52,41,0.4)"
        strokeWidth={0.5}
      />,
    );
    verticalLines.push(
      <text
        key={`vxt${i}`}
        x={px}
        y={y0 - 22}
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="JetBrains Mono, monospace"
        fontSize={8}
        fill="var(--on-surface-variant)"
      >
        {label}
      </text>,
    );
  }
  for (let j = 0; j < ny; j++) {
    const py = y0 + (j * drawW) / (ny - 1);
    horizontalLines.push(
      <line
        key={`hy${j}`}
        y1={py}
        y2={py}
        x1={x0 - 16}
        x2={x0 + drawL + 16}
        stroke="rgba(49,52,41,0.25)"
        strokeDasharray="2 3"
        strokeWidth={0.5}
      />,
    );
    horizontalLines.push(
      <circle
        key={`hyc${j}`}
        cx={x0 - 22}
        cy={py}
        r={7}
        fill="var(--surface-container-lowest)"
        stroke="rgba(49,52,41,0.4)"
        strokeWidth={0.5}
      />,
    );
    horizontalLines.push(
      <text
        key={`hyt${j}`}
        x={x0 - 22}
        y={py}
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="JetBrains Mono, monospace"
        fontSize={8}
        fill="var(--on-surface-variant)"
      >
        {j + 1}
      </text>,
    );
  }

  // Columns at intersections
  const dots: React.ReactElement[] = [];
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < ny; j++) {
      const px = x0 + (i * drawL) / (nx - 1);
      const py = y0 + (j * drawW) / (ny - 1);
      dots.push(
        <circle
          key={`d${i}${j}`}
          cx={px}
          cy={py}
          r={2}
          fill="var(--on-surface)"
        />,
      );
    }
  }

  // Core
  let core: React.ReactElement | null = null;
  if (input.coreLocation !== "none") {
    const cwL = drawL * 0.25;
    const cwW = drawW * 0.3;
    let cx = x0 + drawL / 2 - cwL / 2;
    let cy = y0 + drawW / 2 - cwW / 2;
    switch (input.coreLocation) {
      case "edge_north":
        cy = y0 + drawW - cwW - 12;
        break;
      case "edge_south":
        cy = y0 + 12;
        break;
      case "edge_east":
        cx = x0 + drawL - cwL - 12;
        break;
      case "edge_west":
        cx = x0 + 12;
        break;
      case "corner":
        cx = x0 + 12;
        cy = y0 + 12;
        break;
    }
    core = (
      <g>
        <rect
          x={cx}
          y={cy}
          width={cwL}
          height={cwW}
          fill="var(--zone-core)"
          fillOpacity={0.18}
          stroke="var(--zone-core)"
          strokeWidth={0.75}
          strokeDasharray="3 2"
        />
        <text
          x={cx + cwL / 2}
          y={cy + cwW / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="JetBrains Mono, monospace"
          fontSize={9}
          fill="var(--zone-core)"
          letterSpacing={1}
        >
          CORE
        </text>
      </g>
    );
  }

  const svg = (
    <svg
      viewBox={`0 0 ${view} ${vh}`}
      className="w-full h-full max-h-[360px]"
      style={{ maxWidth: 600 }}
    >
      {horizontalLines}
      {verticalLines}
      {/* Outline */}
      <rect
        x={x0}
        y={y0}
        width={drawL}
        height={drawW}
        fill="var(--surface)"
        fillOpacity={0.5}
        stroke="var(--on-surface)"
        strokeWidth={1.5}
      />
      {core}
      {dots}
      {/* Dimensions */}
      <text
        x={x0 + drawL / 2}
        y={y0 + drawW + 36}
        textAnchor="middle"
        fontFamily="JetBrains Mono, monospace"
        fontSize={10}
        fill="var(--on-surface-variant)"
      >
        {L.toFixed(1)} m
      </text>
      <text
        x={x0 + drawL + 28}
        y={y0 + drawW / 2}
        textAnchor="middle"
        dominantBaseline="central"
        transform={`rotate(90 ${x0 + drawL + 28} ${y0 + drawW / 2})`}
        fontFamily="JetBrains Mono, monospace"
        fontSize={10}
        fill="var(--on-surface-variant)"
      >
        {W.toFixed(1)} m
      </text>
    </svg>
  );

  // Mini elevation
  const storyH = 12;
  const storyW = 80;
  const elev = (
    <svg
      width={storyW}
      height={Math.min(200, storyH * input.stories + 6)}
      viewBox={`0 0 ${storyW} ${storyH * input.stories + 6}`}
    >
      {Array.from({ length: input.stories }).map((_, i) => {
        const y = i * storyH + 3;
        return (
          <rect
            key={i}
            x={1}
            y={y}
            width={storyW - 2}
            height={storyH - 2}
            fill="var(--surface)"
            stroke="var(--on-surface)"
            strokeWidth={0.5}
          />
        );
      })}
      {/* ground */}
      <line
        x1={0}
        x2={storyW}
        y1={storyH * input.stories + 4}
        y2={storyH * input.stories + 4}
        stroke="var(--on-surface)"
        strokeWidth={1}
      />
    </svg>
  );

  return { svg, elevation: elev };
}
