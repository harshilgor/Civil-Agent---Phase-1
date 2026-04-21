"""OCR ensemble: PaddleOCR primary + PARSeq secondary recognizer.

For every PaddleOCR detection with confidence below 0.85, the cropped text
region is re-recognized with PARSeq. Agreement boosts confidence;
disagreement caps it at 0.75 and attaches a ``conflict_flag``.

The ensemble degrades gracefully:
  * No PaddleOCR → returns an empty result list.
  * No PARSeq → falls back to raw PaddleOCR output, unchanged.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
import structlog

from src.cv.ocr_extractor import paddle_ocr_raw

logger = structlog.get_logger(__name__)


PRIMARY_CONFIDENCE_THRESHOLD = 0.85
AGREEMENT_BOOST = 0.10
DISAGREEMENT_CAP = 0.75


class OCREnsemble:
    """PaddleOCR + PARSeq ensemble wrapper."""

    def __init__(
        self,
        paddle_engine: Any | None = None,
        parseq_model: Any | None = None,
        use_gpu: bool = False,
    ) -> None:
        self._paddle = paddle_engine
        if self._paddle is None:
            try:
                from paddleocr import PaddleOCR

                try:
                    self._paddle = PaddleOCR(
                        use_angle_cls=True, lang="en", use_gpu=use_gpu, show_log=False
                    )
                except (TypeError, ValueError):
                    try:
                        self._paddle = PaddleOCR(
                            use_angle_cls=True, lang="en", show_log=False
                        )
                    except (TypeError, ValueError):
                        try:
                            self._paddle = PaddleOCR(use_angle_cls=True, lang="en")
                        except (TypeError, ValueError):
                            self._paddle = PaddleOCR(lang="en")
            except ImportError:
                logger.warning("paddleocr_not_available_in_ensemble")

        self._parseq = parseq_model
        if self._parseq is None:
            self._parseq = _load_parseq()

    def run(self, image: np.ndarray) -> list[dict[str, Any]]:
        """Run PaddleOCR; for every low-confidence region, reconcile with PARSeq.

        Returns a list of per-text-region dicts with keys::

            text, position, confidence, bbox, engine, conflict_flag
        """
        if self._paddle is None:
            return []

        raw = paddle_ocr_raw(self._paddle, image)
        primary = _parse_paddle_results(raw)
        if not primary:
            return []

        if self._parseq is None:
            # No PARSeq available — pass through PaddleOCR results
            return [_annotate(t, engine="paddle", conflict_flag=False) for t in primary]

        out: list[dict[str, Any]] = []
        for t in primary:
            if t["confidence"] >= PRIMARY_CONFIDENCE_THRESHOLD:
                out.append(_annotate(t, engine="paddle", conflict_flag=False))
                continue

            crop = _crop_bbox(image, t["bbox"])
            if crop is None or crop.size == 0:
                out.append(_annotate(t, engine="paddle", conflict_flag=False))
                continue

            parseq_text, parseq_conf = _parseq_predict(self._parseq, crop)
            if parseq_text is None:
                out.append(_annotate(t, engine="paddle", conflict_flag=False))
                continue

            merged = _merge(t, parseq_text, parseq_conf)
            out.append(merged)
        logger.info(
            "ocr_ensemble_run",
            total=len(primary),
            reconciled=sum(1 for r in out if r["engine"] != "paddle"),
            conflicts=sum(1 for r in out if r.get("conflict_flag")),
        )
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_paddle_results(raw: list) -> list[dict[str, Any]]:
    texts: list[dict[str, Any]] = []
    if not raw or not raw[0]:
        return texts
    for item in raw[0]:
        bbox, (text, confidence) = item
        cx = sum(p[0] for p in bbox) / 4
        cy = sum(p[1] for p in bbox) / 4
        texts.append(
            {
                "text": text.strip(),
                "position": [round(cx, 1), round(cy, 1)],
                "confidence": round(float(confidence), 4),
                "bbox": bbox,
            }
        )
    return texts


def _annotate(t: dict[str, Any], *, engine: str, conflict_flag: bool) -> dict[str, Any]:
    out = dict(t)
    out["engine"] = engine
    out["conflict_flag"] = conflict_flag
    return out


def _crop_bbox(image: np.ndarray, bbox: list[list[float]]) -> np.ndarray | None:
    xs = [int(round(p[0])) for p in bbox]
    ys = [int(round(p[1])) for p in bbox]
    x1, x2 = max(min(xs), 0), min(max(xs), image.shape[1])
    y1, y2 = max(min(ys), 0), min(max(ys), image.shape[0])
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2].copy()


def _merge(primary: dict[str, Any], parseq_text: str, parseq_conf: float) -> dict[str, Any]:
    """Reconcile a PaddleOCR result with a PARSeq result for the same crop."""
    paddle_text = primary["text"]
    paddle_conf = float(primary["confidence"])

    if _strings_equivalent(paddle_text, parseq_text):
        boosted = min(1.0, (paddle_conf + parseq_conf) / 2 + AGREEMENT_BOOST)
        return _annotate(
            {**primary, "text": paddle_text, "confidence": round(boosted, 4)},
            engine="paddle+parseq(agreement)",
            conflict_flag=False,
        )

    if parseq_conf > paddle_conf:
        return _annotate(
            {**primary, "text": parseq_text, "confidence": round(min(parseq_conf, DISAGREEMENT_CAP), 4)},
            engine="parseq",
            conflict_flag=True,
        )
    return _annotate(
        {**primary, "confidence": round(min(paddle_conf, DISAGREEMENT_CAP), 4)},
        engine="paddle",
        conflict_flag=True,
    )


def _strings_equivalent(a: str, b: str) -> bool:
    """Loose equality — strip whitespace, case-fold, and ignore trailing punctuation."""
    def _norm(s: str) -> str:
        return s.strip().lower().rstrip(".,:;")

    return _norm(a) == _norm(b)


def _load_parseq() -> Any | None:
    """Load the PARSeq pretrained checkpoint via torch.hub.

    Returns ``None`` when torch or the baudm/parseq repo is not available.
    """
    try:
        import torch  # noqa: F401
    except ImportError:
        logger.warning("parseq_skipped_no_torch")
        return None
    try:
        import torch

        model = torch.hub.load("baudm/parseq", "parseq", pretrained=True, trust_repo=True)
        model.eval()
        logger.info("parseq_loaded")
        return model
    except Exception as exc:  # pragma: no cover — network-dependent
        logger.warning("parseq_load_failed", error=str(exc))
        return None


def _parseq_predict(model: Any, crop: np.ndarray) -> tuple[str | None, float]:
    """Run PARSeq on a cropped BGR image; returns ``(text, confidence)``."""
    try:
        import torch
        from PIL import Image

        if crop.ndim == 2:
            rgb = cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)

        # PARSeq's torch.hub entrypoint exposes a ``img_transform`` and ``tokenizer``
        transform = model.img_transform if hasattr(model, "img_transform") else None
        if transform is None:
            # Fallback — manual resize to 32x128 (PARSeq default)
            from torchvision import transforms

            transform = transforms.Compose([
                transforms.Resize((32, 128)),
                transforms.ToTensor(),
                transforms.Normalize(mean=(0.5,) * 3, std=(0.5,) * 3),
            ])
        x = transform(pil).unsqueeze(0)

        with torch.no_grad():
            logits = model(x)
            probs = logits.softmax(-1)
            preds, confs = model.tokenizer.decode(probs)
        return preds[0], float(confs[0].mean().item())
    except Exception as exc:  # pragma: no cover — model-dependent
        logger.warning("parseq_predict_failed", error=str(exc))
        return None, 0.0


__all__ = ["OCREnsemble"]
