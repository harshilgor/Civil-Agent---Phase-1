#!/usr/bin/env bash
# Clone vendored repos, download weights, verify checksums (implement per vendor).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDORS="${ROOT}/vendors"
echo "Vendor root: ${VENDORS}"
echo "TODO: clone cubicasa, tf2_deepfloorplan, roomformer, polyroom, raster_to_graph, floorplan_transformation"
echo "TODO: download weights to vendors/*/weights or checkpoints per config/models.yaml"
