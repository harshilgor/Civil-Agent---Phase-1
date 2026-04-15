from __future__ import annotations

from backend.pipeline.stage2_fusion.trust import trust_weights


def test_trust_weights_reads_yaml_shape() -> None:
    cfg = {
        "models": {
            "a": {"trust_weight": 1.0},
            "b": {"trust_weight": 0.5},
        }
    }
    w = trust_weights(cfg)
    assert w["a"] == 1.0
    assert w["b"] == 0.5
