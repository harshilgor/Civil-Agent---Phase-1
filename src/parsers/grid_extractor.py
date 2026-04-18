"""Extract structural grid from raw DXF parser output.

Associates nearby text labels with grid lines.
"""

from __future__ import annotations

import structlog

from src.schema.building_graph import GridLine

logger = structlog.get_logger(__name__)

_LABEL_PROXIMITY_MM = 2000  # max distance to associate a text label with a grid line


class GridExtractor:
    """Clean and label raw grid-line data from DXF parsing."""

    def extract(
        self,
        raw_grid: dict[str, list[dict]],
        text_annotations: list[dict],
    ) -> dict[str, list[GridLine]]:
        """Return ``{x_lines: [...], y_lines: [...]}`` of ``GridLine`` objects.

        Labels are assigned from nearby text annotations when possible,
        falling back to alphabetic (X) / numeric (Y) defaults.
        """
        x_lines = self._label_lines(
            raw_grid.get("x_lines", []),
            text_annotations,
            axis="x",
        )
        y_lines = self._label_lines(
            raw_grid.get("y_lines", []),
            text_annotations,
            axis="y",
        )
        logger.info("grid_extracted", x=len(x_lines), y=len(y_lines))
        return {"x_lines": x_lines, "y_lines": y_lines}

    def _label_lines(
        self,
        lines: list[dict],
        texts: list[dict],
        axis: str,
    ) -> list[GridLine]:
        result: list[GridLine] = []
        for idx, line in enumerate(lines):
            pos = line["position_mm"]
            label = self._find_label(line, texts)
            if label is None:
                if axis == "x":
                    label = chr(ord("A") + idx) if idx < 26 else f"X{idx + 1}"
                else:
                    label = str(idx + 1)
            result.append(GridLine(id=label, position_mm=pos))
        return result

    @staticmethod
    def _find_label(line: dict, texts: list[dict]) -> str | None:
        """Find the closest single-character or short text near the grid line."""
        start = line.get("start", [0, 0])
        end = line.get("end", [0, 0])
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2

        best_label = None
        best_dist = _LABEL_PROXIMITY_MM

        for t in texts:
            text = t.get("text", "").strip()
            if not text or len(text) > 3:
                continue
            tx, ty = t["position"]
            dist = ((tx - mid_x) ** 2 + (ty - mid_y) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_label = text

        return best_label
