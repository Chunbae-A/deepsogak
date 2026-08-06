"""역이미지 검색 파이프라인 (참고: https://github.com/BcKmini/copycat-watch).

1) Google Cloud Vision Web Detection으로 공개 웹에서 후보 페이지/이미지를 수집
2) 각 후보 이미지를 서버가 직접 내려받아 pHash로 실측 검증 — Vision이 "비슷하다"고
   준 후보 중 실제로 등록 사진과 가까운 것만 골라낸다 (허위 후보 제거)

EfficientNet-B4 딥페이크 판별 모델은 아직 없어 riskLevel은 이 pHash 유사도로만
근사한다 — 실제 모델이 붙으면 이 시뮬레이션을 대체하면 된다.
"""

import base64
import io
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import imagehash
import requests
from PIL import Image

logger = logging.getLogger("deepsogak")

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
    api_key = os.environ.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
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
        resp.raise_for_status()
        web = resp.json()["responses"][0].get("webDetection", {})
    except Exception as e:
        logger.warning("Vision API 호출 실패, 시뮬레이션 데이터로 폴백: %s", e)
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
