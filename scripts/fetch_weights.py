#!/usr/bin/env python
"""Fetch / verify model weights declared in ``config/weights_manifest.yaml``.

Usage
-----

    # Fetch every enabled model via the default backend (WEIGHTS_BACKEND env):
    python scripts/fetch_weights.py

    # Fetch a single slot:
    python scripts/fetch_weights.py --model wall_segmenter_residential

    # Verify presence+checksums without downloading (exit 1 on any missing):
    python scripts/fetch_weights.py --verify-only

    # Force a specific backend independent of the env var:
    python scripts/fetch_weights.py --backend s3

Behaviour
---------

* The script **never** imports ``boto3`` unless ``--backend s3`` (or
  ``WEIGHTS_BACKEND=s3`` in the env) resolves.  Local-only CI remains free
  of AWS dependencies.

* Disabled manifest entries are skipped with an ``[SKIP]`` line and do not
  affect the exit code.  Missing/failing enabled entries are reported with
  ``[FAIL]`` and cause the script to exit 1.

* Output is a fixed-width status table suitable for CI log scraping.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

# Make the repository root importable when the script is invoked directly.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.weights import (  # noqa: E402
    ResolvedWeights,
    WeightsBackend,
    WeightsBackendError,
    WeightsLoader,
    WeightsManifest,
    get_backend,
)
from backend.weights.manifest import WeightsEntry  # noqa: E402


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


_OK = "[ OK ]"
_FAIL = "[FAIL]"
_SKIP = "[SKIP]"
_GONE = "[MISS]"


def _row(status: str, name: str, detail: str) -> str:
    return f"{status}  {name:<32}  {detail}"


def _describe_entry(entry: WeightsEntry) -> str:
    return f"{entry.architecture.value:<12} {entry.model_id}@{entry.model_version}"


# ---------------------------------------------------------------------------
# Core verb: process one slot
# ---------------------------------------------------------------------------


def _process_slot(
    name: str,
    entry: WeightsEntry,
    backend: WeightsBackend,
    *,
    verify_only: bool,
) -> tuple[str, str]:
    """Return (status, detail) for one manifest slot."""

    if not entry.enabled:
        return _SKIP, f"disabled     ({_describe_entry(entry)})"

    try:
        if verify_only:
            if not backend.available(entry):
                return _GONE, f"missing      ({_describe_entry(entry)})"
            # available() does not check sha256 on its own; force a verify
            # pass through fetch().
            resolved_path = backend.fetch(entry)
            return _OK, f"verified     {resolved_path}"
        t0 = time.perf_counter()
        path = backend.fetch(entry)
        dt = time.perf_counter() - t0
        return _OK, f"ready in {dt:5.1f}s  {path}"
    except WeightsBackendError as exc:
        return _FAIL, f"{exc}"
    except Exception as exc:  # noqa: BLE001  (belt-and-braces CLI surface)
        return _FAIL, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# CLI main
# ---------------------------------------------------------------------------


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch_weights",
        description="Fetch or verify perception-model weights from the manifest.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=None,
        metavar="NAME",
        help="Process only this slot (repeatable). Default: all enabled slots.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also process disabled slots (otherwise they are skipped).",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not download; verify existence and checksums only.",
    )
    parser.add_argument(
        "--backend",
        choices=["local", "s3"],
        default=None,
        help="Override the configured WEIGHTS_BACKEND.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=(
            "Path to the manifest YAML (default: settings.weights_manifest_path, "
            "i.e. config/weights_manifest.yaml)."
        ),
    )
    parser.add_argument(
        "--weights-dir",
        type=Path,
        default=None,
        help="Override settings.weights_dir (local backend cache / S3 cache).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Resolve manifest + backend -------------------------------------------

    from src.config import settings  # noqa: PLC0415

    manifest_path = args.manifest or settings.weights_manifest_path
    try:
        manifest = WeightsManifest.load(manifest_path)
    except Exception as exc:  # noqa: BLE001
        print(f"fetch_weights: could not load manifest {manifest_path}: {exc}",
              file=sys.stderr)
        return 2

    try:
        backend = get_backend(args.backend, weights_dir=args.weights_dir)
    except WeightsBackendError as exc:
        print(f"fetch_weights: backend error: {exc}", file=sys.stderr)
        return 2

    loader = WeightsLoader(manifest=manifest, backend=backend)

    # Pick slots ----------------------------------------------------------

    if args.model:
        names = list(args.model)
        missing = [n for n in names if not loader.is_known(n)]
        if missing:
            print(
                f"fetch_weights: unknown slot(s): {', '.join(missing)}. "
                f"Known: {', '.join(sorted(manifest.models))}",
                file=sys.stderr,
            )
            return 2
    elif args.all:
        names = list(manifest.models)
    else:
        names = list(manifest.enabled_models())

    # Header --------------------------------------------------------------

    print(f"Manifest:   {manifest_path}")
    print(f"Backend:    {backend.name}   (manifest hash {loader.manifest_hash[:12]}…)")
    print(f"Mode:       {'verify' if args.verify_only else 'fetch'}")
    print("-" * 88)

    # Process --------------------------------------------------------------

    exit_code = 0
    for name in names:
        entry = manifest.models[name]
        status, detail = _process_slot(
            name, entry, backend, verify_only=args.verify_only
        )
        print(_row(status, name, detail))
        if status in (_FAIL, _GONE):
            exit_code = 1

    print("-" * 88)
    return exit_code


# ---------------------------------------------------------------------------
# Convenience wrapper reused by unit tests
# ---------------------------------------------------------------------------


def verify_resolved(loader: WeightsLoader) -> list[ResolvedWeights]:
    """Resolve every enabled manifest entry or raise. Used by Phase 1 tests."""

    return [loader.resolve(name) for name in loader.manifest.enabled_models()]


if __name__ == "__main__":
    raise SystemExit(main())
