"""딥백신 단위 테스트.

실제 InsightFace 가중치·실제 얼굴 사진에 의존하면 테스트가 느려지고(수 초),
얼굴 원본 이미지를 저장소에 두지 말라는 팀 원칙과도 어긋난다. 대신 얼굴
탐지·인식 모델을 가짜로 바꿔서(둘 다 순수 함수형 인터페이스라 대체하기
쉽다) 탐색 알고리즘(SimBA류 좌표 탐색, epsilon 클리핑, SSIM 하한)이 올바르게
동작하는지를 결정적으로(deterministic) 검증한다.

실제 모델로 진짜 얼굴 사진을 돌렸을 때 유사도가 실제로 낮아지는지는 이번
PR 설명에 적어둔 수동 검증 기록(반복 48~53회, 유사도 1.0 -> 0.93~0.97,
SSIM 0.997 유지)으로 대신한다.
"""

import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import deepbaeksin


class _FakeFace:
    def __init__(self, bbox, kps, embedding):
        self.bbox = bbox
        self.kps = kps
        self.normed_embedding = embedding


def _make_landmark(size: int) -> np.ndarray:
    # ArcFace 기준 정렬 좌표를 테스트 이미지 크기에 맞게 축소한 대략적인 값.
    # 실제 얼굴 좌표가 아니어도 face_align.norm_crop은 어파인 변환만 계산하므로
    # 숫자로만 유효하면(이미지 범위 내) 문제없이 동작한다.
    scale = size / 112.0
    base = np.array(
        [[38.3, 51.7], [73.5, 51.5], [56.0, 71.7], [41.5, 92.4], [70.7, 92.2]],
        dtype=np.float32,
    )
    return base * scale


def _fake_get_feat(aligned_bgr: np.ndarray) -> np.ndarray:
    """정렬된 크롭을 4x4 블록별 채널 평균으로 쪼갠 "임베딩"을 내는 가짜 인식 모델.

    전체 평균 하나만 쓰면 코사인 유사도가 방향이 아니라 크기 변화에 거의
    영향을 안 받아 둔감해진다. 블록별로 나누면 이미지의 어느 부분이
    바뀌었는지가 벡터의 "방향"에 반영돼, 실제 ArcFace처럼 노이즈가 임베딩
    방향을 실제로 움직이는 성질을 재현한다.
    """
    h, w = aligned_bgr.shape[:2]
    grid = 4
    cell_h, cell_w = max(1, h // grid), max(1, w // grid)
    values = []
    for r in range(grid):
        for c in range(grid):
            cell = aligned_bgr[r * cell_h:(r + 1) * cell_h, c * cell_w:(c + 1) * cell_w, :]
            values.extend(cell.astype(np.float64).mean(axis=(0, 1)))
    return np.array(values)


class _FakeRecognitionModel:
    def get_feat(self, aligned_bgr: np.ndarray) -> np.ndarray:
        return _fake_get_feat(aligned_bgr)


class _FakeFaceApp:
    """항상 같은 얼굴 하나만 찾는(또는 얼굴을 못 찾는) 가짜 FaceAnalysis."""

    def __init__(self, *, has_face: bool, image_size: int):
        self.has_face = has_face
        self.models = {"recognition": _FakeRecognitionModel()}
        self._landmark = _make_landmark(image_size)

    def get(self, bgr: np.ndarray):
        if not self.has_face:
            return []
        from insightface.utils import face_align

        aligned = face_align.norm_crop(bgr, landmark=self._landmark, image_size=112)
        embedding = _fake_get_feat(aligned)
        embedding = embedding / (np.linalg.norm(embedding) + 1e-12)
        h, w = bgr.shape[:2]
        bbox = np.array([0, 0, w, h], dtype=np.float32)
        return [_FakeFace(bbox=bbox, kps=self._landmark, embedding=embedding)]


def _solid_image(size: int = 96, color=(120, 130, 140)) -> Image.Image:
    return Image.new("RGB", (size, size), color=color)


class ApplyDeepbaeksinTestCase(unittest.TestCase):
    def test_no_face_detected_returns_original_unchanged(self):
        fake_app = _FakeFaceApp(has_face=False, image_size=96)
        image = _solid_image()
        with patch.object(deepbaeksin, "_get_face_app", return_value=fake_app):
            protected, meta = deepbaeksin.apply_deepbaeksin(image)

        self.assertFalse(meta["applied"])
        self.assertEqual(meta["reason"], "no_face_detected")
        self.assertEqual(protected.size, image.size)
        self.assertTrue(np.array_equal(np.asarray(protected), np.asarray(image.convert("RGB"))))

    def test_model_unavailable_returns_original_unchanged(self):
        image = _solid_image()
        with patch.object(deepbaeksin, "_get_face_app", return_value=None):
            protected, meta = deepbaeksin.apply_deepbaeksin(image)

        self.assertFalse(meta["applied"])
        self.assertEqual(meta["reason"], "model_unavailable")
        self.assertEqual(protected.size, image.size)

    def test_search_reduces_similarity_while_respecting_ssim_floor(self):
        size = 96
        fake_app = _FakeFaceApp(has_face=True, image_size=size)
        rng = np.random.default_rng(42)
        # 단색이 아니라 약간의 질감을 줘야 블록을 바꿨을 때 평균 픽셀값(가짜
        # 임베딩)이 실제로 움직인다.
        noise = rng.integers(100, 160, size=(size, size, 3), dtype=np.uint8)
        image = Image.fromarray(noise, mode="RGB")

        with patch.object(deepbaeksin, "_get_face_app", return_value=fake_app):
            protected, meta = deepbaeksin.apply_deepbaeksin(
                image,
                epsilon=8,
                max_iterations=60,
                grid_size=6,
                ssim_floor=0.97,
                time_budget_seconds=30.0,
                seed=1,
            )

        self.assertGreater(meta["iterationsRun"], 0)
        self.assertLessEqual(meta["similarityAfter"], 1.0)
        # 가짜 임베딩이라도 탐색이 조금이라도 개선을 찾았다면 1.0보다 작아야 한다.
        self.assertLess(meta["similarityAfter"], 1.0)

        original_array = np.asarray(image.convert("RGB"), dtype=np.float32)
        protected_array = np.asarray(protected, dtype=np.float32)
        actual_ssim = deepbaeksin._ssim(original_array, protected_array)
        self.assertGreaterEqual(actual_ssim, 0.97 - 1e-6)

        # L-infinity epsilon을 넘어서는 변화가 없어야 한다.
        max_change = np.max(np.abs(protected_array - original_array))
        self.assertLessEqual(max_change, 8.0 + 1e-6)

    def test_epsilon_zero_means_no_visible_change_possible(self):
        size = 64
        fake_app = _FakeFaceApp(has_face=True, image_size=size)
        rng = np.random.default_rng(7)
        noise = rng.integers(100, 160, size=(size, size, 3), dtype=np.uint8)
        image = Image.fromarray(noise, mode="RGB")

        with patch.object(deepbaeksin, "_get_face_app", return_value=fake_app):
            protected, meta = deepbaeksin.apply_deepbaeksin(
                image, epsilon=0, max_iterations=20, grid_size=4, time_budget_seconds=10.0
            )

        self.assertFalse(meta["applied"])
        self.assertTrue(np.array_equal(np.asarray(protected), np.asarray(image.convert("RGB"))))


class WarmUpTestCase(unittest.TestCase):
    def test_warm_up_true_when_model_loads(self):
        with patch.object(deepbaeksin, "_get_face_app", return_value=object()):
            self.assertTrue(deepbaeksin.warm_up())

    def test_warm_up_false_when_model_unavailable(self):
        with patch.object(deepbaeksin, "_get_face_app", return_value=None):
            self.assertFalse(deepbaeksin.warm_up())


if __name__ == "__main__":
    unittest.main()
