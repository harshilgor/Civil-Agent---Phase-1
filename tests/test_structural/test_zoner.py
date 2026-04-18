"""Tests for the StructuralZoner."""

from __future__ import annotations

from src.schema.structural_enums import StructuralZoneType
from src.structural.zoner import StructuralZoner


def test_zoner_detects_core(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    core_zones = [z for z in zones if z.type == StructuralZoneType.CORE_SERVICE]
    assert core_zones, "Expected at least one CORE_SERVICE zone"
    assert all(z.area_m2 > 0 for z in core_zones)


def test_zoner_classifies_open_plate(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    open_plates = [z for z in zones if z.type == StructuralZoneType.OPEN_FLOOR_PLATE]
    assert open_plates, "Expected open floor plate zone for large office"


def test_zoner_classifies_corridor(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    corridor = [z for z in zones if z.type == StructuralZoneType.CORRIDOR_BAND]
    assert corridor, "Expected corridor band zone"


def test_zoner_empty_graph(sample_building_graph):
    # Baseline graph has no cores; should still produce no crashes
    zones = StructuralZoner().classify(sample_building_graph)
    # Lobby is a LARGE_OPENING zone
    assert any(z.type == StructuralZoneType.LARGE_OPENING for z in zones)


def test_zoner_zones_have_unique_ids(office_tower_graph):
    zones = StructuralZoner().classify(office_tower_graph)
    ids = [z.id for z in zones]
    assert len(ids) == len(set(ids)), "Zone IDs must be unique"
