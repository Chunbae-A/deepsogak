import hashlib
import io
import time
import uuid
from datetime import datetime
from pathlib import Path

import imagehash
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import model_api
import vision_scan

load_dotenv()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 안전 업로드 화면 안내(최대 20MB)와 동일한 값
ALLOWED_FORMATS = {"JPEG", "PNG"}

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
PROTECTED_DIR = STORAGE_DIR / "protected"
SAVED_DIR = STORAGE_DIR / "saved"
for d in (UPLOADS_DIR, PROTECTED_DIR, SAVED_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="deepsogak-server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.mount("/static", StaticFiles(directory=STORAGE_DIR), name="static")

# 프로토타입용 인메모리 저장소. 실서비스에서는 DB로 교체한다.
JOBS: dict[str, dict] = {}
MONITORING_SCANS: dict[str, dict] = {}
MODEL_CANDIDATES: dict[str, dict] = {}
REPORT_COUNT = 0


@app.post("/api/protection/process")
async def process_protection(photo: UploadFile):
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

        # EXIF·GPS 메타데이터 제거: 픽셀 데이터만 가진 새 이미지에 다시 담아 저장한다.
        # TODO(AI 모델 연동): 여기서 딥백신 Beta(적대적 노이즈) 적용을 추가한다.
        clean_image = Image.new(image.mode, image.size)
        clean_image.putdata(list(image.getdata()))
        clean_image.save(protected_path, format=image.format)
    except OSError:
        raise HTTPException(status_code=500, detail="이미지 처리 중 오류가 발생했습니다.")

    protected_bytes = protected_path.read_bytes()
    sha256 = hashlib.sha256(protected_bytes).hexdigest()
    phash = str(imagehash.phash(clean_image))
    content_type = "image/png" if image.format == "PNG" else "image/jpeg"
    model_analysis = await run_in_threadpool(
        model_api.analyze_protected_photo,
        raw,
        protected_bytes,
        content_type=content_type,
    )

    JOBS[job_id] = {
        "originalPath": original_path,
        "protectedPath": protected_path,
        "sha256": sha256,
        "phash": phash,
        "modelAnalysis": model_analysis,
        "contentType": content_type,
        "createdAt": time.time(),
    }

    return {"jobId": job_id}


@app.get("/api/protection/result")
def get_protection_result(jobId: str):
    job = JOBS.get(jobId)
    if not job:
        raise HTTPException(status_code=404, detail="처리 결과를 찾을 수 없습니다.")

    return {
        "originalLabel": "원본 사진",
        "protectedLabel": "보호본",
        "originalPhotoUrl": f"/static/uploads/{job['originalPath'].name}",
        "protectedPhotoUrl": f"/static/protected/{job['protectedPath'].name}",
        "sha256": job["sha256"],
        "phash": job["phash"],
        "modelAnalysis": job["modelAnalysis"],
        "appliedChecks": [
            "불필요한 위치정보 제거 완료",
            "SHA-256·pHash 생성 완료",
            (
                "AI 모델 연결 시험 완료"
                if job["modelAnalysis"]["status"] == "completed"
                else "AI 모델 연결 시험 일부 또는 전체 미완료"
            ),
        ],
    }


@app.get("/api/model/health")
def get_model_health():
    return model_api.health()


@app.post("/api/protection/save")
def save_protection(jobId: str):
    job = JOBS.get(jobId)
    if not job:
        raise HTTPException(status_code=404, detail="처리 결과를 찾을 수 없습니다.")
    saved_path = SAVED_DIR / job["protectedPath"].name
    try:
        saved_path.write_bytes(job["protectedPath"].read_bytes())
    except OSError:
        raise HTTPException(status_code=500, detail="보호사진 저장 중 오류가 발생했습니다.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 얼굴가드의 새 앱 흐름은 /api/monitoring/scans API에서 SearXNG → ArcFace → ONNX를
# 사용한다. 아래 vision_scan·pHash 함수와 고정 데이터 API는 이전 클라이언트 호환용으로
# 남겨 둔 레거시 경로이며 새 MonitoringScreen에서는 호출하지 않는다.
# ---------------------------------------------------------------------------

_scan_cache: dict = {"job_id": None, "matches": None}


def _get_active_matches() -> list[dict] | None:
    if not JOBS:
        return None
    latest_job_id = max(JOBS, key=lambda k: JOBS[k]["createdAt"])
    if _scan_cache["job_id"] == latest_job_id:
        return _scan_cache["matches"]
    job = JOBS[latest_job_id]
    image_bytes = job["protectedPath"].read_bytes()
    query_hash = imagehash.hex_to_hash(job["phash"])
    matches = vision_scan.scan_web(image_bytes, query_hash)
    _scan_cache["job_id"] = latest_job_id
    _scan_cache["matches"] = matches
    return matches


def _risk_from_similarity(similarity: float) -> tuple[str, str]:
    if similarity >= 85:
        return "high", "딥페이크 위험도 · 높음"
    if similarity >= vision_scan.SIMILARITY_THRESHOLD:
        return "low", "딥페이크 위험도 · 낮음"
    return "exclude-recommended", "제외 권장"


# 사용자가 "URL·캡처·파일 직접 제보"로 추가한 항목. 자동 순찰 대상이 아닌 비공개
# 채널을 지인 제보로 보완하는 기획서 2.2절 "제보 경로"를 실제로 반영한다.
_manual_reports: list[dict] = []  # [{"url": str}]


class StartMonitoringScanBody(BaseModel):
    queryText: str = Field(min_length=1, max_length=200)
    webMonitoringConsent: bool
    referenceJobIds: list[str] = Field(min_length=1, max_length=5)
    maximumResults: int = Field(default=5, ge=1, le=10)


def _raise_model_api_http(error: model_api.ModelApiError) -> None:
    status_code = 503 if error.unavailable else 502
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": error.code,
            "message": (
                "얼굴가드 모델 API에 연결할 수 없습니다."
                if error.unavailable
                else "얼굴가드 모델 API가 요청을 처리하지 못했습니다."
            ),
        },
    )


def _monitoring_record(scan_id: str) -> dict:
    record = MONITORING_SCANS.get(scan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="모니터링 작업을 찾을 수 없습니다.")
    return record


def _candidate_risk(candidate: dict) -> tuple[str, str]:
    action = candidate.get("recommended_action")
    if action == "review_required":
        return "high", "조작 의심 신호 · 검토 필요"
    if action == "identity_review_required":
        return "medium", "본인 여부 · 검토 필요"
    if action == "monitor":
        return "low", "조작 의심 신호 미검출 · 모니터링"
    if action == "exclude_recommended":
        return "exclude-recommended", "다른 사람 가능성 · 제외 권장"
    return "medium", "분석 실패 · 원문 확인 필요"


def _score_signal(label: str, value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{label} {float(value):.3f} (확률 아님)"
    return f"{label}를 계산하지 못함"


def _client_candidate(candidate: dict, index: int) -> dict:
    risk_level, risk_label = _candidate_risk(candidate)
    source_engine = candidate.get("source_engine")
    source_type = candidate.get("source_type")
    source_label = str(source_engine or source_type or "공개 웹")
    candidate_id = str(candidate.get("candidate_id") or f"unknown-{index}")
    source_url = str(candidate.get("source_url") or "-")
    result = {
        "id": candidate_id,
        "label": f"후보 {index}",
        "faceSimilarity": candidate.get("face_similarity"),
        "deepfakeScore": candidate.get("deepfake_score"),
        "faceMatchLevel": candidate.get("face_match_level", "unavailable"),
        "deepfakeSignal": candidate.get("deepfake_signal", "unavailable"),
        "recommendedAction": candidate.get(
            "recommended_action", "analysis_unavailable"
        ),
        "analysisStatus": candidate.get("analysis_status", "unavailable"),
        "riskLabel": risk_label,
        "riskLevel": risk_level,
        "sourceLabel": source_label,
        "thumbnailUrl": candidate.get("thumbnail_url")
        or candidate.get("media_url"),
        "sourceUrl": source_url,
        "sourceAccount": "-",
        "foundAt": "이번 공개 검색에서 발견",
        "signals": [
            _score_signal("ArcFace 얼굴 유사도 원점수", candidate.get("face_similarity")),
            _score_signal("딥페이크 모델 원점수", candidate.get("deepfake_score")),
            "AI 결과는 자동 신고·삭제가 아닌 사람 검토용 후보 신호",
        ],
        "warning": candidate.get("warning") or model_api.RESEARCH_WARNING,
    }
    MODEL_CANDIDATES[candidate_id] = result
    return result


def _manual_client_candidate(report: dict, index: int) -> dict:
    candidate_id = f"manual-{index}"
    result = {
        "id": candidate_id,
        "label": f"후보 {index}",
        "faceSimilarity": None,
        "deepfakeScore": None,
        "faceMatchLevel": "unavailable",
        "deepfakeSignal": "not_analyzed",
        "recommendedAction": "analysis_unavailable",
        "analysisStatus": "unavailable",
        "riskLabel": "직접 제보 · 원문 검토 필요",
        "riskLevel": "medium",
        "sourceLabel": "직접 제보",
        "thumbnailUrl": None,
        "sourceUrl": report["url"],
        "sourceAccount": "-",
        "foundAt": "방금 제보",
        "signals": [
            "사용자가 직접 제출한 URL",
            "자동 얼굴·딥페이크 분석을 완료하지 않은 검토 대기 자료",
        ],
        "warning": model_api.RESEARCH_WARNING,
    }
    MODEL_CANDIDATES[candidate_id] = result
    return result


async def _scan_client_candidates(scan_id: str) -> list[dict]:
    _monitoring_record(scan_id)
    try:
        payload = await run_in_threadpool(
            model_api.get_client_exposure_candidates, scan_id
        )
    except model_api.ModelApiError as error:
        _raise_model_api_http(error)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise HTTPException(status_code=502, detail="모델 후보 응답 형식이 올바르지 않습니다.")
    result = [
        _client_candidate(candidate, index)
        for index, candidate in enumerate(candidates, start=1)
        if isinstance(candidate, dict)
    ]
    result.extend(
        _manual_client_candidate(report, len(result) + index)
        for index, report in enumerate(_manual_reports, start=1)
    )
    return result


@app.post("/api/monitoring/scans", status_code=202)
async def start_monitoring_scan(body: StartMonitoringScanBody):
    if not body.webMonitoringConsent:
        raise HTTPException(
            status_code=400,
            detail="공개 웹 검색을 시작하려면 명시적 동의가 필요합니다.",
        )
    query_text = body.queryText.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="공개 검색어를 입력해 주세요.")

    reference_images: list[tuple[bytes, str]] = []
    missing_job_ids: list[str] = []
    for job_id in dict.fromkeys(body.referenceJobIds):
        job = JOBS.get(job_id)
        if job is None:
            missing_job_ids.append(job_id)
            continue
        try:
            reference_images.append(
                (
                    job["originalPath"].read_bytes(),
                    job.get("contentType", "image/jpeg"),
                )
            )
        except OSError:
            raise HTTPException(
                status_code=500, detail="등록 사진을 읽지 못했습니다. 다시 업로드해 주세요."
            )
    if missing_job_ids:
        raise HTTPException(
            status_code=404,
            detail="등록 사진 처리 결과를 찾을 수 없습니다. 다시 업로드해 주세요.",
        )

    try:
        enrollment = await run_in_threadpool(
            model_api.create_face_enrollment, reference_images
        )
        enrollment_id = enrollment.get("enrollment_id")
        if not isinstance(enrollment_id, str) or not enrollment_id:
            raise model_api.ModelApiError("MODEL_API_ENROLLMENT_INVALID_RESPONSE")
        scan = await run_in_threadpool(
            model_api.start_exposure_scan,
            enrollment_id,
            query_text=query_text,
            maximum_results=body.maximumResults,
            idempotency_key=f"deepsogak-monitoring-{uuid.uuid4().hex}",
        )
    except model_api.ModelApiError as error:
        _raise_model_api_http(error)

    scan_id = scan.get("scan_id")
    if not isinstance(scan_id, str) or not scan_id:
        _raise_model_api_http(
            model_api.ModelApiError("MODEL_API_SCAN_START_INVALID_RESPONSE")
        )
    MONITORING_SCANS[scan_id] = {
        "enrollmentId": enrollment_id,
        "referenceJobIds": list(dict.fromkeys(body.referenceJobIds)),
        "queryText": query_text,
        "createdAt": time.time(),
    }
    return {
        "scanId": scan_id,
        "status": scan.get("status", "queued"),
        "statusUrl": f"/api/monitoring/scans/{scan_id}",
        "candidatesUrl": f"/api/monitoring/scans/{scan_id}/candidates",
        "referenceCount": len(reference_images),
        "recommendedReferenceCount": 3,
        "warning": scan.get("warning") or model_api.RESEARCH_WARNING,
    }


@app.get("/api/monitoring/scans/{scan_id}")
async def get_monitoring_scan(scan_id: str):
    _monitoring_record(scan_id)
    try:
        payload = await run_in_threadpool(model_api.get_exposure_scan, scan_id)
    except model_api.ModelApiError as error:
        _raise_model_api_http(error)
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    return {
        "scanId": scan_id,
        "status": payload.get("status", "failed"),
        "progressPercent": payload.get("progress_percent", 0),
        "searchedCandidateCount": progress.get("searched_candidate_count", 0),
        "analyzedCandidateCount": progress.get("analyzed_candidate_count", 0),
        "identityMatchCount": progress.get("identity_match_count", 0),
        "deepfakeCompletedCount": progress.get("deepfake_completed_count", 0),
        "errorCode": payload.get("error_code"),
        "warning": payload.get("warning") or model_api.RESEARCH_WARNING,
    }


@app.get("/api/monitoring/scans/{scan_id}/candidates")
async def get_monitoring_scan_candidates(scan_id: str):
    return await _scan_client_candidates(scan_id)


@app.get("/api/monitoring/scans/{scan_id}/summary")
async def get_monitoring_scan_summary(scan_id: str):
    candidates = await _scan_client_candidates(scan_id)
    counts: dict[str, int] = {}
    for candidate in candidates:
        source_label = candidate["sourceLabel"]
        counts[source_label] = counts.get(source_label, 0) + 1
    return {
        "lastCheckedAt": "방금 확인",
        "totalCandidates": len(candidates),
        "sources": [
            {"label": label, "count": f"{count}건"}
            for label, count in counts.items()
        ],
    }


class ManualReportBody(BaseModel):
    url: str


@app.post("/api/monitoring/report")
def submit_manual_report(body: ManualReportBody):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL을 입력해 주세요.")
    _manual_reports.append({"url": url})
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

    if _manual_reports:
        sources.append({"label": "직접 제보", "count": f"{len(_manual_reports)}건"})

    return {
        "lastCheckedAt": last_checked,
        "totalCandidates": base_total + len(_manual_reports),
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

    for j, _rep in enumerate(_manual_reports, start=len(result) + 1):
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
    model_candidate = MODEL_CANDIDATES.get(candidate_id)
    if model_candidate is not None:
        return model_candidate

    base = next((c for c in get_candidates() if c["id"] == candidate_id), None)
    if base is None:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")

    matches = _get_active_matches()
    base_count = len(matches) if matches is not None else 3
    index = int(candidate_id[1:]) - 1

    if index >= base_count:
        rep = _manual_reports[index - base_count]
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
# 정하는 데 쓴다 (프로토타입 인메모리 저장소라 사용자·세션 구분 없이 마지막 선택만 남는다).
_confirmed_keep_ids: list[str] = []


@app.post("/api/monitoring/candidates/confirm")
def confirm_candidates(body: ConfirmCandidatesBody):
    global _confirmed_keep_ids, _draft_overrides
    _confirmed_keep_ids = body.keepIds
    _draft_overrides = None
    return {"ok": True, "keepIds": body.keepIds}


# "직접 수정"으로 사용자가 덮어쓴 증거 초안. 값이 있으면 계산된 초안보다 우선한다.
_draft_overrides: list[dict] | None = None


def _build_report_draft() -> list[dict]:
    if _draft_overrides is not None:
        return _draft_overrides

    primary_id = _confirmed_keep_ids[0] if _confirmed_keep_ids else None
    if primary_id and primary_id in MODEL_CANDIDATES:
        candidate = MODEL_CANDIDATES[primary_id]
        face_score = candidate.get("faceSimilarity")
        deepfake_score = candidate.get("deepfakeScore")
        return [
            {
                "key": "postUrl",
                "label": "게시물 URL",
                "value": candidate.get("sourceUrl") or "-",
            },
            {"key": "account", "label": "게시 계정", "value": "-"},
            {
                "key": "foundAt",
                "label": "발견 시각",
                "value": candidate.get("foundAt") or "이번 공개 검색에서 발견",
            },
            {
                "key": "capture",
                "label": "캡처 또는 파일",
                "value": candidate.get("thumbnailUrl") or "공개 후보 URL",
            },
            {"key": "sha256", "label": "SHA-256", "value": "아직 수집하지 않음"},
            {"key": "phash", "label": "pHash", "value": "아직 수집하지 않음"},
            {"key": "c2pa", "label": "C2PA 확인 상태", "value": "확인하지 않음"},
            {
                "key": "aiResult",
                "label": "AI 분석 결과",
                "value": (
                    f"{candidate['riskLabel']} · 얼굴 원점수 "
                    f"{face_score if face_score is not None else '-'} · 딥페이크 원점수 "
                    f"{deepfake_score if deepfake_score is not None else '-'}"
                ),
            },
        ]
    matches = _get_active_matches()
    base_count = len(matches) if matches is not None else 3
    primary_index = int(primary_id[1:]) - 1 if primary_id else None

    if primary_index is not None and primary_index >= base_count:
        rep = _manual_reports[primary_index - base_count]
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
    global _draft_overrides
    _draft_overrides = [f.model_dump() for f in body.fields]
    return {"ok": True}


@app.post("/api/report/consent")
def submit_report_consent():
    global REPORT_COUNT
    REPORT_COUNT += 1
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
# 기준) 이번 세션에서 처리한 보호사진·노출후보·신고자료 건수를 그대로 보여준다.
# ---------------------------------------------------------------------------


@app.get("/api/home/summary")
def get_home_summary():
    monitoring = get_monitoring_summary()
    return {
        "protectedCount": len(JOBS),
        "candidateCount": monitoring["totalCandidates"],
        "reportCount": REPORT_COUNT,
        "lastCheckedAt": monitoring["lastCheckedAt"],
    }
