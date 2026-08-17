"""Google Cloud Vision Web Detection 기반 공개 후보 수집기.

새 얼굴가드 API는 Vision이 찾은 URL을 ArcFace와 ONNX 모델 API에 전달한다.
기존 클라이언트 호환 경로의 pHash 검증 함수도 당분간 함께 유지한다.
"""

import base64
import io
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urljoin, urlparse

import imagehash
import requests
from PIL import Image

logger = logging.getLogger("deepsogak")

VISION_ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"
FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeepSogak/1.0"}
VERIFY_TIMEOUT = 5
VERIFY_MAX_BYTES = 5 * 1024 * 1024
VERIFY_WORKERS = 8
WEB_RESULT_LIMIT = 20
SIMILARITY_THRESHOLD = 60  # 기획서상 ArcFace 코사인 유사도 0.6 기준과 동일한 취지의 컷오프

SNS_DOMAINS = ("instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com", "threads.net")

_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:image["\']',
    re.IGNORECASE,
)
_IMG_TAG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


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


def _phash_similarity(query_hash: imagehash.ImageHash, candidate_image: Image.Image) -> float:
    diff = query_hash - imagehash.phash(candidate_image)  # 0~64 해밍 거리
    return round(max(0.0, 100 - diff * (100 / 64)), 1)


def _download_image(url: str) -> Image.Image | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        p = urlparse(url)
        headers = {**FETCH_HEADERS, "Referer": f"{p.scheme}://{p.netloc}/"}
        resp = requests.get(url, headers=headers, timeout=VERIFY_TIMEOUT, stream=True)
        resp.raise_for_status()
        data = resp.raw.read(VERIFY_MAX_BYTES + 1, decode_content=True)
        if len(data) > VERIFY_MAX_BYTES:
            return None
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")
    except Exception:
        return None


def _extract_page_image_urls(page_url: str) -> list[str]:
    try:
        resp = requests.get(page_url, headers=FETCH_HEADERS, timeout=8, stream=True)
        resp.raise_for_status()
        if "text/html" not in resp.headers.get("content-type", ""):
            return []
        html = resp.raw.read(2 * 1024 * 1024, decode_content=True).decode(
            resp.encoding or "utf-8", errors="ignore"
        )
    except Exception:
        return []
    raw_urls = [a or b for a, b in _OG_IMAGE_RE.findall(html)]
    raw_urls.extend(_IMG_TAG_RE.findall(html))
    out, seen = [], set()
    for u in raw_urls:
        full = urljoin(page_url, u.strip())
        if full.startswith(("http://", "https://")) and full not in seen:
            seen.add(full)
            out.append(full)
        if len(out) >= 4:
            break
    return out


def _verify_candidate(query_hash: imagehash.ImageHash, cand: dict) -> float | None:
    """후보를 실측 검증해 pHash 기반 유사도(0~100)를 반환한다. 실패 시 None."""
    if cand.get("image_url"):
        img = _download_image(cand["image_url"])
        if img is not None:
            return _phash_similarity(query_hash, img)
    if cand.get("source_url"):
        for img_url in _extract_page_image_urls(cand["source_url"]):
            img = _download_image(img_url)
            if img is not None:
                sim = _phash_similarity(query_hash, img)
                if sim >= SIMILARITY_THRESHOLD:
                    return sim
    return None


def _classify_source(url: str | None) -> str:
    if not url:
        return "기타 웹사이트"
    domain = urlparse(url).netloc.lower()
    if any(sns in domain for sns in SNS_DOMAINS):
        return "공개 SNS"
    return "검색엔진"


def scan_web(image_bytes: bytes, query_hash: imagehash.ImageHash) -> list[dict] | None:
    """Vision Web Detection + pHash 실측 검증. API 키가 없거나 호출 실패 시 None
    (호출자가 시뮬레이션 데이터로 폴백)."""
    try:
        web = _request_web_detection(image_bytes)
    except VisionScanError as error:
        logger.warning("Vision API 호출 실패, 시뮬레이션 데이터로 폴백: %s", error.code)
        return None

    candidates: list[dict] = []
    seen: set[str] = set()

    def _add(key, title, image_url, source_url):
        if not key or key in seen:
            return
        seen.add(key)
        candidates.append({"title": title, "image_url": image_url, "source_url": source_url})

    for page in web.get("pagesWithMatchingImages", []):
        page_url = page.get("url")
        thumb = (page.get("fullMatchingImages") or page.get("partialMatchingImages") or [{}])[0].get("url")
        _add(page_url, page.get("pageTitle") or page_url, thumb, page_url)
    for img in web.get("fullMatchingImages", []):
        _add(img.get("url"), "게시 페이지 미확인 (동일 이미지)", img.get("url"), None)
    for img in web.get("visuallySimilarImages", []):
        _add(img.get("url"), "게시 페이지 미확인 (유사 이미지)", img.get("url"), None)

    with ThreadPoolExecutor(max_workers=VERIFY_WORKERS) as pool:
        similarities = list(pool.map(lambda c: _verify_candidate(query_hash, c), candidates))

    matches = []
    for cand, sim in zip(candidates, similarities):
        if sim is None or sim < SIMILARITY_THRESHOLD:
            continue
        matches.append(
            {
                "title": cand["title"],
                "source_url": cand["source_url"],
                "image_url": cand["image_url"],
                "similarity": sim,
                "source_type": _classify_source(cand["source_url"] or cand["image_url"]),
            }
        )

    matches.sort(key=lambda m: -m["similarity"])
    return matches[:WEB_RESULT_LIMIT]
