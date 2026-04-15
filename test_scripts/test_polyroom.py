#!/usr/bin/env python3
"""Phase-1 smoke test: PolyRoom model/weights loading."""

from __future__ import annotations

from common import parse_args, run_load_smoke


def main() -> int:
    args = parse_args("polyroom")
    return run_load_smoke("polyroom", weights_path=args.weights)


if __name__ == "__main__":
    raise SystemExit(main())
