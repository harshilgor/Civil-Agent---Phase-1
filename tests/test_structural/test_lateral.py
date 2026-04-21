"""Tests for LateralSystemCandidateGenerator."""

from __future__ import annotations

from src.schema.structural_enums import LateralSystemType
from src.structural.lateral import LateralSystemCandidateGenerator
from src.structural.zoner import StructuralZoner


def test_lateral_generates_core_wall(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    out = LateralSystemCandidateGenerator().generate(office_tower_graph, zones)
    types = {c.system_type for c in out}
    assert LateralSystemType.CORE_WALL in types


def test_lateral_generates_shear_wall_when_present(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    out = LateralSystemCandidateGenerator().generate(office_tower_graph, zones)
    types = {c.system_type for c in out}
    assert LateralSystemType.SHEAR_WALL in types


def test_lateral_generates_dual_when_core_and_frame(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    out = LateralSystemCandidateGenerator().generate(office_tower_graph, zones)
    types = {c.system_type for c in out}
    # Moment frame always present + core wall present → dual system
    if LateralSystemType.CORE_WALL in types and LateralSystemType.MOMENT_FRAME in types:
        assert LateralSystemType.DUAL_SYSTEM in types


def test_lateral_sorted_by_plausibility(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    out = LateralSystemCandidateGenerator().generate(office_tower_graph, zones)
    plaus = [c.plausibility for c in out]
    assert plaus == sorted(plaus, reverse=True)
