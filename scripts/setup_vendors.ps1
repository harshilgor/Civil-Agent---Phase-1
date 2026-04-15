$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$vendors = Join-Path $root "vendors"
$sources = Join-Path $root "_vendor_sources"

New-Item -ItemType Directory -Force -Path $sources | Out-Null

function Invoke-CloneIfMissing {
    param(
        [Parameter(Mandatory = $true)][string]$RepoUrl,
        [Parameter(Mandatory = $true)][string]$Target
    )
    if (Test-Path (Join-Path $Target ".git")) {
        Write-Host "Already cloned: $Target"
        return
    }
    git clone --depth 1 $RepoUrl $Target
}

Invoke-CloneIfMissing "https://github.com/CubiCasa/CubiCasa5k" (Join-Path $sources "cubicasa5k")
Invoke-CloneIfMissing "https://github.com/zcemycl/TF2DeepFloorplan" (Join-Path $sources "tf2deepfloorplan")
Invoke-CloneIfMissing "https://github.com/SizheHu/Raster-to-Graph" (Join-Path $sources "raster-to-graph")
Invoke-CloneIfMissing "https://github.com/ywyue/RoomFormer" (Join-Path $sources "roomformer")
Invoke-CloneIfMissing "https://github.com/3dv-casia/PolyRoom" (Join-Path $sources "polyroom")

Copy-Item -Recurse -Force (Join-Path $sources "cubicasa5k/floortrans/*") (Join-Path $vendors "cubicasa/floortrans/")
Copy-Item -Recurse -Force (Join-Path $sources "tf2deepfloorplan/src/dfp/*") (Join-Path $vendors "tf2_deepfloorplan/dfp/")
Copy-Item -Recurse -Force (Join-Path $sources "raster-to-graph/models/*") (Join-Path $vendors "raster_to_graph/models/")
Copy-Item -Recurse -Force (Join-Path $sources "roomformer/models/*") (Join-Path $vendors "roomformer/models/")
Copy-Item -Recurse -Force (Join-Path $sources "polyroom/models/*") (Join-Path $vendors "polyroom/models/")

Write-Host "Vendor source code copied."
Write-Host "Run these manually for weights:"
Write-Host "gdown 'https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK' -O 'vendors/cubicasa/weights/model_best_val_loss_var.pkl'"
Write-Host "gdown 'https://drive.google.com/uc?id=1czUSFvk6Z49H-zRikTc67g2HUUz4imON' -O 'vendors/tf2_deepfloorplan/weights/log.zip'"
Write-Host "Expand-Archive -Force 'vendors/tf2_deepfloorplan/weights/log.zip' 'vendors/tf2_deepfloorplan/weights'"
