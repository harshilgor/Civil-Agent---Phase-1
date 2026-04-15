Here's the plan. No production strategy, no reimplementation, no licensing tangents. Just: clone repo, load model the way the docs say, run inference, get output.

---

## Step-by-Step: Get Every Model Running

### Step 1: Gather sample floor plan images

Before touching any model, you need test inputs.

- Go to Google Images, search "architectural floor plan PNG" or "residential floor plan image"
- Download 3 images: one simple (3–4 rooms, clean lines), one medium (6–8 rooms), one messy (scanned/hand-drawn)
- Save them to `test_scripts/samples/` as `simple.png`, `medium.png`, `messy.png`
- Also: for RoomFormer/PolyRoom testing later, you'll need their own test data (density maps, not floor plans) — we'll grab those when we get to those models

Create the folder structure now:
```
test_scripts/
├── samples/
│   ├── simple.png
│   ├── medium.png
│   └── messy.png
├── outputs/         # each test script saves results here
│   ├── cubicasa/
│   ├── deepfloorplan/
│   ├── roomformer/
│   ├── raster_to_graph/
│   └── polyroom/
```

---

### Step 2: CubiCasa

**2a. Clone the repo and get the weights**

- Go to: `https://github.com/CubiCasa/CubiCasa5k`
- Clone it somewhere outside your project (e.g., `/tmp/cubicasa` or a `_vendor_sources/` folder)
- From the README, the weights download link is in the repo — they say "Our model weights file can be downloaded here" — that "here" links to a Google Drive file. The ID from the community usage is `1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK`. Download it:
  ```
  pip install gdown
  gdown 'https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK'
  ```
- You should get `model_best_val_loss_var.pkl`. Move it into `vendors/cubicasa/weights/`
- Copy the `floortrans/` folder from the cloned repo into `vendors/cubicasa/floortrans/`

**2b. Check what dependencies CubiCasa needs**

From their `requirements.txt` and `samples.ipynb`:
- PyTorch (they used 1.0, but modern PyTorch should work — try your current version first)
- OpenCV
- numpy
- scipy
- scikit-image
- lmdb (only for training data loading — you may not need this for inference)

Install whatever you're missing.

**2c. Write `test_scripts/test_cubicasa.py`**

The inference pattern comes directly from their `samples.ipynb`. Here's what the notebook does:

```python
# Their notebook does exactly this:
from floortrans.models import get_model
from floortrans.loaders import FloorplanSVG, DictToTensor, Compose, RotateNTurns
from floortrans.plotting import segmentation_plot, polygons_to_image, draw_junction_from_dict, discrete_cmap
from floortrans.post_prosessing import split_prediction, get_polygons, split_validation

# Build model
model = get_model('hg_furukawa_original', 51)
n_classes = 44
split = [21, 12, 11]
model.conv4_ = torch.nn.Conv2d(256, n_classes, bias=True, kernel_size=1)
model.upsample = torch.nn.ConvTranspose2d(n_classes, n_classes, kernel_size=4, stride=4)

# Load weights
checkpoint = torch.load('model_best_val_loss_var.pkl')
model.load_state_dict(checkpoint['model_state'])
model.eval()
model.cuda()  # or model.cpu() if no GPU

# Load image — they use their own FloorplanSVG loader for the dataset,
# but for a raw image you'll need to:
#   1. Load with PIL/OpenCV
#   2. Resize
#   3. Convert to tensor
#   4. Apply RotateNTurns for 4-rotation TTA

# Run inference
rot = RotateNTurns()
# ... (see their notebook cell for the exact rotation + averaging logic)

# Split the 44-channel output into room/icon/heatmap
rooms, icons, heatmaps = split_prediction(result, split)
```

Your test script should:
1. Add `vendors/cubicasa/` to `sys.path` so the imports work
2. Load the model exactly as above
3. Load a sample PNG, resize it, tensorize it
4. Run inference (try CPU first: `model.cpu()`)
5. Save the room segmentation as a colored PNG to `test_scripts/outputs/cubicasa/rooms.png`
6. Save the wall/boundary output as a binary PNG to `test_scripts/outputs/cubicasa/walls.png`
7. Print: number of detected room classes, image dimensions, success/fail

**2d. Run it, fix errors**

The most likely issues:
- Import errors from old PyTorch API calls in `floortrans/` — fix them inline in the vendored code
- `model.cuda()` failing if no GPU — switch to `model.cpu()` and `torch.load(..., map_location='cpu')`
- The image loading path — their loader expects their dataset format, but you're feeding a raw PNG. You'll need to manually replicate what their `FloorplanSVG` loader does to a raw image: load, resize, normalize, convert to tensor

**Success = you run the script and get two saved PNG files that look like a room segmentation and a wall map.**

---

### Step 3: DeepFloorplan (TF2 port)

**3a. Clone the repo and get the weights**

- Go to: `https://github.com/zcemycl/TF2DeepFloorplan`
- Clone it
- Weights: check their `deepfloorplan.ipynb` — it does:
  ```
  gdown https://drive.google.com/uc?id=1czUSFvk6Z49H-zRikTc67g2HUUz4imON
  unzip log.zip
  ```
  This gives you a `log/` folder with TF checkpoints. Move it into `vendors/tf2_deepfloorplan/weights/`
- Copy the `src/dfp/` folder into `vendors/tf2_deepfloorplan/dfp/`

**3b. Set up a separate TF environment**

This model runs on TensorFlow 2, not PyTorch. Do NOT try to run it in the same environment.

```bash
conda create -n civilagent-tf python=3.8
conda activate civilagent-tf
pip install tensorflow  # or tensorflow-gpu if you have a GPU
pip install opencv-python-headless numpy matplotlib
# Then install the dfp package:
cd vendors/tf2_deepfloorplan
pip install -e .  # if their setup.py/pyproject.toml works
# OR just make sure dfp/ is importable
```

**3c. Write `test_scripts/test_deepfloorplan.py`**

The inference pattern comes from their README and `deploy.py`:

```bash
# Their documented way to run inference:
python -m dfp.deploy \
  --image path/to/image.jpg \
  --weight log/store/G \
  --postprocess \
  --colorize \
  --save output.jpg \
  --loadmethod log
```

Your test script should either:
- Call this as a subprocess (simplest, most reliable), OR
- Import from `dfp` directly and replicate what `deploy.py` does internally

The subprocess approach for the test script:
```python
import subprocess
result = subprocess.run([
    "python", "-m", "dfp.deploy",
    "--image", "test_scripts/samples/simple.png",
    "--weight", "vendors/tf2_deepfloorplan/weights/log/store/G",
    "--postprocess", "--colorize",
    "--save", "test_scripts/outputs/deepfloorplan/result.jpg",
    "--loadmethod", "log",
], capture_output=True, text=True)
```

For more control (getting the raw room logits and boundary logits separately), look inside `dfp/deploy.py` — it loads the model, runs inference, and the raw output is a two-headed tensor: rooms + boundaries. The `--colorize` flag just visualizes it.

Your test script should save:
1. The colorized room output to `test_scripts/outputs/deepfloorplan/rooms.png`
2. The boundary output to `test_scripts/outputs/deepfloorplan/boundaries.png`
3. Print success/fail

**3d. Run it in the TF environment, fix errors**

Most likely issues:
- TF version conflicts (their setup was TF 2.x with Python 3.8 — check if newer TF works)
- The gdown weight link might be broken — if so, check their GitHub Issues for alternative links
- Backbone mismatch — default is VGG16, make sure you're using `--backbone vgg16` consistently

**Success = you run the script (in the TF conda env) and get two saved images.**

---

### Step 4: Raster-to-Graph

**4a. Clone the repo and get the weights**

- Go to: `https://github.com/SizheHu/Raster-to-Graph`
- Clone it
- Their README says the weights and data require filling out a Google Form to get access (they have a "LIFULL HOME'S Data" access process). The model weights should be included in or downloadable from the repo after setup. Check their `demo.py` for what weight file path it expects.
- Copy the relevant model code into `vendors/raster_to_graph/`

**4b. Dependencies**

From their README: Python 3.7, CUDA 11.1. Check their `requirements.txt`. Key packages: PyTorch, torchvision, PIL (pillow 8.0.0 for their data processing, 9.1.1 for inference).

**4c. Write `test_scripts/test_raster_to_graph.py`**

Their documented inference approach from the README:

```
# Their demo.py expects:
# 1. An image folder as input
# 2. You modify demo.py to point MyDataset_demo to your folder
# 3. Run: python demo.py
# 4. Output goes to output/your_path_name/
```

Your test script should:
1. Create a temp folder with your sample image(s)
2. Either call their `demo.py` as subprocess, or import their model + dataset classes directly and run inference
3. The output is a structural graph: wall junctions (x,y coordinates) + wall segments (pairs of junctions) + room type labels
4. Save the visualized output to `test_scripts/outputs/raster_to_graph/result.png`
5. Print the junction list and edge list

**4d. Run it, fix errors**

Likely issues:
- Their code was developed on Windows 10 — path separators, file handling might break on Linux/Mac
- The pretrained weights path might be hardcoded — look in their code for where it loads the checkpoint
- Their input images were preprocessed in a specific way (centered, 512×512) — your raw floor plan might need the same preprocessing. Check their `image_process.py` for the exact steps.

**Success = you get a visualization showing detected junctions and wall edges overlaid on the floor plan.**

---

### Step 5: RoomFormer

**5a. Clone the repo and get the weights**

- Go to: `https://github.com/ywyue/RoomFormer`
- Clone it
- Their README links to pretrained checkpoints for Structured3D and SceneCAD. Download the `.pth` files and put them in `vendors/roomformer/checkpoints/`
- Also download their processed Structured3D test data (they link to it) — you need this because RoomFormer takes density maps, not floor plan images

**5b. Dependencies**

From their README:
```bash
pip install torch==1.9.0+cu111 torchvision==0.10.0+cu111 -f https://download.pytorch.org/whl/torch_stable.html
pip install -r requirements.txt
```
Try with your current PyTorch first. If it breaks, pin to their versions.

**5c. Write `test_scripts/test_roomformer.py`**

Their documented evaluation approach:
```bash
# Their eval script:
./tools/eval_stru3d.sh
# Which internally runs eval.py with their checkpoint + test data
```

Your test script should:
1. Load the model using their model-building code + `torch.load('checkpoints/roomformer_stru3d.pth')`
2. **First test:** Load one of their own test density maps (from the downloaded Structured3D test set). Run inference. Verify it produces polygon outputs that make sense. This proves the model loads and works.
3. **Second test:** Take the wall/boundary output from your CubiCasa test (Step 2), convert it to a grayscale 256×256 image (binarize, blur slightly, resize). Feed THIS as input to RoomFormer. See what happens. Save the result.
4. Save predicted polygons drawn on the input to `test_scripts/outputs/roomformer/result.png`

**5d. Run it, fix errors**

Likely issues:
- Their code has custom CUDA ops or specific deformable attention modules that need compilation — check their install instructions
- Checkpoint loading might fail if PyTorch version is very different from 1.9
- The density map format needs to match exactly what they expect (single channel, specific normalization)

**Success = polygons drawn on a density map that correspond to room outlines.**

---

### Step 6: PolyRoom

**6a. Clone the repo and get the weights**

- Go to: `https://github.com/3dv-casia/PolyRoom`
- Clone it
- Their README says: "The checkpoints of the Mask2former and PolyRoom can be downloaded in this link" — follow that link, download both checkpoints
- PolyRoom depends on MMDetection (for Mask2Former). You need to install MMDetection from source and place their config files in the right spots. Their README and Issue #2 have details.

**6b. This is the most complex setup**

PolyRoom is a two-model chain:
1. Mask2Former runs first (instance segmentation on density map → room masks)
2. PolyRoom runs second (takes room masks as query initialization → refines to polygons)

You need:
- MMDetection installed from source
- Their custom config file placed in `mmdetection/configs/str3d/`
- Their custom dataset file placed in `mmdetection/mmdet/datasets/`
- Both checkpoints downloaded

**6c. Write `test_scripts/test_polyroom.py`**

Follow their `engine.py` which chains Mask2Former → PolyRoom. Your test script mirrors that flow:
1. Load Mask2Former with their checkpoint
2. Load PolyRoom with their checkpoint
3. Feed a density map from the Structured3D test set (same data as RoomFormer)
4. Run Mask2Former → get instance masks
5. Run PolyRoom with those masks → get refined polygons
6. Save result to `test_scripts/outputs/polyroom/result.png`

**6d. Do this one LAST**

PolyRoom has the highest setup complexity of all the models (MMDetection dependency, two-model chain, custom config files). Do it after all other models work. If it's too painful, skip it for now — RoomFormer serves the same role (A3 polygon proposals) and is simpler to set up.

---

### Step 7: FloorplanTransformation — SKIP

Don't do this one. The codebase is Torch7/Lua, the PyTorch port is untested by the authors, and Raster-to-Graph (Step 4) fills the same role (B3 — vectorized wall edges). Only come back to this if Raster-to-Graph completely fails on your data.

---

### Step 8: Create `vendors/LICENSE_AUDIT.md`

Once all models are cloned, create a single file documenting what you've got:

```
vendors/LICENSE_AUDIT.md
```

Contents: the table I gave you earlier — repo URL, license, commercial status, commit hash you cloned from, date cloned. This is just a record so you don't lose track.

---

### Step 9: Verify all 4 (or 5) test scripts run clean

At this point you should have:

```
test_scripts/
├── samples/
│   ├── simple.png
│   ├── medium.png
│   └── messy.png
├── outputs/
│   ├── cubicasa/
│   │   ├── rooms.png          ← colored room segmentation
│   │   └── walls.png          ← binary wall mask
│   ├── deepfloorplan/
│   │   ├── rooms.png          ← colored room segmentation
│   │   └── boundaries.png     ← boundary map
│   ├── raster_to_graph/
│   │   └── result.png         ← junctions + edges overlay
│   ├── roomformer/
│   │   ├── density_test.png   ← polygons on their own test density map
│   │   └── synth_test.png     ← polygons on your CubiCasa-derived density map
│   └── polyroom/              ← (if you got to it)
│       └── result.png
├── test_cubicasa.py
├── test_deepfloorplan.py
├── test_raster_to_graph.py
├── test_roomformer.py
└── test_polyroom.py           ← (if you got to it)
```

Each script should be runnable standalone:
```bash
python test_scripts/test_cubicasa.py --image test_scripts/samples/simple.png
python test_scripts/test_deepfloorplan.py --image test_scripts/samples/simple.png  # (in TF env)
python test_scripts/test_raster_to_graph.py --image test_scripts/samples/simple.png
python test_scripts/test_roomformer.py  # (uses their test density maps)
```

Each prints PASS or FAIL and saves output images.

---

### Execution Order Summary

Do them in this exact sequence. Don't jump ahead.

1. **Create `test_scripts/samples/` and `test_scripts/outputs/` directories.** Download 3 sample floor plan PNGs.
2. **CubiCasa** — clone, get weights, write test script, get it passing.
3. **DeepFloorplan** — clone, get weights, set up TF env, write test script, get it passing.
4. **Raster-to-Graph** — clone, get weights, write test script, get it passing.
5. **RoomFormer** — clone, get weights + their test data, write test script, get it passing.
6. **PolyRoom** — only if time allows, highest setup friction.
7. **Skip FloorplanTransformation** entirely.
8. **Create `vendors/LICENSE_AUDIT.md`** documenting everything.
9. **Verify all scripts run clean**, outputs look correct.

That's it. Once all test scripts pass, the next phase is backporting the loading + inference code into the adapter stubs in `backend/pipeline/stage1_perception/adapters/`. But that's a separate step — don't touch the adapters until every test script works independently.