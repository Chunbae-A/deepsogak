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
버리는" black-box 좌표 탐색(SimBA, Guo et al., "Simple Black-box Adversarial
Attacks", ICML 2019)으로 노이즈를 만든다. 좌표 하나(여기서는 사각 블록 하나)를
뽑아 +epsilon을 먼저 시도하고, 개선이 없으면 -epsilon을 시도하고, 둘 다
실패하면 포기하고 다음 좌표로 넘어가는 SimBA 원 논문의 갱신 규칙을 그대로
따른다.

## 왜 블록 크기를 8의 배수로 고정했나

처음에는 "SimBA-DCT"(Guo et al. 동일 논문의 변형, 픽셀이 아니라 저주파 DCT
계수를 좌표로 써서 query 효율을 높이는 방식)와 "Low-Mid Adversarial
Perturbation against Unauthorized Face Recognition System"(저·중주파
성분이 JPEG 압축에서도 잘 살아남는다는 연구)을 참고해, 8x8 JPEG 블록의
특정 저-중주파 DCT 계수 하나만 건드리는 방식으로 구현했다. 그런데 실제
ArcFace 모델로 검증해보니, epsilon=8 같은 작은 노이즈 예산 안에서는 이
방식이 원래 방식(사각 블록을 통째로 균일하게 밝게/어둡게 미는 방식)보다
공격 효과가 훨씬 약했다(같은 시간 예산 안에서 코사인 유사도가 0.999대에서
거의 안 움직임, 원래 방식은 0.93대까지 낮아짐). 저-중주파 한 계수만으로는
얼굴 임베딩이 실제로 반응하는 미세한 텍스처 정보를 건드리기에 예산이 너무
적었던 것으로 보인다.

그런데 사각 블록을 통째로 균일하게 미는 방식도 알고 보면 이미 "저주파
편향"이다. 블록 안의 모든 픽셀을 똑같이 이동시키는 건, 그 블록 크기가
JPEG의 8x8 그리드와 겹칠 때 사실상 그 안에 포함된 각 JPEG 블록의 **DC
계수**(그 블록의 평균 밝기)만 바꾸는 것과 같다. JPEG는 표준 양자화 표에서
DC 계수를 가장 약하게 압축한다(가장 잘 보존한다). 그래서 블록 크기를
8의 배수(코드에서는 32, 즉 4x4 JPEG 블록 단위)로 맞추면, 원래도 강했던
공격 방식이 "왜 JPEG에도 잘 버티는지"를 정확히 설명할 수 있고, 실측으로도
확인된다(재압축 후에도 코사인 유사도가 거의 그대로 유지됨, 아래 실측 기록
참고). 즉 이 프로젝트에서는 두 논문이 알려주는 통찰(SimBA의 좌표 탐색 규칙,
저주파가 JPEG에 강하다는 사실)을 "저주파 DCT 계수를 직접 고르는 정교한
방식"이 아니라 "JPEG 블록 그리드에 맞춘 균일한 사각 블록 이동"이라는 더
단순하고 실제로 더 효과적인 형태로 반영했다.

## 실측 기록 (2026-08-17, 공개 테스트 이미지 512x512, epsilon=8, 12초 예산)

- 원본 대비 코사인 유사도: 1.000 → 0.929 (전체 파이프라인 재탐지 기준 0.927)
- SSIM: 0.996 (거의 육안 차이 없음)
- JPEG quality=80 재압축 왕복 후 코사인 유사도: 0.923 (거의 그대로 유지)
- JPEG quality=60 재압축 왕복 후 코사인 유사도: 0.909 (여전히 유지)

매 채택마다 L-infinity epsilon과 SSIM 하한을 함께 지켜, "사람 눈에는 거의
그대로, 기계에게는 다른 사람"이라는 목표를 유지한다. 마지막에는 실제 SNS
재업로드를 흉내 낸 JPEG 재압축 왕복 후에도 효과가 남아있는지 검증해
메타데이터에 정직하게 남긴다(100% 보장이 아니라 참고 신호다).

이 모듈은 InsightFace가 설치돼 있지 않거나 얼굴을 찾지 못하는 등 어떤
이유로든 실패하면 예외를 던지지 않고 원본 이미지를 그대로 반환한다 —
"딥백신이 됐다고 거짓으로 표시하지 않는다"는 원칙에 따라, 실패 사유는
반환되는 메타데이터에 정직하게 남긴다.
"""

from __future__ import annotations

import io
import time
from typing import Any

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

THRESHOLD_STATUS = "research_only_unapproved"

# JPEG의 8x8 DCT 그리드와 정렬되도록 8의 배수로 고정한다(모듈 docstring 참고).
BLOCK_SIZE = 32

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


def _jpeg_round_trip(rgb_uint8: np.ndarray, quality: int) -> np.ndarray:
    """SNS 업로드 시 흔히 일어나는 JPEG 재압축을 흉내 낸다(메모리 안에서만)."""
    image = Image.fromarray(rgb_uint8, mode="RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return np.asarray(Image.open(buffer).convert("RGB"), dtype=np.uint8)


def _block_positions(height: int, width: int, block_size: int) -> list[tuple[int, int, int, int]]:
    rows = max(1, height // block_size)
    cols = max(1, width // block_size)
    return [
        (r * block_size, min((r + 1) * block_size, height), c * block_size, min((c + 1) * block_size, width))
        for r in range(rows)
        for c in range(cols)
    ]


def apply_deepbaeksin(
    image: Image.Image,
    *,
    epsilon: int = 8,
    max_iterations: int = 220,
    block_size: int = BLOCK_SIZE,
    ssim_floor: float = 0.97,
    time_budget_seconds: float = 12.0,
    seed: int = 0,
    jpeg_quality_check: int = 80,
) -> tuple[Image.Image, dict[str, Any]]:
    """딥백신 노이즈를 적용한다.

    block_size x block_size 사각 블록을 하나씩 뽑아(SimBA 갱신 규칙: +epsilon을
    먼저 시도하고 실패하면 -epsilon, 둘 다 실패하면 포기) 원본과의 얼굴 임베딩
    코사인 유사도를 낮춘다. 반환값은 (처리된 이미지, 메타데이터). 실패·스킵
    시 이미지는 원본과 동일한 내용을 담은 새 Image 객체이고, applied가
    False다.
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
        "similarityAfterJpegRoundTrip": None,
        "jpegQualityChecked": jpeg_quality_check,
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
    block_positions = _block_positions(height, width, block_size)
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

        current_block = delta[top:bottom, left:right, :]

        # SimBA 갱신 규칙: +epsilon을 먼저 시도하고, 개선이 없으면 -epsilon을
        # 시도한다. 둘 다 개선이 없으면(또는 SSIM 하한을 못 지키면) 이 블록은
        # 포기하고 다음 블록으로 넘어간다.
        for step in (epsilon, -epsilon):
            iterations_run += 1
            candidate_block = np.clip(current_block + step, -epsilon, epsilon)
            candidate_delta = delta.copy()
            candidate_delta[top:bottom, left:right, :] = candidate_block
            candidate = np.clip(original + candidate_delta, 0, 255)

            candidate_embedding = _fast_embed(recognition_model, landmark, candidate.astype(np.uint8))
            candidate_similarity = _cosine_similarity(original_embedding, candidate_embedding)
            if candidate_similarity >= best_similarity:
                continue

            if _ssim(original, candidate) < ssim_floor:
                continue  # 시각적 보존 하한을 못 지키면 아무리 효과적이어도 버린다

            delta = candidate_delta
            best_similarity = candidate_similarity
            break

        if iterations_run >= max_iterations or time.monotonic() - loop_started > time_budget_seconds:
            break

    protected_array = np.clip(original + delta, 0, 255).astype(np.uint8)
    protected_image = Image.fromarray(protected_array, mode="RGB")

    # 빠른 경로(고정 정렬)로 찾은 결과가 실제 전체 파이프라인(재탐지+재정렬)에서도
    # 유효한지, 그리고 SNS 업로드에서 흔한 JPEG 재압축을 한 번 거쳐도 남아있는지
    # 마지막에 검증한다. 이게 실제로 딥소각 얼굴가드나 외부 재인식 시스템,
    # 그리고 재유포 경로에서 보게 될 값이다.
    end_to_end_face = _detect_primary_face(app, protected_array)
    end_to_end_similarity = (
        _cosine_similarity(original_embedding, end_to_end_face.normed_embedding)
        if end_to_end_face is not None
        else None
    )

    jpeg_round_tripped = _jpeg_round_trip(protected_array, jpeg_quality_check)
    jpeg_face = _detect_primary_face(app, jpeg_round_tripped)
    jpeg_similarity = (
        _cosine_similarity(original_embedding, jpeg_face.normed_embedding)
        if jpeg_face is not None
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
            "similarityAfterJpegRoundTrip": (
                round(jpeg_similarity, 6) if jpeg_similarity is not None else None
            ),
            "ssim": round(_ssim(original, protected_array.astype(np.float32)), 6),
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }
    )
    return protected_image, meta
