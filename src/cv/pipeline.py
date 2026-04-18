"""Full CV pipeline orchestrator: image → BuildingGraph.

Chains preprocessing, segmentation, detection, OCR, vectorization, and
grid inference into a single ``process()`` call.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import structlog

from src.core.graph_builder import GraphBuilder
from src.schema.building_graph import BuildingGraph

from .grid_inferrer import GridInferrer
from .ocr_extractor import OCRExtractor
from .preprocessor import Preprocessor
from .room_segmenter import RoomSegmenter
from .symbol_detector import SymbolDetector
from .vectorizer import Vectorizer
from .wall_segmenter import WallSegmenter

logger = structlog.get_logger(__name__)


class CVPipeline:
    """Orchestrates the full image → BuildingGraph pipeline.

    Steps:
    1. Preprocess image (load, deskew, binarise)
    2. Segment walls (U-Net or classical)
    3. Segment rooms (SAM or contour-based)
    4. Detect symbols (YOLOv8 or skip)
    5. Extract text / dimensions (PaddleOCR or skip)
    6. Vectorize wall mask → line segments
    7. Infer grid from wall segments
    8. Assemble → GraphBuilder.from_cv_output()
    """

    def __init__(
        self,
        wall_model_path: str | Path | None = None,
        symbol_model_path: str | Path | None = None,
        sam_checkpoint: str | Path | None = None,
        use_gpu: bool = False,
    ) -> None:
        self.preprocessor = Preprocessor()
        self.wall_segmenter = WallSegmenter(model_path=wall_model_path)
        self.room_segmenter = RoomSegmenter(sam_checkpoint=sam_checkpoint)
        self.symbol_detector = SymbolDetector(model_path=symbol_model_path)
        self.ocr_extractor = OCRExtractor(use_gpu=use_gpu)
        self.vectorizer = Vectorizer()
        self.grid_inferrer = GridInferrer()
        self.graph_builder = GraphBuilder()

    def process(
        self,
        image_path: str | Path,
        project_name: str = "Floor Plan Import",
        num_stories: int = 1,
    ) -> BuildingGraph:
        """Run the full pipeline on a floor-plan image.

        Returns a validated ``BuildingGraph``.
        """
        logger.info("cv_pipeline_start", image=str(image_path))

        # 1. Preprocess
        images = self.preprocessor.preprocess(image_path)
        color = images["original"]
        binary = images["binary"]

        # 2. Wall segmentation
        wall_mask, element_masks = self.wall_segmenter.segment(color)

        # 3. Room segmentation
        room_instances = self.room_segmenter.segment(color, wall_mask)

        # 4. Symbol detection
        symbols = self.symbol_detector.detect(color)

        # 5. OCR + unit inference (MUST run before vectorization so the
        #    vectorizer can derive scale-aware tolerances)
        text_data = self.ocr_extractor.extract(color)

        # 6. Vectorize walls using scale-aware tolerances
        scale = text_data.get("scale_factor")
        wall_segments = self.vectorizer.vectorize(wall_mask, scale_mm_per_px=scale)

        # 7. Vectorize rooms (use resolved scale from vectorizer stats)
        resolved_scale = (
            self.vectorizer.last_stats.scale_mm_per_px
            if self.vectorizer.last_stats is not None
            else scale or 1.0
        )
        room_polygons = self.vectorizer.masks_to_polygons(
            room_instances, scale_mm_per_px=resolved_scale
        )

        # 8. Infer grid (OCR labels take precedence over geometric inference)
        h, w = wall_mask.shape[:2]
        all_text = text_data.get("all_text", []) + text_data.get("grid_labels", [])
        grid_data = self.grid_inferrer.infer(
            wall_segments,
            ocr_text=all_text,
            image_size_px=(w, h),
            scale_mm_per_px=resolved_scale,
        )

        # 9. Associate dimensions
        dim_associations = self.ocr_extractor.associate_dimensions(text_data, wall_segments)

        # 10. Assemble via GraphBuilder
        cv_results = {
            "walls": wall_segments,
            "rooms": room_polygons,
            "grid": grid_data,
            "symbols": symbols,
            "dimensions": dim_associations,
            "text_labels": text_data.get("room_labels", []),
            "scale_factor": scale,
            "element_masks": {k: v.shape for k, v in element_masks.items()},
        }

        logger.info(
            "cv_pipeline_results",
            walls=len(wall_segments),
            rooms=len(room_polygons),
            symbols=len(symbols),
            grid_lines=len(grid_data.get("x_lines", [])) + len(grid_data.get("y_lines", [])),
        )

        # For now, use from_cad_data with the grid/wall data
        # (from_cv_output will be refined as models improve)
        parsed = {
            "walls": wall_segments,
            "rooms": [
                {"polygon": rp["polygon"], "label": None}
                for rp in room_polygons
            ],
            "grid_lines": {
                "x_lines": [
                    {"position_mm": gl.position_mm, "start": [gl.position_mm, 0], "end": [gl.position_mm, 0]}
                    for gl in grid_data.get("x_lines", [])
                ],
                "y_lines": [
                    {"position_mm": gl.position_mm, "start": [0, gl.position_mm], "end": [0, gl.position_mm]}
                    for gl in grid_data.get("y_lines", [])
                ],
            },
            "text_annotations": [
                {"text": t.get("text", ""), "position": t.get("position", [0, 0])}
                for t in text_data.get("room_labels", [])
            ],
            "doors": [s for s in symbols if s.get("class_name") == "door"],
            "windows": [s for s in symbols if s.get("class_name") == "window"],
            "columns": [],
            "units": "mm",
        }

        return self.graph_builder.from_cad_data(
            parsed,
            project_name=project_name,
            num_stories=num_stories,
        )
