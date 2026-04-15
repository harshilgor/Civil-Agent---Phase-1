"""Serialize pipeline results to GeoJSON, JSON, CSV."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

ExportFormat = Literal["json", "geojson", "csv"]


class ExportService:
    def export(self, result: dict[str, Any], fmt: ExportFormat) -> tuple[str, str]:
        """Returns (content_type, body)."""
        if fmt == "json":
            return "application/json", json.dumps(result, default=str)
        if fmt == "geojson":
            raise NotImplementedError("Build FeatureCollection from rooms/boundaries.")
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["room_id", "label", "area_m2"])
        writer.writerow(["stub", "unknown", "0"])
        return "text/csv", buf.getvalue()
