"""Uploaded originals + generated overlay tiles."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import BinaryIO
from uuid import uuid4


class ImageStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path.cwd() / "data" / "uploads"
        self._lock = Lock()
        self._paths: dict[str, Path] = {}

    def save(self, job_id: str, stream: BinaryIO, suffix: str = ".bin") -> Path:
        self._base.mkdir(parents=True, exist_ok=True)
        name = f"{job_id}_{uuid4().hex}{suffix}"
        path = self._base / name
        path.write_bytes(stream.read())
        with self._lock:
            self._paths[job_id] = path
        return path

    def path_for(self, job_id: str) -> Path | None:
        with self._lock:
            return self._paths.get(job_id)
