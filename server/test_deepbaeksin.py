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

import os
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
    """정렬된 크롭을 4x4 블록별 채널 평균(전체 평균 제거)으로 쪼갠 가짜 임베딩.

    블록 평균을 그대로 쓰면 모든 값이 배경 밝기(~100~160)라는 큰 공통
    성분에 묻혀서, 아주 작은 지역적 변화는 코사인 유사도를 거의 못 움직인다
    (실측: epsilon=8짜리 노이즈로도 유사도가 0.9999999 언저리에서 안 움직임).
    전체 평균을 빼서 "이 블록이 전체 평균보다 얼마나 밝은가"라는 상대값만
    남기면, 지역적 변화가 벡터의 방향에 훨씬 잘 반영된다(실측: 같은 노이즈로
    유사도가 0.99 근처까지 움직임). 실제 ArcFace도 절대 밝기가 아니라
    상대적인 지역 패턴에 반응하도록 학습돼 있어, 이 쪽이 더 현실적인 가짜
    모델이다.
    """
    h, w = aligned_bgr.shape[:2]
    grid = 4
    cell_h, cell_w = max(1, h // grid), max(1, w // grid)
    global_mean = aligned_bgr.astype(np.float64).mean(axis=(0, 1))
    values = []
    for r in range(grid):
        for c in range(grid):
            cell = aligned_bgr[r * cell_h:(r + 1) * cell_h, c * cell_w:(c + 1) * cell_w, :]
            values.extend(cell.astype(np.float64).mean(axis=(0, 1)) - global_mean)
    return np.array(values)


class _FakeRecognitionModel:
    def get_feat(self, aligned_bgr: np.ndarray) -> np.ndarray:
        return _fake_get_feat(aligned_bgr)


class _FakeFaceApp:
    """항상 같은 얼굴 하나만 찾는(또는 얼굴을 못 찾는) 가짜 FaceAnalysis."""

    def __init__(self, *, has_face: bool, image_size: int, bbox: tuple[float, float, float, float] | None = None):
        self.has_face = has_face
        self.models = {"recognition": _FakeRecognitionModel()}
        self._landmark = _make_landmark(image_size)
        self._bbox = bbox

    def get(self, bgr: np.ndarray):
        if not self.has_face:
            return []
        from insightface.utils import face_align

        aligned = face_align.norm_crop(bgr, landmark=self._landmark, image_size=112)
        embedding = _fake_get_feat(aligned)
        embedding = embedding / (np.linalg.norm(embedding) + 1e-12)
        h, w = bgr.shape[:2]
        bbox = np.array(self._bbox if self._bbox is not None else (0, 0, w, h), dtype=np.float32)
        return [_FakeFace(bbox=bbox, kps=self._landmark, embedding=embedding)]


def _solid_image(size: int = 96, color=(120, 130, 140)) -> Image.Image:
    return Image.new("RGB", (size, size), color=color)


class ApplyDeepbaeksinTestCase(unittest.TestCase):
    def test_no_face_detected_returns_original_unchanged(self):
        fake_app = _FakeFaceApp(has_face=False, image_size=96)
        image = _solid_image()
        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": fake_app}):
            protected, meta = deepbaeksin.apply_deepbaeksin(image)

        self.assertFalse(meta["applied"])
        self.assertEqual(meta["reason"], "no_face_detected")
        self.assertEqual(protected.size, image.size)
        self.assertTrue(np.array_equal(np.asarray(protected), np.asarray(image.convert("RGB"))))

    def test_model_unavailable_returns_original_unchanged(self):
        image = _solid_image()
        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": None}):
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

        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": fake_app}):
            protected, meta = deepbaeksin.apply_deepbaeksin(
                image,
                epsilon=8,
                max_iterations=60,
                block_size=24,
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

        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": fake_app}):
            protected, meta = deepbaeksin.apply_deepbaeksin(
                image, epsilon=0, max_iterations=20, time_budget_seconds=10.0
            )

        self.assertFalse(meta["applied"])
        self.assertTrue(np.array_equal(np.asarray(protected), np.asarray(image.convert("RGB"))))

    def test_meta_reports_jpeg_round_trip_similarity(self):
        size = 96
        fake_app = _FakeFaceApp(has_face=True, image_size=size)
        rng = np.random.default_rng(3)
        noise = rng.integers(100, 160, size=(size, size, 3), dtype=np.uint8)
        image = Image.fromarray(noise, mode="RGB")

        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": fake_app}):
            _, meta = deepbaeksin.apply_deepbaeksin(
                image, max_iterations=80, time_budget_seconds=30.0, seed=2, jpeg_quality_check=80
            )

        self.assertEqual(meta["jpegQualityChecked"], 80)
        self.assertIsNotNone(meta["similarityAfterJpegRoundTrip"])
        self.assertLessEqual(meta["similarityAfterJpegRoundTrip"], 1.0)


class BlockSearchRegionTestCase(unittest.TestCase):
    def test_face_search_region_adds_margin_and_clamps_to_image(self):
        bbox = np.array([60, 60, 84, 84], dtype=np.float32)
        region = deepbaeksin._face_search_region(bbox, height=96, width=96, margin_ratio=0.5)
        self.assertEqual(region, (48, 96, 48, 96))

    def test_face_search_region_full_image_bbox_stays_full_image(self):
        bbox = np.array([0, 0, 96, 96], dtype=np.float32)
        region = deepbaeksin._face_search_region(bbox, height=96, width=96)
        self.assertEqual(region, (0, 96, 0, 96))

    def test_block_positions_stay_within_given_region(self):
        positions = deepbaeksin._block_positions(top=48, bottom=96, left=48, right=96, block_size=24)
        self.assertTrue(positions)
        for top, bottom, left, right in positions:
            self.assertGreaterEqual(top, 48)
            self.assertLessEqual(bottom, 96)
            self.assertGreaterEqual(left, 48)
            self.assertLessEqual(right, 96)

    def test_apply_deepbaeksin_never_modifies_pixels_outside_face_region(self):
        """탐색이 효과를 찾든 못 찾든, 얼굴 영역(+마진) 밖 픽셀은 항상 원본 그대로여야 한다."""
        size = 96
        # 얼굴이 우하단 모서리에만 있다고 가정하면, 마진(50%)을 더해도 좌상단
        # 48x48 영역은 탐색 범위 밖이다.
        fake_app = _FakeFaceApp(has_face=True, image_size=size, bbox=(60, 60, 84, 84))
        rng = np.random.default_rng(21)
        noise = rng.integers(100, 160, size=(size, size, 3), dtype=np.uint8)
        image = Image.fromarray(noise, mode="RGB")

        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": fake_app}):
            protected, _ = deepbaeksin.apply_deepbaeksin(
                image, max_iterations=200, block_size=24, time_budget_seconds=30.0, seed=1
            )

        original_array = np.asarray(image.convert("RGB"))
        protected_array = np.asarray(protected)
        self.assertTrue(np.array_equal(original_array[0:48, 0:48], protected_array[0:48, 0:48]))


class TargetModelNamesTestCase(unittest.TestCase):
    def test_defaults_to_single_model_without_env_var(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop(deepbaeksin._TARGET_MODELS_ENV_VAR, None)
            self.assertEqual(deepbaeksin.target_model_names(), ("buffalo_l",))

    def test_parses_comma_separated_env_var(self):
        with patch.dict("os.environ", {deepbaeksin._TARGET_MODELS_ENV_VAR: "buffalo_l, buffalo_sc ,"}):
            self.assertEqual(deepbaeksin.target_model_names(), ("buffalo_l", "buffalo_sc"))


class EnsembleTestCase(unittest.TestCase):
    def test_ensemble_optimizes_average_similarity_across_models(self):
        """두 가짜 모델을 동시에 타깃으로 주면, 결과는 각 모델 평균이 낮아지는
        방향으로 나오고 메타데이터에 모델별 값이 함께 담겨야 한다."""
        size = 96
        fake_app_a = _FakeFaceApp(has_face=True, image_size=size)
        fake_app_b = _FakeFaceApp(has_face=True, image_size=size)
        rng = np.random.default_rng(11)
        noise = rng.integers(100, 160, size=(size, size, 3), dtype=np.uint8)
        image = Image.fromarray(noise, mode="RGB")

        with patch.object(
            deepbaeksin,
            "_get_face_apps",
            return_value={"model_a": fake_app_a, "model_b": fake_app_b},
        ):
            protected, meta = deepbaeksin.apply_deepbaeksin(
                image, max_iterations=80, time_budget_seconds=30.0, seed=5
            )

        self.assertEqual(set(meta["usedModels"]), {"model_a", "model_b"})
        self.assertIsNotNone(meta["similarityAfterByModel"])
        self.assertEqual(set(meta["similarityAfterByModel"].keys()), {"model_a", "model_b"})
        # 두 가짜 모델이 완전히 동일한 임베딩 함수를 쓰므로 평균과 개별값이 같아야 한다.
        avg_of_models = sum(meta["similarityAfterByModel"].values()) / 2
        self.assertAlmostEqual(meta["similarityAfter"], avg_of_models, places=5)
        self.assertLess(meta["similarityAfter"], 1.0)
        self.assertEqual(protected.size, image.size)

    def test_one_failed_model_does_not_block_the_other(self):
        """지정한 모델 중 하나가 로딩에 실패해도(None) 나머지 모델로 계속 진행한다."""
        size = 96
        fake_app = _FakeFaceApp(has_face=True, image_size=size)
        rng = np.random.default_rng(9)
        noise = rng.integers(100, 160, size=(size, size, 3), dtype=np.uint8)
        image = Image.fromarray(noise, mode="RGB")

        with patch.object(
            deepbaeksin,
            "_get_face_apps",
            return_value={"model_a": fake_app, "model_b_failed": None},
        ):
            protected, meta = deepbaeksin.apply_deepbaeksin(
                image, max_iterations=40, time_budget_seconds=30.0, seed=6
            )

        self.assertEqual(meta["usedModels"], ["model_a"])
        self.assertNotIn("model_b_failed", meta["similarityAfterByModel"])
        self.assertEqual(protected.size, image.size)


class WarmUpTestCase(unittest.TestCase):
    def test_warm_up_true_when_model_loads(self):
        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": object()}):
            self.assertTrue(deepbaeksin.warm_up())

    def test_warm_up_false_when_model_unavailable(self):
        with patch.object(deepbaeksin, "_get_face_apps", return_value={"fake_model": None}):
            self.assertFalse(deepbaeksin.warm_up())


if __name__ == "__main__":
    unittest.main()
