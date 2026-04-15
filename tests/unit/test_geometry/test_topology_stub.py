from __future__ import annotations

import pytest

from backend.pipeline.stage3_geometry.topology import fix_topology


def test_topology_stub() -> None:
    with pytest.raises(NotImplementedError):
        fix_topology([])
