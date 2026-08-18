"""Google Cloud Vision Web Detection 기반 공개 후보 수집기.

얼굴가드 API는 여기서 찾은 URL을 ArcFace와 ONNX 모델 API에 전달해 동일인·
딥페이크 여부를 판별한다(server/main.py의 /api/faceguard/scans/* 참고).

예전에는 이 모듈이 pHash 실측 검증(scan_web)까지 자체적으로 했지만, 그
방식은 동일인 여부를 픽셀 유사도로만 근사해 실제로는 신뢰도가 낮았다.
#80에서 그 경로를 걷어내고 discover_web_candidates()가 수집한 URL을 실제
ArcFace/EfficientNet-B4 모델(services/faceguard-model-api)로 넘기는 방식
하나로 통일했다.
"""

import base64
import logging
import os
from typing import Any

import requests

logger = logging.getLogger("deepsogak")

VISION_ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"


class VisionScanError(RuntimeError):
    """Google Vision 후보 수집 실패를 비밀값 없이 서버 계층에 전달한다."""

    def __init__(self, code: str, message: str, *, unavailable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.unavailable = unavailable


def _request_web_detection(image_bytes: bytes) -> dict[str, Any]:
    """Web Detection 원본 응답을 반환한다.

    API 키는 URL이나 로그에 남지 않도록 Google 권장 방식인 x-goog-api-key
    헤더로 전달한다. HTTP 200 안의 응답별 error 필드도 실패로 처리한다.
    """

    api_key = os.environ.get("GOOGLE_VISION_API_KEY", "").strip()
    if not api_key:
        raise VisionScanError(
            "GOOGLE_VISION_API_KEY_MISSING",
            "Google Vision API 키가 설정되지 않았습니다.",
            unavailable=True,
        )

    try:
        response = requests.post(
            VISION_ANNOTATE_URL,
            headers={"x-goog-api-key": api_key},
            json={
                "requests": [
                    {
                        "image": {"content": base64.b64encode(image_bytes).decode()},
                        "features": [{"type": "WEB_DETECTION", "maxResults": 50}],
                    }
                ]
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise VisionScanError(
            "GOOGLE_VISION_REQUEST_FAILED",
            "Google Vision Web Detection 호출에 실패했습니다.",
            unavailable=True,
        ) from error
    except (TypeError, ValueError) as error:
        raise VisionScanError(
            "GOOGLE_VISION_INVALID_RESPONSE",
            "Google Vision 응답 형식이 올바르지 않습니다.",
        ) from error

    responses = payload.get("responses")
    if not isinstance(responses, list) or not responses or not isinstance(responses[0], dict):
        raise VisionScanError(
            "GOOGLE_VISION_INVALID_RESPONSE",
            "Google Vision 응답에 분석 결과가 없습니다.",
        )
    first = responses[0]
    if isinstance(first.get("error"), dict):
        raise VisionScanError(
            "GOOGLE_VISION_ANALYSIS_FAILED",
            "Google Vision이 이미지 분석을 완료하지 못했습니다.",
        )
    web = first.get("webDetection", {})
    if not isinstance(web, dict):
        raise VisionScanError(
            "GOOGLE_VISION_INVALID_RESPONSE",
            "Google Vision Web Detection 결과가 올바르지 않습니다.",
        )
    return web


def discover_web_candidates(
    image_bytes: bytes,
    *,
    maximum_results: int = 10,
) -> dict[str, Any]:
    """Google Vision에서 공개 후보 URL을 수집해 모델 API 입력으로 정규화한다.

    pHash로 먼저 제거하지 않는다. 크롭·압축·합성된 얼굴은 전체 이미지 pHash가
    크게 달라질 수 있으므로, 후보의 실제 동일인 여부는 다음 단계 ArcFace가 맡는다.
    """

    if not 1 <= maximum_results <= 10:
        raise ValueError("maximum_results는 1~10이어야 합니다.")
    web = _request_web_detection(image_bytes)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(
        *,
        page_url: str | None,
        media_url: str | None,
        match_type: str,
        page_title: str | None = None,
    ) -> None:
        page = (page_url or media_url or "").strip()
        media = (media_url or "").strip()
        if not page.startswith(("http://", "https://")):
            return
        if media and not media.startswith(("http://", "https://")):
            media = ""
        # 같은 이미지가 페이지별 목록과 전역 목록에 중복 등장해도 한 번만 분석한다.
        key = media or page
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "page_url": page,
                "media_url": media or None,
                "thumbnail_url": media or None,
                "provider": "google_vision_web_detection",
                "match_type": match_type,
                "page_title": page_title,
            }
        )

    # 게시 페이지가 있는 후보를 우선한다. 신고자료에 원문 URL을 남길 수 있기 때문이다.
    pages = web.get("pagesWithMatchingImages", [])
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_url = page.get("url")
            title = page.get("pageTitle")
            for item in page.get("fullMatchingImages", []) or []:
                if isinstance(item, dict):
                    add_candidate(
                        page_url=page_url,
                        media_url=item.get("url"),
                        match_type="full_match",
                        page_title=title,
                    )
            for item in page.get("partialMatchingImages", []) or []:
                if isinstance(item, dict):
                    add_candidate(
                        page_url=page_url,
                        media_url=item.get("url"),
                        match_type="partial_match",
                        page_title=title,
                    )

    for field, match_type in (
        ("fullMatchingImages", "full_match"),
        ("partialMatchingImages", "partial_match"),
        ("visuallySimilarImages", "visually_similar"),
    ):
        items = web.get(field, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                media_url = item.get("url")
                add_candidate(
                    page_url=media_url,
                    media_url=media_url,
                    match_type=match_type,
                )

    best_guess_labels = [
        str(item.get("label"))
        for item in web.get("bestGuessLabels", [])
        if isinstance(item, dict) and item.get("label")
    ]
    raw_count = len(candidates)
    return {
        "provider": "google_vision_web_detection",
        "status": "completed",
        "raw_candidate_count": raw_count,
        "candidate_count": min(raw_count, maximum_results),
        "truncated_count": max(0, raw_count - maximum_results),
        "best_guess_labels": best_guess_labels,
        "candidates": candidates[:maximum_results],
    }
