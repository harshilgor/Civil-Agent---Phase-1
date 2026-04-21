"""
floorplan_ocr.py — Architectural Floor Plan OCR using PaddleOCR v5 (PP-OCRv5)
==============================================================================

Extracts and classifies all text from an architectural floor plan image using
PaddleOCR's latest PP-OCRv5 server models, outputting a structured JSON file
with bounding boxes, confidence scores, rotation angles, and semantic labels
for every detected text element.

Dependencies:
    pip install paddlepaddle==3.0.0
    pip install paddleocr

Example usage:
    # Basic usage — auto-names output JSON next to the input image
    python floorplan_ocr.py --image ./floorplan.png

    # Full options
    python floorplan_ocr.py --image ./floorplan.png \\
                            --output ./results.json \\
                            --confidence-threshold 0.6 \\
                            --save-visualization
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Supported image extensions
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


# ---------------------------------------------------------------------------
# Text classification patterns
# ---------------------------------------------------------------------------

# Feet/inches: 13'-7", 14'-0", 8'-5", 24'-0"  OR  simple foot marks: 10'
_FEET_INCHES_RE = re.compile(
    r"""
    (?:
        \d+[^\w\s]?\s*'\s*-?\s*\d+[^\w\s]?\s*"   # e.g. 13'-7"  or 14' - 0" or 8^'-0"
        | \d+[^\w\s]?\s*'\s*-?\s*\d*[^\w\s]?"?    # e.g. 14'-0"  or just 10' or 8^'-0"
        | \d+[^\w\s]?'\d+[^\w\s]?"                # e.g. 5'10"
    )
    """,
    re.VERBOSE,
)

# Metric with multiplication: 4.76 x 3.79  |  3.97 × 3.61  |  2.4x3.0
_METRIC_DIM_RE = re.compile(
    r"""\d+(?:\.\d+)?\s*[xX×]\s*\d+(?:\.\d+)?""",
    re.VERBOSE,
)

# Standalone number with optional unit (m, ft, mm, cm)
_UNIT_NUMBER_RE = re.compile(
    r"""\b\d+(?:\.\d+)?\s*(?:m|ft|mm|cm|'|")\b""",
    re.IGNORECASE,
)

ROOM_KEYWORDS = [
    "bedroom", "bed", "kitchen", "bath", "bathroom", "dining", "living",
    "family", "foyer", "study", "utility", "utlity", "closet", "garage", "porch",
    "pool", "hall", "mud", "reception", "master", "primary", "suite",
    "laundry", "pantry", "office", "den", "loft", "nook", "breakfast",
]

# Ceiling height markers
_CEILING_RE = re.compile(
    r"\b(?:clg|ceiling|flat\s+clg|cathedral)\b",
    re.IGNORECASE,
)

FIXTURE_KEYWORDS = [
    "fridge", "dw", "cooktop", "w/m", "dryer", "wm", "sink",
    "tub", "shower", "toilet", "oven", "range", "washer",
]

def levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def classify_text(text: str) -> str:
    """Return one of: dimension | room_label | ceiling_height | fixture_label | annotation."""
    t_lower = text.lower()
    
    # Ceiling height override rule
    has_meas = bool(_FEET_INCHES_RE.search(text) or _UNIT_NUMBER_RE.search(text))
    if (has_meas and "flat" in t_lower) or _CEILING_RE.search(text):
        return "ceiling_height"
        
    if _FEET_INCHES_RE.search(text) or _METRIC_DIM_RE.search(text) or _UNIT_NUMBER_RE.search(text):
        return "dimension"
        
    # Fixture keyword substring matching
    for kw in FIXTURE_KEYWORDS:
        if kw in t_lower:
            return "fixture_label"

    # Fuzzy room matching
    words = t_lower.replace('-', ' ').replace('/', ' ').split()
    for word in words:
        for kw in ROOM_KEYWORDS:
            if kw in word and len(kw) >= 3:
                return "room_label"
            if levenshtein(word, kw) <= 2:
                return "room_label"
                
    return "annotation"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def compute_center(points: list) -> list:
    """Return [cx, cy] as the mean of 4 polygon vertices."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [int(round(sum(xs) / len(xs))), int(round(sum(ys) / len(ys)))]


def compute_rotation(points: list) -> float:
    """
    Estimate the rotation angle (degrees) of a text bounding box.

    Uses the vector from point[0] (top-left) to point[1] (top-right) and
    computes its angle relative to the positive x-axis.
    """
    if len(points) < 2:
        return 0.0
    dx = points[1][0] - points[0][0]
    dy = points[1][1] - points[0][1]
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    return round(angle_deg, 4)

def get_aabb(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)

def compute_iou(box1, box2):
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2
    
    inter_xmin = max(x1_min, x2_min)
    inter_ymin = max(y1_min, y2_min)
    inter_xmax = min(x1_max, x2_max)
    inter_ymax = min(y1_max, y2_max)
    
    if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
        return 0.0
        
    inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
    area1 = (x1_max - x1_min) * (y1_max - y1_min)
    area2 = (x2_max - x2_min) * (y2_max - y2_min)
    
    union_area = area1 + area2 - inter_area
    if union_area <= 0: return 0.0
    return inter_area / union_area

# ---------------------------------------------------------------------------
# Image dimensions (PIL-free fallback using struct for PNG/BMP/JPEG)
# ---------------------------------------------------------------------------

def get_image_dimensions(image_path: str) -> dict:
    """
    Return {"width": w, "height": h} without requiring Pillow.

    Falls back to a best-effort read using struct for common formats.
    If Pillow is available it will be preferred.
    """
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            w, h = img.size
            return {"width": w, "height": h}
    except ImportError:
        pass

    # Minimal header parsing for PNG / JPEG / BMP
    path = image_path.lower()
    try:
        import struct
        with open(image_path, "rb") as f:
            header = f.read(26)
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", header[16:24])
            return {"width": w, "height": h}
        if header[:2] == b"\xff\xd8":  # JPEG
            import struct as _s
            with open(image_path, "rb") as f:
                f.read(2)
                while True:
                    marker, size = _s.unpack(">HH", f.read(4))
                    if marker in (0xFFC0, 0xFFC2):
                        f.read(1)
                        h, w = _s.unpack(">HH", f.read(4))
                        return {"width": w, "height": h}
                    f.read(size - 2)
        if header[:2] == b"BM":
            w, h = struct.unpack("<II", header[18:26])
            return {"width": w, "height": h}
    except Exception:
        pass

    return {"width": 0, "height": 0}


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def save_visualization(image_path: str, detections: list, viz_path: str) -> None:
    """
    Draw bounding boxes and text labels on the image and save it.
    Tries OpenCV first, then falls back to Pillow.
    """
    # --- OpenCV path ---
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"cv2.imread returned None for {image_path}")

        for det in detections:
            pts = np.array(det["bounding_box"]["points"], dtype=np.int32)
            # Color by classification
            colors = {
                "dimension":      (0, 200, 255),   # amber
                "room_label":     (50, 200, 50),    # green
                "ceiling_height": (255, 100, 0),    # blue-ish
                "fixture_label":  (200, 50, 200),   # purple
                "annotation":     (180, 180, 180),  # grey
                "noise":          (50, 50, 50),     # dark grey
            }
            color = colors.get(det["classification"], (255, 255, 255))
            cv2.polylines(img, [pts.reshape((-1, 1, 2))], isClosed=True, color=color, thickness=2)
            cx, cy = det["bounding_box"]["center"]
            label = f"{det['text'][:20]} ({det['confidence']:.2f})"
            font_scale = 0.4 if det["classification"] != "noise" else 0.3
            thickness = 1
            cv2.putText(img, label, (cx - 5, cy - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)

        cv2.imwrite(viz_path, img)
        return
    except ImportError:
        pass

    # --- Pillow fallback ---
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        colors = {
            "dimension":      "#FFC800",
            "room_label":     "#32C832",
            "ceiling_height": "#FF6400",
            "fixture_label":  "#C832C8",
            "annotation":     "#B4B4B4",
            "noise":          "#323232",
        }
        for det in detections:
            pts = [tuple(p) for p in det["bounding_box"]["points"]]
            color = colors.get(det["classification"], "#FFFFFF")
            draw.polygon(pts, outline=color)
            cx, cy = det["bounding_box"]["center"]
            draw.text((cx, cy), det["text"][:20], fill=color)

        img.save(viz_path)
        return
    except ImportError:
        pass

    print(
        "WARNING: Neither OpenCV nor Pillow is installed. "
        "Visualization could not be saved.",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Core OCR runner
# ---------------------------------------------------------------------------

def run_ocr(
    image_path: str,
    confidence_threshold: float,
    save_viz: bool,
    output_path: str,
) -> dict:
    """
    Run PaddleOCR PP-OCRv5 on *image_path* and return the result dict.
    Also writes the JSON file and optionally the visualization image.
    """
    print(f"[INFO] Loading PP-OCRv5 server model...", file=sys.stderr)

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        # Use the highest-accuracy server-grade models
        text_detection_model_name="PP-OCRv5_server_det",
        text_recognition_model_name="PP-OCRv5_server_rec",
        # Critical for rotated dimension text on floor plans
        use_textline_orientation=True,
        # Disable document-oriented pre-processing (hurts clean images)
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        # Preserve detail in high-resolution floor plans
        text_det_limit_type="min",
        text_det_limit_side_len=1280,
    )

    print(f"[INFO] Running inference on normal image: {image_path}", file=sys.stderr)
    try:
        result_normal = ocr.predict(input=image_path)
    except Exception as exc:
        print(f"[ERROR] PaddleOCR predict() normal failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Running inference on 90-degree rotated copy", file=sys.stderr)
    try:
        import tempfile
        import cv2
        img = cv2.imread(image_path)
        if img is not None:
            H, W = img.shape[:2]
            img_rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            fd, temp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            cv2.imwrite(temp_path, img_rot)
            
            result_rot = ocr.predict(input=temp_path)
            os.remove(temp_path)
        else:
            result_rot = []
            H, W = 0, 0
    except Exception as exc:
        print(f"[WARNING] Rotated inference failed (maybe missing cv2?): {exc}", file=sys.stderr)
        result_rot = []
        H, W = 0, 0

    # -----------------------------------------------------------------------
    # Parse PaddleOCR v3 result objects
    # -----------------------------------------------------------------------
    raw_detections = []
    
    def extract_res(results, is_rotated=False):
        extracted = []
        if not results: return extracted
        for res in results:
            res_dict = res
            try:
                polys  = res_dict["dt_polys"]   # shape: (N, 4, 2)
                texts  = res_dict["rec_texts"]  # shape: (N,)
                scores = res_dict["rec_scores"] # shape: (N,)
            except (KeyError, TypeError):
                polys  = getattr(res, "dt_polys",   [])
                texts  = getattr(res, "rec_texts",  [])
                scores = getattr(res, "rec_scores", [])

            for poly, text, score in zip(polys, texts, scores):
                if is_rotated and H > 0 and W > 0:
                    new_poly = []
                    for p in poly:
                        x_rot, y_rot = p[0], p[1]
                        x_orig = y_rot
                        y_orig = H - x_rot
                        new_poly.append([x_orig, y_orig])
                    extracted.append({
                        "poly":  new_poly,
                        "text":  text,
                        "score": float(score),
                    })
                else:
                    extracted.append({
                        "poly":  poly,
                        "text":  text,
                        "score": float(score),
                    })
        return extracted

    raw_detections.extend(extract_res(result_normal, False))
    raw_detections.extend(extract_res(result_rot, True))

    print(
        f"[INFO] Combined raw detections before NMS/threshold: {len(raw_detections)}",
        file=sys.stderr,
    )

    # -----------------------------------------------------------------------
    # Deduplicate with AABB IoU
    # -----------------------------------------------------------------------
    raw_detections.sort(key=lambda x: x["score"], reverse=True)
    deduped = []
    for raw in raw_detections:
        try:
            points = [[int(round(float(x))), int(round(float(y)))] for x, y in raw["poly"]]
        except Exception:
            points = [[int(round(float(v))) for v in row] for row in raw["poly"]]
        raw["poly"] = points
        
        box = get_aabb(points)
        is_dup = False
        for d in deduped:
            if compute_iou(box, get_aabb(d["poly"])) > 0.3:
                is_dup = True
                break
        if not is_dup:
            deduped.append(raw)
            
    raw_detections = deduped

    # -----------------------------------------------------------------------
    # Build initial structured detections
    # -----------------------------------------------------------------------
    img_dims = get_image_dimensions(image_path)
    detections = []

    for raw in raw_detections:
        score = round(raw["score"], 4)
        if score < confidence_threshold:
            continue

        text = raw["text"].strip()
        points = raw["poly"]
        center = compute_center(points)
        rotation = compute_rotation(points)
        category = classify_text(text)

        detections.append({
            "text":       text,
            "confidence": score,
            "bounding_box": {
                "points": points,
                "center": center,
            },
            "classification":  category,
            "rotation_degrees": rotation,
        })

    # -----------------------------------------------------------------------
    # Merge Ceiling Heights
    # -----------------------------------------------------------------------
    merged_detections = []
    skip_indices = set()
    for i in range(len(detections)):
        if i in skip_indices: continue
        det1 = detections[i]
        
        merged = True
        while merged:
            merged = False
            is_ceil = (det1["classification"] == "ceiling_height" or "clg" in det1["text"].lower() or "ceiling" in det1["text"].lower())
            if not is_ceil:
                break
                
            for j in range(i+1, len(detections)):
                if j in skip_indices: continue
                det2 = detections[j]
                
                dx = abs(det1["bounding_box"]["center"][0] - det2["bounding_box"]["center"][0])
                dy = abs(det1["bounding_box"]["center"][1] - det2["bounding_box"]["center"][1])
                
                if dx <= 40 and dy <= 50:
                    skip_indices.add(j)
                    raw_text_1 = det1["text"]
                    raw_text_2 = det2["text"]
                    
                    # combine text - top to bottom usually
                    if det2["bounding_box"]["center"][1] < det1["bounding_box"]["center"][1]:
                        new_text = raw_text_2 + " " + raw_text_1
                    else:
                        new_text = raw_text_1 + " " + raw_text_2
                        
                    points = det1["bounding_box"]["points"] + det2["bounding_box"]["points"]
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    new_points = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
                    
                    det1["text"] = new_text
                    det1["bounding_box"]["points"] = new_points
                    det1["bounding_box"]["center"] = compute_center(new_points)
                    det1["classification"] = "ceiling_height"
                    merged = True
                    break  # break inner loop to re-evaluate with updated det1
        merged_detections.append(det1)

    # -----------------------------------------------------------------------
    # Filter Junk Detections
    # -----------------------------------------------------------------------
    final_detections = []
    det_id = 0
    for d in merged_detections:
        category = d["classification"]
        text = d["text"]
        conf = d["confidence"]
        t_lower = text.lower()
        
        if conf < 0.6 and len(text) <= 3 and category == "annotation":
            is_kw = False
            for kw in FIXTURE_KEYWORDS + ROOM_KEYWORDS:
                if kw in t_lower:
                    is_kw = True
                    break
            if not is_kw and not _CEILING_RE.search(text):
                d["classification"] = "noise"
        
        d["id"] = det_id
        final_detections.append(d)
        det_id += 1
        
    detections = final_detections

    print(
        f"[INFO] Detections after NMS, merging, and confidence threshold ({confidence_threshold}): "
        f"{len(detections)}",
        file=sys.stderr,
    )

    # -----------------------------------------------------------------------
    # Summary counts
    # -----------------------------------------------------------------------
    summary = {
        "dimensions_found":      sum(1 for d in detections if d["classification"] == "dimension"),
        "room_labels_found":     sum(1 for d in detections if d["classification"] == "room_label"),
        "ceiling_heights_found": sum(1 for d in detections if d["classification"] == "ceiling_height"),
        "fixture_labels_found":  sum(1 for d in detections if d["classification"] == "fixture_label"),
        "annotations_found":     sum(1 for d in detections if d["classification"] == "annotation"),
        "noise_filtered":        sum(1 for d in detections if d["classification"] == "noise"),
    }

    output_data = {
        "input_image":              str(Path(image_path).resolve()),
        "image_dimensions":         img_dims,
        "total_detections":         len(detections),
        "confidence_threshold_used": confidence_threshold,
        "detections":               detections,
        "summary":                  summary,
    }

    # -----------------------------------------------------------------------
    # Write JSON output
    # -----------------------------------------------------------------------
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"[INFO] JSON output saved to: {output_path}", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Optionally write visualization
    # -----------------------------------------------------------------------
    if save_viz:
        viz_path = str(Path(output_path).with_suffix("").with_suffix("")) + "_ocr_viz.png"
        # Strip trailing _ocr_result so we don't get _ocr_result_ocr_viz.png
        base = output_path
        if base.endswith("_ocr_result.json"):
            base = base[: -len("_ocr_result.json")]
        viz_path = base + "_ocr_viz.png"
        save_visualization(image_path, detections, viz_path)
        print(f"[INFO] Visualization saved to: {viz_path}", file=sys.stderr)

    return output_data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="floorplan_ocr.py",
        description=(
            "Run PaddleOCR PP-OCRv5 on an architectural floor plan image and "
            "output a structured JSON file with every detected text element."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--image",
        required=True,
        metavar="PATH",
        help="Path to the input floor plan image (png/jpg/jpeg/tiff/bmp).",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Path for the output JSON file. "
            "Defaults to <image_stem>_ocr_result.json in the same directory as the image."
        ),
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.5,
        metavar="FLOAT",
        help="Minimum confidence score (0–1) for a detection to be included.",
    )
    parser.add_argument(
        "--save-visualization",
        action="store_true",
        help=(
            "When set, saves an annotated copy of the image with bounding boxes "
            "drawn on it (<output_stem>_ocr_viz.png)."
        ),
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate CLI arguments and exit with a clear message on failure."""
    # Check file exists
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"[ERROR] Input file does not exist: {args.image}", file=sys.stderr)
        sys.exit(1)
    if not image_path.is_file():
        print(f"[ERROR] Input path is not a file: {args.image}", file=sys.stderr)
        sys.exit(1)

    # Check extension
    ext = image_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        print(
            f"[ERROR] Unsupported image format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate confidence threshold
    if not (0.0 <= args.confidence_threshold <= 1.0):
        print(
            f"[ERROR] --confidence-threshold must be between 0 and 1, "
            f"got {args.confidence_threshold}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve output path
    if args.output is None:
        args.output = str(image_path.parent / (image_path.stem + "_ocr_result.json"))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    result = run_ocr(
        image_path=args.image,
        confidence_threshold=args.confidence_threshold,
        save_viz=args.save_visualization,
        output_path=args.output,
    )

    print(
        f"[DONE] {result['total_detections']} detections written to {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
