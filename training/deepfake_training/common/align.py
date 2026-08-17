"""얼굴 검출 + 정렬. InsightFace buffalo_l(SCRFD 검출 + ArcFace 5점 랜드마크)로
정사각형 정렬 크롭을 만든다. 실제 검출기가 필요 없는 테스트에서는 이 모듈의
FaceAligner 프로토콜만 만족하는 가짜 구현(tests/fakes.py::FakeAligner)을 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class FaceAligner(Protocol):
    def align(self, image_bgr: np.ndarray, *, aligned_size: int) -> "AlignResult | None":
        """BGR uint8 이미지에서 얼굴을 찾아 정렬한다. 얼굴이 없으면 None."""
        ...


@dataclass(frozen=True)
class AlignResult:
    aligned_bgr: np.ndarray  # (aligned_size, aligned_size, 3) uint8 BGR
    detection_score: float


class InsightFaceAligner:
    """InsightFace buffalo_l 기반 실제 구현. 여러 얼굴이 잡히면 검출 점수가 가장 높은
    얼굴 하나만 쓴다(학습 데이터는 한 프레임에 얼굴 하나만 있다고 가정).
    """

    def __init__(self, *, detection_size: int = 640, device: str = "cpu") -> None:
        self._detection_size = detection_size
        self._device = device
        self._app = None

    def _ensure_loaded(self) -> None:
        if self._app is not None:
            return
        from insightface.app import FaceAnalysis

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if self._device == "cuda"
            else ["CPUExecutionProvider"]
        )
        app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection", "recognition"],
            providers=providers,
        )
        app.prepare(
            ctx_id=0 if self._device == "cuda" else -1,
            det_size=(self._detection_size, self._detection_size),
        )
        self._app = app

    def align(self, image_bgr: np.ndarray, *, aligned_size: int) -> AlignResult | None:
        self._ensure_loaded()
        faces = self._app.get(image_bgr)
        if not faces:
            return None

        best = max(faces, key=lambda face: float(face.det_score))

        from insightface.utils import face_align

        aligned = face_align.norm_crop(image_bgr, landmark=best.kps, image_size=aligned_size)
        return AlignResult(aligned_bgr=aligned, detection_score=float(best.det_score))
