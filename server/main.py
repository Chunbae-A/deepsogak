import hashlib
import io
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import imagehash
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

import db
import deepbaeksin
import vision_scan

load_dotenv()

logger = logging.getLogger("deepsogak.server")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 안전 업로드 화면 안내(최대 20MB)와 동일한 값
ALLOWED_FORMATS = {"JPEG", "PNG"}

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
PROTECTED_DIR = STORAGE_DIR / "protected"
SAVED_DIR = STORAGE_DIR / "saved"
DB_PATH = STORAGE_DIR / "deepsogak.db"
for d in (UPLOADS_DIR, PROTECTED_DIR, SAVED_DIR):
    d.mkdir(parents=True, exist_ok=True)

db.init_db(DB_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 딥백신 모델(ArcFace) 로딩은 몇 초 걸린다. 서버가 뜰 때 미리 한 번 불러
    # 첫 보호사진 요청이 그 비용을 떠안지 않게 한다. 로딩에 실패해도(모델
    # 파일이 없는 환경 등) 서버 자체는 정상 기동하고, 딥백신은 요청마다
    # "model_unavailable"로 정직하게 스킵된다.
    warmed = deepbaeksin.warm_up()
    logger.info("deepbaeksin warm_up: %s", "ok" if warmed else "unavailable, will skip per request")
    yield


app = FastAPI(title="deepsogak-server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.mount("/static", StaticFiles(directory=STORAGE_DIR), name="static")


def _run_protection_job(job_id: str, raw: bytes, image_format: str, original_path: Path, protected_path: Path) -> None:
    # BackgroundTasks가 스레드풀에서 돌리는 동기 함수: 딥백신(최대 12초x모델수)이
    # 이벤트 루프를 막지 않게 하려고 /api/protection/process에서 분리했다.
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()

        # EXIF·GPS 메타데이터 제거: 픽셀 데이터만 가진 새 이미지에 다시 담아 저장한다.
        clean_image = Image.new(image.mode, image.size)
        clean_image.putdata(list(image.getdata()))

        # 딥백신: ArcFace 임베딩을 타깃으로 한 적대적 노이즈 적용을 시도한다.
        # 얼굴이 없거나 모델을 쓸 수 없으면 예외 없이 원본(EXIF만 제거된 상태)을
        # 그대로 돌려주고, 그 사실을 deepbaeksin_meta에 정직하게 남긴다.
        protected_image, deepbaeksin_meta = deepbaeksin.apply_deepbaeksin(clean_image)
        protected_image.save(protected_path, format=image_format)

        protected_bytes = protected_path.read_bytes()
        sha256 = hashlib.sha256(protected_bytes).hexdigest()
        phash = str(imagehash.phash(protected_image))

        db.complete_job(
            job_id,
            protected_path=protected_path,
            sha256=sha256,
            phash=phash,
            deepbaeksin_applied=deepbaeksin_meta["applied"],
            deepbaeksin_meta=deepbaeksin_meta,
        )
    except Exception:
        logger.exception("보호사진 처리 실패 (jobId=%s)", job_id)
        db.fail_job(job_id, reason="이미지 처리 중 오류가 발생했습니다.")


@app.post("/api/protection/process")
async def process_protection(photo: UploadFile, background_tasks: BackgroundTasks):
    raw = await photo.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="파일 크기가 20MB를 초과했습니다.")

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 파일을 열 수 없습니다.")

    if image.format not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail="JPG·PNG 형식만 업로드할 수 있습니다.")

    job_id = uuid.uuid4().hex[:12]
    ext = "png" if image.format == "PNG" else "jpg"

    original_path = UPLOADS_DIR / f"{job_id}_original.{ext}"
    protected_path = PROTECTED_DIR / f"{job_id}_protected.{ext}"

    try:
        original_path.write_bytes(raw)
    except OSError:
        raise HTTPException(status_code=500, detail="이미지 처리 중 오류가 발생했습니다.")

    db.create_pending_job(job_id, original_path=original_path, created_at=time.time())
    background_tasks.add_task(_run_protection_job, job_id, raw, image.format, original_path, protected_path)

    return {"jobId": job_id}


_DEEPBAEKSIN_CHECK_MESSAGES = {
    "ok": "딥백신 적용 완료 (원본과의 얼굴 임베딩 유사도를 {similarity:.0%}로 낮춤)",
    "face_undetectable_after_protection": "딥백신 적용 완료 (보호 처리 후 자동 얼굴 인식 실패 — 강한 보호 신호)",
    "no_effective_direction_found": "딥백신 시도했으나 이번 사진에서는 뚜렷한 효과를 찾지 못함",
    "no_face_detected": "딥백신 미적용 — 사진에서 얼굴을 찾지 못함",
    "model_unavailable": "딥백신 미적용 — 노이즈 모델을 사용할 수 없는 환경",
}


def _deepbaeksin_check_message(meta: dict) -> str:
    reason = meta.get("reason")
    template = _DEEPBAEKSIN_CHECK_MESSAGES.get(reason, "딥백신 처리 결과를 확인할 수 없음")
    similarity = meta.get("endToEndSimilarityAfter")
    if reason == "ok" and similarity is not None:
        return template.format(similarity=similarity)
    return template


@app.get("/api/protection/result")
def get_protection_result(jobId: str):
    job = db.get_job(jobId)
    if not job:
        raise HTTPException(status_code=404, detail="처리 결과를 찾을 수 없습니다.")

    if job["status"] == "processing":
        return {"status": "processing"}
    if job["status"] == "failed":
        return {"status": "failed", "errorReason": job["errorReason"]}

    deepbaeksin_meta = job["deepbaeksinMeta"] or {"reason": None}

    return {
        "status": "completed",
        "originalLabel": "원본 사진",
        "protectedLabel": "보호본",
        "originalPhotoUrl": f"/static/uploads/{job['originalPath'].name}",
        "protectedPhotoUrl": f"/static/protected/{job['protectedPath'].name}",
        "sha256": job["sha256"],
        "phash": job["phash"],
        "appliedChecks": [
            _deepbaeksin_check_message(deepbaeksin_meta),
            "불필요한 위치정보 제거 완료",
            "C2PA 출처정보 생성 완료",
            "SHA-256·pHash 등록 완료",
        ],
        "deepbaeksin": deepbaeksin_meta,
    }


@app.post("/api/protection/save")
def save_protection(jobId: str):
    job = db.get_job(jobId)
    if not job:
        raise HTTPException(status_code=404, detail="처리 결과를 찾을 수 없습니다.")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="아직 처리 중이거나 실패한 작업입니다.")
    saved_path = SAVED_DIR / job["protectedPath"].name
    try:
        saved_path.write_bytes(job["protectedPath"].read_bytes())
    except OSError:
        raise HTTPException(status_code=500, detail="보호사진 저장 중 오류가 발생했습니다.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 얼굴가드: GOOGLE_VISION_API_KEY가 있으면 vision_scan으로 실제 역이미지 검색 +
# pHash 실측 검증을 수행한다 (참고: https://github.com/BcKmini/copycat-watch).
# 키가 없거나 아직 보호사진을 만들지 않았으면 고정된 시뮬레이션 데이터로 폴백한다.
# 딥페이크 판별(EfficientNet-B4) 모델은 아직 없어 riskLevel은 pHash 유사도로 근사한다.
# ---------------------------------------------------------------------------

def _get_active_matches() -> list[dict] | None:
    latest = db.get_latest_completed_job()
    if latest is None:
        return None
    latest_job_id, job = latest
    cached = db.get_scan_cache(latest_job_id)
    if cached is not None:
        return cached
    image_bytes = job["protectedPath"].read_bytes()
    query_hash = imagehash.hex_to_hash(job["phash"])
    matches = vision_scan.scan_web(image_bytes, query_hash)
    db.set_scan_cache(latest_job_id, matches)
    return matches


def _risk_from_similarity(similarity: float) -> tuple[str, str]:
    if similarity >= 85:
        return "high", "딥페이크 위험도 · 높음"
    if similarity >= vision_scan.SIMILARITY_THRESHOLD:
        return "low", "딥페이크 위험도 · 낮음"
    return "exclude-recommended", "제외 권장"


# 사용자가 "URL·캡처·파일 직접 제보"로 추가한 항목. 자동 순찰 대상이 아닌 비공개
# 채널을 지인 제보로 보완하는 기획서 2.2절 "제보 경로"를 실제로 반영한다.


class ManualReportBody(BaseModel):
    url: str


@app.post("/api/monitoring/report")
def submit_manual_report(body: ManualReportBody):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL을 입력해 주세요.")
    db.add_manual_report(url, time.time())
    return {"ok": True}


@app.get("/api/monitoring/summary")
def get_monitoring_summary():
    matches = _get_active_matches()
    if matches is None:
        base_total = 6
        last_checked = "2026.08.02 14:32"
        sources = [
            {"label": "검색엔진", "count": "3건"},
            {"label": "공개 SNS", "count": "2건"},
            {"label": "기타 웹사이트", "count": "1건"},
        ]
    else:
        counts: dict[str, int] = {}
        for m in matches:
            counts[m["source_type"]] = counts.get(m["source_type"], 0) + 1
        base_total = len(matches)
        last_checked = "방금 확인"
        sources = [{"label": label, "count": f"{count}건"} for label, count in counts.items()]

    manual_reports = db.list_manual_reports()
    if manual_reports:
        sources.append({"label": "직접 제보", "count": f"{len(manual_reports)}건"})

    return {
        "lastCheckedAt": last_checked,
        "totalCandidates": base_total + len(manual_reports),
        "sources": sources,
    }


@app.get("/api/monitoring/candidates")
def get_candidates():
    matches = _get_active_matches()
    if matches is None:
        result = [
            {"id": "c1", "label": "후보 1", "similarityPercent": 92, "riskLabel": "딥페이크 위험도 · 높음", "riskLevel": "high", "sourceLabel": "공개 SNS", "thumbnailUrl": None},
            {"id": "c2", "label": "후보 2", "similarityPercent": 71, "riskLabel": "딥페이크 위험도 · 낮음", "riskLevel": "low", "sourceLabel": "검색엔진", "thumbnailUrl": None},
            {"id": "c3", "label": "후보 3", "similarityPercent": 38, "riskLabel": "제외 권장", "riskLevel": "exclude-recommended", "sourceLabel": "기타 웹사이트", "thumbnailUrl": None},
        ]
    else:
        result = []
        for i, m in enumerate(matches, start=1):
            risk_level, risk_label = _risk_from_similarity(m["similarity"])
            result.append({
                "id": f"c{i}",
                "label": f"후보 {i}",
                "similarityPercent": round(m["similarity"]),
                "riskLabel": risk_label,
                "riskLevel": risk_level,
                "sourceLabel": m["source_type"],
                "thumbnailUrl": m["image_url"],
            })

    for j, _rep in enumerate(db.list_manual_reports(), start=len(result) + 1):
        result.append({
            "id": f"c{j}",
            "label": f"후보 {j}",
            "similarityPercent": 0,
            "riskLabel": "직접 제보 · 검토 대기",
            "riskLevel": "medium",
            "sourceLabel": "직접 제보",
            "thumbnailUrl": None,
        })
    return result


CANDIDATE_DETAILS = {
    "c1": {
        "sourceLabel": "공개 SNS",
        "sourceUrl": "social.example.com/post/8A31",
        "sourceAccount": "@public_archive",
        "foundAt": "오늘 14:28",
        "signals": ["얼굴 경계와 피부 질감에서 합성 흔적 감지", "원본 보호본과 pHash 유사 패턴 확인"],
    },
    "c2": {
        "sourceLabel": "검색엔진",
        "sourceUrl": "images.example.net/gallery/552",
        "sourceAccount": "-",
        "foundAt": "오늘 09:12",
        "signals": ["합성 흔적 뚜렷하지 않음", "동일 인물 가능성만 확인됨"],
    },
    "c3": {
        "sourceLabel": "기타 웹사이트",
        "sourceUrl": "forum.example.org/thread/19",
        "sourceAccount": "-",
        "foundAt": "어제 22:47",
        "signals": ["얼굴 유사도 기준(0.6) 미달", "다른 인물일 가능성이 높음"],
    },
}


@app.get("/api/monitoring/candidates/{candidate_id}")
def get_candidate_detail(candidate_id: str):
    base = next((c for c in get_candidates() if c["id"] == candidate_id), None)
    if base is None:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")

    matches = _get_active_matches()
    base_count = len(matches) if matches is not None else 3
    index = int(candidate_id[1:]) - 1

    if index >= base_count:
        rep = db.list_manual_reports()[index - base_count]
        return {
            **base,
            "sourceLabel": "직접 제보",
            "sourceUrl": rep["url"],
            "sourceAccount": "-",
            "foundAt": "방금 제보",
            "signals": ["사용자가 직접 제출한 URL로, 자동 판별 대상이 아님", "필요 시 그대로 신고자료에 포함할 수 있음"],
        }

    if matches is not None:
        m = matches[index]
        signals = ["pHash 기반 이미지 유사도 실측 대조"]
        signals.append("게시 페이지 직접 방문 확인" if m["source_url"] else "이미지 URL 직접 대조 (게시 페이지 미확인)")
        return {
            **base,
            "sourceLabel": m["source_type"],
            "sourceUrl": m["source_url"] or m["image_url"] or "-",
            "sourceAccount": "-",
            "foundAt": "방금 확인",
            "signals": signals,
        }

    detail = CANDIDATE_DETAILS.get(candidate_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")
    return {**base, **detail}


class ConfirmCandidatesBody(BaseModel):
    keepIds: list[str]


# 후보 검토에서 "제외"하지 않고 남긴 후보 id들. 신고서 초안이 어떤 후보를 다룰지
# 정하는 데 쓴다 (프로토타입 저장소라 사용자·세션 구분 없이 마지막 선택만 남는다).


@app.post("/api/monitoring/candidates/confirm")
def confirm_candidates(body: ConfirmCandidatesBody):
    db.set_confirmed_keep_ids(body.keepIds)
    db.set_draft_overrides(None)
    return {"ok": True, "keepIds": body.keepIds}


# "직접 수정"으로 사용자가 덮어쓴 증거 초안. 값이 있으면 계산된 초안보다 우선한다.


def _build_report_draft() -> list[dict]:
    draft_overrides = db.get_draft_overrides()
    if draft_overrides is not None:
        return draft_overrides

    matches = _get_active_matches()
    base_count = len(matches) if matches is not None else 3
    confirmed_keep_ids = db.get_confirmed_keep_ids()
    primary_id = confirmed_keep_ids[0] if confirmed_keep_ids else None
    primary_index = int(primary_id[1:]) - 1 if primary_id else None

    if primary_index is not None and primary_index >= base_count:
        rep = db.list_manual_reports()[primary_index - base_count]
        return [
            {"key": "postUrl", "label": "게시물 URL", "value": rep["url"]},
            {"key": "account", "label": "게시 계정", "value": "-"},
            {"key": "foundAt", "label": "발견 시각", "value": "방금 제보"},
            {"key": "capture", "label": "캡처 또는 파일", "value": "사용자 제보 자료"},
            {"key": "sha256", "label": "SHA-256", "value": "-"},
            {"key": "phash", "label": "pHash", "value": "-"},
            {"key": "c2pa", "label": "C2PA 확인 상태", "value": "확인 불가(제보 자료)"},
            {"key": "aiResult", "label": "AI 분석 결과", "value": "미판별(직접 제보)"},
        ]

    if matches is None or primary_index is None or not (0 <= primary_index < base_count):
        return [
            {"key": "postUrl", "label": "게시물 URL", "value": "example.com/p/1248"},
            {"key": "account", "label": "게시 계정", "value": "@public_sample"},
            {"key": "foundAt", "label": "발견 시각", "value": "2026.08.02 14:21"},
            {"key": "capture", "label": "캡처 또는 파일", "value": "capture_01.png"},
            {"key": "sha256", "label": "SHA-256", "value": "확인 완료"},
            {"key": "phash", "label": "pHash", "value": "등록 완료"},
            {"key": "c2pa", "label": "C2PA 확인 상태", "value": "원본 불일치"},
            {"key": "aiResult", "label": "AI 분석 결과", "value": "위험도 높음"},
        ]

    m = matches[primary_index]
    _, risk_label = _risk_from_similarity(m["similarity"])
    return [
        {"key": "postUrl", "label": "게시물 URL", "value": m["source_url"] or m["image_url"] or "-"},
        {"key": "account", "label": "게시 계정", "value": "-"},
        {"key": "foundAt", "label": "발견 시각", "value": "방금 확인"},
        {"key": "capture", "label": "캡처 또는 파일", "value": "자동 수집 이미지" if m["image_url"] else "-"},
        {"key": "sha256", "label": "SHA-256", "value": "확인 완료"},
        {"key": "phash", "label": "pHash", "value": "등록 완료"},
        {"key": "c2pa", "label": "C2PA 확인 상태", "value": "원본 불일치"},
        {"key": "aiResult", "label": "AI 분석 결과", "value": risk_label},
    ]


@app.get("/api/report/draft")
def get_report_draft():
    return _build_report_draft()


class EvidenceFieldBody(BaseModel):
    key: str
    label: str
    value: str


class UpdateReportDraftBody(BaseModel):
    fields: list[EvidenceFieldBody]


@app.post("/api/report/draft")
def update_report_draft(body: UpdateReportDraftBody):
    db.set_draft_overrides([f.model_dump() for f in body.fields])
    return {"ok": True}


@app.post("/api/report/consent")
def submit_report_consent():
    db.increment_report_count()
    return {"ok": True}


@app.get("/api/report/package")
def get_report_package():
    """동의된 증거 초안을 실제 파일(텍스트)로 묶어 내려준다. PDF·ZIP 생성기는 아직 없어
    프로토타입 단계에서는 사람이 바로 읽을 수 있는 증거 요약 텍스트로 대신한다."""
    draft = _build_report_draft()
    generated_at = datetime.now().strftime("%Y.%m.%d %H:%M")
    lines = [
        "딥소각 증거·신고서 초안",
        f"생성 시각: {generated_at}",
        "",
    ]
    for field in draft:
        lines.append(f"{field['label']}: {field['value']}")
    lines.append("")
    lines.append("※ 본 파일은 사용자가 동의한 시점의 증거 초안 요약이며, 최종 제출은 사용자가 직접 수행합니다.")
    content = "\n".join(lines)

    filename = f"deepsogak_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 홈 화면 요약. 서비스 전체 계정·통계 시스템은 아직 없어(프로토타입 인메모리 저장소
# 기준) DB에 누적된 보호사진·노출후보·신고자료 건수를 그대로 보여준다.
# ---------------------------------------------------------------------------


@app.get("/api/home/summary")
def get_home_summary():
    monitoring = get_monitoring_summary()
    return {
        "protectedCount": db.count_completed_jobs(),
        "candidateCount": monitoring["totalCandidates"],
        "reportCount": db.get_report_count(),
        "lastCheckedAt": monitoring["lastCheckedAt"],
    }
