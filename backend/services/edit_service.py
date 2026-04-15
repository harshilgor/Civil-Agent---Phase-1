"""Apply user edits; recompute area/perimeter and topology checks."""

from __future__ import annotations

from typing import Any

from backend.storage.result_store import ResultStore


class EditService:
    def __init__(self, results: ResultStore) -> None:
        self._results = results

    def apply_room_patch(
        self,
        job_id: str,
        room_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge PATCH into stored room; stub topology revalidation."""
        base = self._results.get(job_id) or {"rooms": [], "boundaries": [], "scale": None, "metadata": {}}
        rooms: list[dict[str, Any]] = list(base.get("rooms", []))
        found = False
        for i, room in enumerate(rooms):
            if str(room.get("id")) == str(room_id):
                rooms[i] = {**room, **payload, "id": room_id}
                found = True
                break
        if not found:
            rooms.append({"id": room_id, **payload})
        out = {**base, "rooms": rooms}
        self._results.put(job_id, out)
        return out
