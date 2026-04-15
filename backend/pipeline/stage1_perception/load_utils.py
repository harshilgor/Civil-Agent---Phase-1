"""Helpers for phase-1 model loading (local vendor or external package)."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable


class ModelLoadError(RuntimeError):
    """Raised when a model cannot be loaded from any supported source."""


@dataclass
class ModuleResolution:
    """Resolved module import metadata."""

    source: str  # local | external
    module_name: str
    module: ModuleType


def repo_root() -> Path:
    """Return repository root from stage1_perception package location."""
    return Path(__file__).resolve().parents[3]


def has_materialized_files(path: Path) -> bool:
    """True when directory contains more than .gitkeep placeholders."""
    if not path.exists() or not path.is_dir():
        return False
    for item in path.rglob("*"):
        if item.is_file() and item.name != ".gitkeep":
            return True
    return False


def resolve_weights_path(raw_path: str | Path, require_file: bool = False) -> Path:
    """Resolve a relative/absolute weights path and validate existence."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = repo_root() / path
    if not path.exists():
        raise ModelLoadError(f"Weights path does not exist: {path}")
    if require_file and not path.is_file():
        raise ModelLoadError(f"Expected a weights file but found: {path}")
    if path.is_dir() and not has_materialized_files(path):
        raise ModelLoadError(
            f"Weights directory exists but is empty (only placeholders): {path}"
        )
    return path


def _try_import(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def resolve_module(
    *,
    vendor_path: str | Path,
    local_module_candidates: Iterable[str],
    external_module_candidates: Iterable[str],
) -> ModuleResolution:
    """
    Resolve model code source with local-vendor precedence.

    1) Try importing from local vendor directory if code exists.
    2) Fallback to external installed package(s).
    """
    root = repo_root()
    vendor = Path(vendor_path)
    if not vendor.is_absolute():
        vendor = root / vendor

    if has_materialized_files(vendor):
        vendor_entry = str(vendor)
        if vendor_entry not in sys.path:
            sys.path.insert(0, vendor_entry)
        for name in local_module_candidates:
            module = _try_import(name)
            if module is not None:
                return ModuleResolution(source="local", module_name=name, module=module)

    for name in external_module_candidates:
        module = _try_import(name)
        if module is not None:
            return ModuleResolution(source="external", module_name=name, module=module)

    local_names = ", ".join(local_module_candidates)
    external_names = ", ".join(external_module_candidates)
    raise ModelLoadError(
        "Could not import model code from local vendor or external package. "
        f"local=[{local_names}] external=[{external_names}] vendor_path={vendor}"
    )


def resolve_source_without_import(vendor_path: str | Path) -> str:
    """Return 'local' when vendor path contains real files, else raise."""
    vendor = Path(vendor_path)
    if not vendor.is_absolute():
        vendor = repo_root() / vendor
    if has_materialized_files(vendor):
        return "local"
    raise ModelLoadError(
        f"Local vendor source path does not contain model files: {vendor}"
    )


def require_dependency(module_name: str) -> ModuleType:
    """Import a runtime dependency and raise a clear install hint on failure."""
    module = _try_import(module_name)
    if module is None:
        raise ModelLoadError(
            f"Missing dependency '{module_name}'. Install required runtime dependencies first."
        )
    return module
