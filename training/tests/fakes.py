"""테스트 전용 가짜 구현 + 합성 데이터 생성기. 실제 InsightFace 가중치나 opencv 없이
CPU에서 빠르게 파이프라인 전체를 돌려보기 위한 것들이다 (services/faceguard-model-api의
model-api-ci.yml이 FakeSession/FakeFaceEncoder로 진짜 모델 없이 테스트하는 것과 동일한
선례).
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image

from deepfake_training.common.align import AlignResult
from deepfake_training.common.manifest import ManifestRow


class FakeAligner:
    """항상 얼굴을 찾은 것처럼 동작한다 — 입력 이미지를 aligned_size로 리사이즈만
    한다. cv2/insightface 없이 PIL만으로 동작해서 CI에 무겁지 않다.
    """

    def align(self, image_bgr: np.ndarray, *, aligned_size: int) -> AlignResult:
        rgb = image_bgr[..., ::-1]
        resized_rgb = np.asarray(Image.fromarray(rgb).resize((aligned_size, aligned_size)))
        aligned_bgr = np.ascontiguousarray(resized_rgb[..., ::-1])
        return AlignResult(aligned_bgr=aligned_bgr, detection_score=0.99)


def make_synthetic_image(path: Path, *, seed: int, size: int = 96) -> None:
    """seed 고정 랜덤 RGB 이미지를 만들어 path에 저장한다."""

    rng = np.random.default_rng(seed)
    array = rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path)


def make_synthetic_manifest(
    root: Path,
    *,
    num_subjects_per_label: int = 4,
    frames_per_group: int = 3,
    groups_per_subject: int = 2,
    seed: int = 0,
) -> list[ManifestRow]:
    """label별로 여러 subject, subject별로 여러 group(영상 하나에 해당), group별로
    여러 프레임(이미지 파일)을 만들어 raw ManifestRow 목록으로 돌려준다. split은
    아직 안 채워져 있다 — assign_subject_level_split을 호출해서 채울 것.
    """

    rng = random.Random(seed)
    rows: list[ManifestRow] = []
    counter = 0

    for label in (0, 1):
        for subject_index in range(num_subjects_per_label):
            subject_id = f"label{label}_subject{subject_index}"
            for group_index in range(groups_per_subject):
                group_id = f"{subject_id}_group{group_index}"
                for frame_index in range(frames_per_group):
                    counter += 1
                    image_path = root / f"{group_id}_{frame_index:02d}.png"
                    make_synthetic_image(image_path, seed=seed * 10_000 + counter)
                    rows.append(
                        ManifestRow(
                            path=str(image_path),
                            subject_id=subject_id,
                            group_id=group_id,
                            label=label,
                            dataset="synthetic",
                        )
                    )

    rng.shuffle(rows)
    return rows
