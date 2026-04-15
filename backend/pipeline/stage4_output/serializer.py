"""JSON / GeoJSON / internal format export."""

from __future__ import annotations

import json
from typing import Any, Literal

Format = Literal["json", "geojson", "internal"]


def serialize(data: Any, fmt: Format = "json") -> str:
    if fmt == "internal":
        return repr(data)
    if fmt == "geojson":
        raise NotImplementedError("Emit GeoJSON FeatureCollection.")
    return json.dumps(data, default=str)
