"""딥백신: 얼굴 임베딩을 흔드는 black-box 적대적 노이즈.

기술스택 문서상 딥백신은 PhotoGuard(MadryLab, PGD 기반) 컨셉을 참고한다. 다만
원조 PhotoGuard는 디퓨전 모델의 latent 인코더까지 공격 대상으로 삼아야 해서
GPU와 수 GB짜리 모델 다운로드가 필요하다. 이 저장소·얼굴가드 파이프라인은
이미 InsightFace buffalo_l(ArcFace)을 동일인 판별에 쓰고 있으므로, 같은 모델을
공격 대상으로 삼아 "이 얼굴의 ArcFace 임베딩이 원본과 달라지게 만든다"는
축소된 목표로 구현한다. ArcFace 임베딩은 얼굴가드·딥페이크 판별 파이프라인
전체의 입력이므로, 이 임베딩만 흔들어도 자동 재인식에 대한 실질적인 방어
효과가 있다.

ArcFace는 ONNX로 배포돼 있어 역전파(그라디언트)를 직접 쓸 수 없다. 대신
그라디언트 없이 "방향을 하나 시도해보고 유사도가 낮아지면 채택, 아니면
버리는" black-box 좌표 탐색(SimBA, Guo et al. 2019, "Simple Black-box
Adversarial Attacks"의 좌표 기반 탐색 방식)으로 노이즈를 만든다. 매 스텝
L-infinity epsilon과 SSIM 하한을 지켜, "사람 눈에는 거의 그대로, 기계에게는
다른 사람"이라는 목표를 유지한다.

이 모듈은 InsightFace가 설치돼 있지 않거나 얼굴을 찾지 못하는 등 어떤
이유로든 실패하면 예외를 던지지 않고 원본 이미지를 그대로 반환한다 —
"딥백신이 됐다고 거짓으로 표시하지 않는다"는 원칙에 따라, 실패 사유는
반환되는 메타데이터에 정직하게 남긴다.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

THRESHOLD_STATUS = "research_only_unapproved"

_face_app = None
_face_app_error: str | None = None


def warm_up() -> bool:
    """서버 시작 시 미리 호출해 모델 로딩 비용을 첫 요청 밖으로 빼낸다.

    반환값은 로딩 성공 여부(사용 가능한 GPU/CPU 프로바이더로 모델을 올렸는지).
    """
    return _get_face_app() is not None


def _get_face_app():
    """InsightFace FaceAnalysis(buffalo_l)를 지연 로딩한다. 실패하면 None."""
    global _face_app, _face_app_error
    if _face_app is not None or _face_app_error is not None:
        return _face_app
    try:
        from insightface.app import FaceAnalysis

        # 랜드마크·성별나이 모델은 필요 없다 — 얼굴 위치(detection)와 임베딩
        # (recognition)만 있으면 되므로 allowed_modules로 나머지를 아예 로딩·실행
        # 하지 않는다. det_size도 낮춰 CPU에서 반복 탐색이 가능한 속도로 맞춘다.
        app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition"],
        )
        app.prepare(ctx_id=-1, det_size=(320, 320))
        _face_app = app
    except Exception as exc:  # noqa: BLE001 - 모델 로딩 실패는 전부 "사용 불가"로 취급
        _face_app_error = str(exc)
    return _face_app


def _detect_primary_face(app, rgb: np.ndarray):
    """RGB uint8 배열에서 가장 큰 얼굴 하나를 찾는다(전체 탐지 파이프라인, 느림)."""
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    faces = app.get(bgr)
    if not faces:
        return None
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))


def _fast_embed(recognition_model, landmark: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """이미 알고 있는 얼굴 위치(landmark)로 정렬만 다시 하고 인식 모델만 돌린다(빠름).

    탐지·정렬 전체 파이프라인을 매 반복 다시 돌리면 한 스텝에 수백 ms가 걸려 탐색
    횟수가 너무 적어진다. 노이즈 폭이 L-infinity epsilon으로 작게 제한돼 있어
    원본에서 구한 얼굴 위치가 후보 이미지에서도 그대로 유효하다고 가정할 수 있으므로,
    정렬 크롭 + 인식 모델 forward만 반복한다. 최종 결과는 다시 전체 파이프라인으로
    검증한다(아래 apply_deepbaeksin의 end-to-end 재확인 참고).
    """
    from insightface.utils import face_align

    bgr = np.ascontiguousarray(rgb[:, :, ::-1]).astype(np.uint8)
    aligned = face_align.norm_crop(bgr, landmark=landmark, image_size=112)
    feat = recognition_model.get_feat(aligned).flatten()
    return feat / (np.linalg.norm(feat) + 1e-12)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _ssim(original: np.ndarray, candidate: np.ndarray) -> float:
    return float(
        structural_similarity(original, candidate, channel_axis=2, data_range=255)
    )


def apply_deepbaeksin(
    image: Image.Image,
    *,
    epsilon: int = 8,
    max_iterations: int = 150,
    grid_size: int = 14,
    ssim_floor: float = 0.97,
    time_budget_seconds: float = 12.0,
    seed: int = 0,
) -> tuple[Image.Image, dict[str, Any]]:
    """딥백신 노이즈를 적용한다.

    반환값은 (처리된 이미지, 메타데이터). 실패·스킵 시 이미지는 원본과 동일한
    내용을 담은 새 Image 객체이고, 메타데이터의 applied가 False다.
    """
    started = time.monotonic()
    rgb_image = image.convert("RGB")
    original = np.asarray(rgb_image, dtype=np.float32)
    height, width = original.shape[:2]

    meta: dict[str, Any] = {
        "applied": False,
        "reason": None,
        "iterationsRun": 0,
        "epsilon": epsilon,
        "similarityAfter": None,
        "endToEndSimilarityAfter": None,
        "ssim": None,
        "elapsedSeconds": 0.0,
        "thresholdStatus": THRESHOLD_STATUS,
    }

    app = _get_face_app()
    if app is None:
        meta["reason"] = "model_unavailable"
        meta["elapsedSeconds"] = round(time.monotonic() - started, 3)
        return rgb_image, meta

    primary_face = _detect_primary_face(app, original.astype(np.uint8))
    if primary_face is None:
        meta["reason"] = "no_face_detected"
        meta["elapsedSeconds"] = round(time.monotonic() - started, 3)
        return rgb_image, meta

    original_embedding = primary_face.normed_embedding
    recognition_model = app.models["recognition"]
    landmark = primary_face.kps

    rng = np.random.default_rng(seed)
    grid_h = max(1, height // grid_size)
    grid_w = max(1, width // grid_size)
    block_positions = [
        (r * grid_h, min((r + 1) * grid_h, height), c * grid_w, min((c + 1) * grid_w, width))
        for r in range(grid_size)
        for c in range(grid_size)
    ]
    rng.shuffle(block_positions)

    delta = np.zeros_like(original, dtype=np.float32)
    best_similarity = 1.0  # 원본 대 원본 유사도(자기 자신)에서 출발
    iterations_run = 0
    # 모델 로딩(최초 1회, 서버 시작 시 미리 데워둠)과 첫 탐지는 시간 예산에서
    # 제외한다 — 탐색 루프 자체에만 시간 예산을 적용해야, 서버가 막 켜진
    # 직후의 첫 요청이라고 해서 노이즈 탐색을 거의 못 하는 일이 없다.
    loop_started = time.monotonic()

    for top, bottom, left, right in block_positions:
        if iterations_run >= max_iterations:
            break
        if time.monotonic() - loop_started > time_budget_seconds:
            break
        iterations_run += 1

        step_sign = rng.choice([-1.0, 1.0])
        candidate_delta = delta.copy()
        candidate_delta[top:bottom, left:right, :] = np.clip(
            candidate_delta[top:bottom, left:right, :] + step_sign * epsilon,
            -epsilon,
            epsilon,
        )
        candidate = np.clip(original + candidate_delta, 0, 255)

        candidate_embedding = _fast_embed(recognition_model, landmark, candidate.astype(np.uint8))
        candidate_similarity = _cosine_similarity(original_embedding, candidate_embedding)
        if candidate_similarity >= best_similarity:
            continue  # 개선 없음 — 이 블록은 버린다(SimBA의 채택/기각 규칙)

        if _ssim(original, candidate) < ssim_floor:
            continue  # 시각적 보존 하한을 못 지키면 아무리 효과적이어도 버린다

        delta = candidate_delta
        best_similarity = candidate_similarity

    protected_array = np.clip(original + delta, 0, 255).astype(np.uint8)
    protected_image = Image.fromarray(protected_array, mode="RGB")

    # 빠른 경로(고정 정렬)로 찾은 결과가 실제 전체 파이프라인(재탐지+재정렬)에서도
    # 유효한지 마지막에 한 번 더 검증한다. 이게 실제로 딥소각 얼굴가드나 외부
    # 재인식 시스템이 보게 될 값이다.
    end_to_end_face = _detect_primary_face(app, protected_array)
    end_to_end_similarity = (
        _cosine_similarity(original_embedding, end_to_end_face.normed_embedding)
        if end_to_end_face is not None
        else None
    )

    applied = iterations_run > 0 and bool(np.any(delta))
    if end_to_end_face is None:
        reason = "face_undetectable_after_protection"
    elif applied:
        reason = "ok"
    else:
        reason = "no_effective_direction_found"

    meta.update(
        {
            "applied": applied,
            "reason": reason,
            "iterationsRun": iterations_run,
            "similarityAfter": round(best_similarity, 6),
            "endToEndSimilarityAfter": (
                round(end_to_end_similarity, 6) if end_to_end_similarity is not None else None
            ),
            "ssim": round(_ssim(original, protected_array.astype(np.float32)), 6),
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }
    )
    return protected_image, meta
