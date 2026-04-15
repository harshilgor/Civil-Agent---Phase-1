#!/usr/bin/env bash
# Clone vendored repos and place local code/weights for phase-1 loading tests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDORS="${ROOT}/vendors"
SRC="${ROOT}/_vendor_sources"
mkdir -p "${SRC}"

echo "Vendor root: ${VENDORS}"
echo "Source cache: ${SRC}"

clone_if_missing() {
  local repo_url="$1"
  local dst="$2"
  if [[ -d "${dst}/.git" ]]; then
    echo "Already cloned: ${dst}"
    return 0
  fi
  git clone --depth 1 "${repo_url}" "${dst}"
}

clone_if_missing "https://github.com/CubiCasa/CubiCasa5k" "${SRC}/cubicasa5k"
clone_if_missing "https://github.com/zcemycl/TF2DeepFloorplan" "${SRC}/tf2deepfloorplan"
clone_if_missing "https://github.com/SizheHu/Raster-to-Graph" "${SRC}/raster-to-graph"
clone_if_missing "https://github.com/ywyue/RoomFormer" "${SRC}/roomformer"
clone_if_missing "https://github.com/3dv-casia/PolyRoom" "${SRC}/polyroom"

mkdir -p "${VENDORS}/cubicasa/floortrans" "${VENDORS}/tf2_deepfloorplan/dfp"
mkdir -p "${VENDORS}/raster_to_graph/models" "${VENDORS}/roomformer/models" "${VENDORS}/polyroom/models"

cp -R "${SRC}/cubicasa5k/floortrans/." "${VENDORS}/cubicasa/floortrans/"
cp -R "${SRC}/tf2deepfloorplan/src/dfp/." "${VENDORS}/tf2_deepfloorplan/dfp/"
cp -R "${SRC}/raster-to-graph/models/." "${VENDORS}/raster_to_graph/models/"
cp -R "${SRC}/roomformer/models/." "${VENDORS}/roomformer/models/"
cp -R "${SRC}/polyroom/models/." "${VENDORS}/polyroom/models/"

echo "Install gdown if not available and fetch weights:"
echo "  gdown 'https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK' -O '${VENDORS}/cubicasa/weights/model_best_val_loss_var.pkl'"
echo "  gdown 'https://drive.google.com/uc?id=1czUSFvk6Z49H-zRikTc67g2HUUz4imON' -O '${VENDORS}/tf2_deepfloorplan/weights/log.zip'"
echo "  unzip/expand '${VENDORS}/tf2_deepfloorplan/weights/log.zip' into '${VENDORS}/tf2_deepfloorplan/weights/'"
