import hashlib
import io
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import imagehash
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import db
import deepbaeksin
import model_api
import vision_scan

load_dotenv()

logger = logging.getLogger("deepsogak.server")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 안전 업로드 화면 안내(최대 20MB)와 동일한 값
ALLOWED_FORMATS = {"JPEG", "PNG"}

BASE_DIR = Path(__file__).parent
# STORAGE_DIR 전체가 /static으로 그대로 서빙된다(아래 app.mount 참고). DB
# 파일을 이 트리 안에 두면 인증 없이 그대로 다운로드된다(#75) — 반드시
# 정적 서빙 경로 밖의 별도 DATA_DIR에 둔다.
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
PROTECTED_DIR = STORAGE_DIR / "protected"
SAVED_DIR = STORAGE_DIR / "saved"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "deepsogak.db"
for d in (UPLOADS_DIR, PROTECTED_DIR, SAVED_DIR, DATA_DIR):
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

# 얼굴가드 노출 스캔의 진행 상태. 프로토타입용 인메모리 저장소라 서버가
# 재시작되면 소실된다(#52 계열 후속 작업에서 DB 영속화 예정).
FACEGUARD_SCANS: dict[str, dict] = {}


# #78 스캐폴딩: "가장 최근 완료 job 이외의 파일"을 얼마나 오래 남겨둘지.
# 기본값 7일은 보수적인 시작값일 뿐 — 데모 기간(8/21까지)에는 사실상
# 영향이 없도록 일부러 넉넉하게 잡았다. 실제 서비스에서 얼마나 짧게
# 잡을지는 #78에서 논의해 정할 제품 결정이다.
JOB_FILE_RETENTION_SECONDS = float(os.environ.get("JOB_FILE_RETENTION_SECONDS", 7 * 24 * 3600))


def _prune_old_job_files(keep_job_id: str) -> None:
    """keep_job_id(방금 완료된 job) 이외의, 정리 대상 job 파일을 지운다(#78).

    DB 행(sha256/phash/생성시각 등)은 절대 지우지 않는다 — protectedCount
    같은 누적 통계가 job 행 개수에 의존하고 있어서, 행을 지우면 그 통계가
    깨진다. 여기서는 디스크의 원본·보호사진 파일만 지우고, 지운 job은
    files_pruned=1로 표시해 다음에 다시 시도하지 않게 한다.

    saved/ 폴더(사용자가 명시적으로 "저장"을 눌러 만든 사본)는 건드리지
    않는다 — 그건 자동 정리 대상이 아니라 사용자의 의도적인 보관이다.
    """
    prunable = db.list_prunable_jobs(
        exclude_job_id=keep_job_id,
        older_than_seconds=JOB_FILE_RETENTION_SECONDS,
        now=time.time(),
    )
    for job in prunable:
        for path in (job["originalPath"], job["protectedPath"]):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("job 파일 정리 실패 (jobId=%s, path=%s)", job["id"], path)
                continue
        db.mark_files_pruned(job["id"])


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
        _prune_old_job_files(keep_job_id=job_id)
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

    # TODO(#77): 클라이언트 식별자를 받게 되면 owner_id=<식별자>를 넘겨서
    # get_latest_completed_job(owner_id=...)로 사용자별로 좁힐 수 있다.
    # 지금은 owner_id를 안 넘겨(None) 기존 단일 사용자 동작을 그대로 둔다.
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
    if job["filesPruned"]:
        # #78: 이 job이 "최신"이 아니게 된 뒤 원본·보호사진 파일이 정리됐다.
        # photoUrl을 그대로 내려주면 화면에서 깨진 이미지로 보이므로, 아예
        # 별도 상태로 분기해 화면이 "만료된 결과" 안내를 보여줄 수 있게 한다.
        return {"status": "expired"}

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
    if job["filesPruned"]:
        raise HTTPException(status_code=410, detail="보호사진 파일이 정리되어 더 이상 저장할 수 없습니다.")
    saved_path = SAVED_DIR / job["protectedPath"].name
    try:
        saved_path.write_bytes(job["protectedPath"].read_bytes())
    except OSError:
        raise HTTPException(status_code=500, detail="보호사진 저장 중 오류가 발생했습니다.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 얼굴가드 모델 파이프라인(서버 전용 API)
#
# Google Vision: 공개 웹 후보 URL 수집
# ArcFace: 후보 얼굴이 등록자와 같은 사람인지 확인
# EfficientNet-B4 ONNX: 같은 사람 후보의 딥페이크 의심 원점수 계산
#
# 기존 앱 API는 변경하지 않는다. 클라이언트 연결 전 서버·모델 계약을 먼저 검증한다.
# ---------------------------------------------------------------------------


class StartFaceGuardScanBody(BaseModel):
    referenceJobIds: list[str] = Field(min_length=1, max_length=5)
    webMonitoringConsent: bool
    maximumResults: int = Field(default=10, ge=1, le=10)


def _faceguard_scan_record(scan_id: str) -> dict:
    record = FACEGUARD_SCANS.get(scan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="얼굴가드 분석 작업을 찾을 수 없습니다.")
    return record


def _raise_model_api_error(error: model_api.ModelApiError) -> None:
    raise HTTPException(
        status_code=503 if error.unavailable else 502,
        detail={
            "code": error.code,
            "message": error.message or "얼굴가드 모델 API가 요청을 처리하지 못했습니다.",
        },
    )


def _raise_vision_error(error: vision_scan.VisionScanError) -> None:
    raise HTTPException(
        status_code=503 if error.unavailable else 502,
        detail={"code": error.code, "message": error.message},
    )


def _candidate_action(result: dict) -> str:
    deepfake = result.get("deepfake")
    deepfake = deepfake if isinstance(deepfake, dict) else {}
    if result.get("identity_match") is False:
        return "exclude_recommended"
    if result.get("identity_match") is True and deepfake.get(
        "is_suspected_deepfake"
    ) is True:
        return "review_required"
    if result.get("identity_match") is True and deepfake.get("status") == "analyzed":
        return "monitor"
    return "manual_review_required"


def _candidate_url_key(value: object) -> str | None:
    """모델 API가 제거한 추적 쿼리와 무관하게 Vision 메타데이터를 다시 찾는다."""

    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", "")
    )


def _public_candidate(item: dict, record: dict) -> dict:
    if "face_match_level" in item:
        page_url = item.get("source_url")
        media_url = item.get("media_url")
        discovery_by_url = record.get("discoveryByUrl", {})
        discovery = discovery_by_url.get(
            _candidate_url_key(media_url)
        ) or discovery_by_url.get(_candidate_url_key(page_url), {})
        face_level = item.get("face_match_level")
        deepfake_signal = item.get("deepfake_signal")
        return {
            "candidateId": item.get("candidate_id"),
            "sourceUrl": page_url,
            "mediaUrl": media_url,
            "thumbnailUrl": item.get("thumbnail_url"),
            "sourceProvider": "google_vision_web_detection",
            "visionMatchType": discovery.get("match_type"),
            "faceSimilarity": item.get("face_similarity"),
            "isSamePerson": (
                True
                if face_level == "matched"
                else False
                if face_level == "not_matched"
                else None
            ),
            "faceAnalysisStatus": face_level,
            "deepfakeScore": item.get("deepfake_score"),
            "isSuspectedDeepfake": (
                True
                if deepfake_signal == "suspected"
                else False
                if deepfake_signal == "not_suspected"
                else None
            ),
            "deepfakeAnalysisStatus": deepfake_signal,
            "recommendedAction": item.get("recommended_action"),
            "errorCode": None,
            "warning": item.get("warning") or model_api.RESEARCH_WARNING,
        }

    result = item.get("result")
    result = result if isinstance(result, dict) else {}
    deepfake = result.get("deepfake")
    deepfake = deepfake if isinstance(deepfake, dict) else {}
    page_url = result.get("page_url")
    media_url = result.get("media_url")
    discovery_by_url = record.get("discoveryByUrl", {})
    discovery = discovery_by_url.get(_candidate_url_key(media_url)) or discovery_by_url.get(
        _candidate_url_key(page_url), {}
    )
    return {
        "candidateId": item.get("candidate_id"),
        "sourceUrl": page_url,
        "mediaUrl": media_url,
        "thumbnailUrl": result.get("thumbnail_url"),
        "sourceProvider": "google_vision_web_detection",
        "visionMatchType": discovery.get("match_type"),
        "faceSimilarity": result.get("similarity_raw"),
        "isSamePerson": result.get("identity_match"),
        "faceAnalysisStatus": result.get("status"),
        "deepfakeScore": deepfake.get("deepfake_score"),
        "isSuspectedDeepfake": deepfake.get("is_suspected_deepfake"),
        "deepfakeAnalysisStatus": deepfake.get("status", "not_analyzed"),
        "recommendedAction": _candidate_action(result),
        "errorCode": result.get("error_code") or deepfake.get("error_code"),
        "warning": item.get("warning") or model_api.RESEARCH_WARNING,
    }


@app.get("/api/faceguard/health")
def get_faceguard_health():
    model_health = model_api.health()
    vision_configured = bool(os.environ.get("GOOGLE_VISION_API_KEY", "").strip())
    return {
        "status": (
            "ready"
            if vision_configured
            and model_health.get("connected")
            and model_health.get("status") == "ok"
            else "not_ready"
        ),
        "googleVision": {
            "configured": vision_configured,
            "liveRequestPerformed": False,
            "role": "public_candidate_discovery",
        },
        "modelApi": model_health,
        "pipeline": [
            "google_vision_web_detection",
            "arcface_identity_filter",
            "efficientnet_b4_onnx_deepfake_analysis",
        ],
    }


@app.get("/api/faceguard/capabilities")
def get_faceguard_capabilities():
    try:
        payload = model_api.capabilities()
    except model_api.ModelApiError as error:
        _raise_model_api_error(error)
    models = payload.get("models")
    models = models if isinstance(models, list) else []
    return {
        "status": "ready" if payload.get("connected") else "not_ready",
        "apiVersion": payload.get("api_version"),
        "deploymentMode": payload.get("deployment_mode"),
        "workflows": payload.get("workflows", []),
        "models": [
            {
                "componentId": item.get("component_id"),
                "role": item.get("role"),
                "modelName": item.get("model_name"),
                "loadState": item.get("load_state"),
                "decisionStatus": item.get("decision_status"),
                "scoreSemantics": item.get("score_semantics"),
                "defaultEnabled": item.get("default_enabled"),
            }
            for item in models
            if isinstance(item, dict)
        ],
        "googleVision": {
            "configured": bool(os.environ.get("GOOGLE_VISION_API_KEY", "").strip()),
            "role": "public_candidate_discovery",
        },
        "scoresAreProbabilities": False,
        "automaticEnforcementAllowed": False,
        "originalMediaPersisted": False,
        "stateStorage": payload.get("state_storage"),
        "warning": payload.get("warning") or model_api.RESEARCH_WARNING,
    }


@app.post("/api/faceguard/scans", status_code=202)
async def start_faceguard_scan(body: StartFaceGuardScanBody):
    if not body.webMonitoringConsent:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "WEB_MONITORING_CONSENT_REQUIRED",
                "message": "사진을 Google Vision으로 전송하고 공개 웹을 검색하려면 동의가 필요합니다.",
            },
        )

    job_ids = list(dict.fromkeys(body.referenceJobIds))
    jobs: list[dict] = []
    for job_id in job_ids:
        job = db.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "REFERENCE_JOB_NOT_FOUND",
                    "message": "등록 사진 처리 결과를 찾을 수 없습니다.",
                },
            )
        if job["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REFERENCE_JOB_NOT_READY",
                    "message": "등록 사진의 딥백신 처리가 아직 끝나지 않았습니다.",
                },
            )
        jobs.append(job)

    try:
        references = [
            (
                job["originalPath"].read_bytes(),
                "image/png" if job["originalPath"].suffix.lower() == ".png" else "image/jpeg",
            )
            for job in jobs
        ]
        # 검색 제공자에는 EXIF가 제거된 보호본 한 장만 전달해 비용과 개인정보 전송을 줄인다.
        query_image = jobs[0]["protectedPath"].read_bytes()
    except (KeyError, OSError):
        raise HTTPException(
            status_code=500,
            detail={
                "code": "REFERENCE_IMAGE_READ_FAILED",
                "message": "등록 사진을 읽지 못했습니다. 다시 업로드해 주세요.",
            },
        )

    try:
        discovery = await run_in_threadpool(
            vision_scan.discover_web_candidates,
            query_image,
            maximum_results=body.maximumResults,
        )
    except vision_scan.VisionScanError as error:
        _raise_vision_error(error)

    candidates = discovery["candidates"]
    if not candidates:
        scan_id = f"vision-empty-{uuid.uuid4().hex[:12]}"
        FACEGUARD_SCANS[scan_id] = {
            "modelScanId": None,
            "status": "completed",
            "referenceJobIds": job_ids,
            "discovery": discovery,
            "discoveryByUrl": {},
            "createdAt": time.time(),
        }
        return {
            "scanId": scan_id,
            "status": "completed",
            "visionCandidateCount": 0,
            "message": "Google Vision에서 공개 후보를 찾지 못했습니다.",
            "warning": model_api.RESEARCH_WARNING,
        }

    try:
        enrollment = await run_in_threadpool(
            model_api.create_face_enrollment, references
        )
        enrollment_id = enrollment.get("enrollment_id")
        if not isinstance(enrollment_id, str) or not enrollment_id:
            raise model_api.ModelApiError("MODEL_API_ENROLLMENT_INVALID_RESPONSE")
        model_scan = await run_in_threadpool(
            model_api.start_candidate_scan,
            enrollment_id,
            candidates,
            maximum_results=body.maximumResults,
            idempotency_key=f"google-vision-{uuid.uuid4().hex}",
        )
    except model_api.ModelApiError as error:
        _raise_model_api_error(error)

    scan_id = model_scan.get("scan_id")
    if not isinstance(scan_id, str) or not scan_id:
        _raise_model_api_error(
            model_api.ModelApiError("MODEL_API_SCAN_START_INVALID_RESPONSE")
        )
    FACEGUARD_SCANS[scan_id] = {
        "modelScanId": scan_id,
        "status": model_scan.get("status", "queued"),
        "referenceJobIds": job_ids,
        "enrollmentId": enrollment_id,
        "discovery": discovery,
        "discoveryByUrl": {
            key: candidate
            for candidate in candidates
            for key in (
                _candidate_url_key(candidate.get("media_url")),
                _candidate_url_key(candidate.get("page_url")),
            )
            if key is not None
        },
        "createdAt": time.time(),
    }
    return {
        "scanId": scan_id,
        "status": model_scan.get("status", "queued"),
        "visionCandidateCount": discovery["candidate_count"],
        "visionRawCandidateCount": discovery["raw_candidate_count"],
        "referenceCount": len(references),
        "recommendedReferenceCount": 3,
        "statusUrl": f"/api/faceguard/scans/{scan_id}",
        "candidatesUrl": f"/api/faceguard/scans/{scan_id}/candidates",
        "warning": model_scan.get("warning") or model_api.RESEARCH_WARNING,
    }


@app.get("/api/faceguard/scans/{scan_id}")
async def get_faceguard_scan(scan_id: str):
    record = _faceguard_scan_record(scan_id)
    if record["modelScanId"] is None:
        return {
            "scanId": scan_id,
            "status": "completed",
            "progressPercent": 100,
            "visionCandidateCount": 0,
            "analyzedCandidateCount": 0,
        }
    try:
        payload = await run_in_threadpool(
            model_api.get_exposure_scan, record["modelScanId"]
        )
    except model_api.ModelApiError as error:
        _raise_model_api_error(error)
    progress = payload.get("progress")
    progress = progress if isinstance(progress, dict) else {}
    return {
        "scanId": scan_id,
        "status": payload.get("status", "failed"),
        "progressPercent": payload.get("progress_percent", 0),
        "visionCandidateCount": record["discovery"]["candidate_count"],
        "analyzedCandidateCount": progress.get("analyzed_candidate_count", 0),
        "identityMatchCount": progress.get("identity_match_count", 0),
        "deepfakeCompletedCount": progress.get("deepfake_completed_count", 0),
        "errorCode": payload.get("error_code"),
        "warning": payload.get("warning") or model_api.RESEARCH_WARNING,
    }


@app.get("/api/faceguard/scans/{scan_id}/candidates")
async def get_faceguard_candidates(scan_id: str):
    record = _faceguard_scan_record(scan_id)
    if record["modelScanId"] is None:
        return {
            "scanId": scan_id,
            "status": "completed",
            "candidateCount": 0,
            "candidates": [],
            "warning": model_api.RESEARCH_WARNING,
        }
    try:
        payload = await run_in_threadpool(
            model_api.get_exposure_candidates, record["modelScanId"]
        )
    except model_api.ModelApiError as error:
        _raise_model_api_error(error)
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        _raise_model_api_error(
            model_api.ModelApiError("MODEL_API_SCAN_CANDIDATES_INVALID_RESPONSE")
        )
    candidates = [
        _public_candidate(item, record)
        for item in raw_candidates
        if isinstance(item, dict)
    ]
    return {
        "scanId": scan_id,
        "status": payload.get("status", "failed"),
        "candidateCount": len(candidates),
        "candidates": candidates,
        "warning": payload.get("warning") or model_api.RESEARCH_WARNING,
    }


# ---------------------------------------------------------------------------
# 얼굴가드: 가장 최근 완료된 보호사진을 등록 사진으로 삼아 실제 얼굴가드
# 파이프라인(/api/faceguard/scans/* — Google Vision → ArcFace 동일인 판별 →
# EfficientNet-B4 딥페이크 판별)을 재사용한다(#80).
#
# 예전에는 pHash 유사도로 위험도를 근사하거나(vision_scan.scan_web, 제거됨),
# 아직 보호사진이 없으면 하드코딩된 가짜 후보 3개(CANDIDATE_DETAILS, 제거됨)를
# 보여줬다. #55에서 이미 만든 진짜 모델 파이프라인이 있는데도 화면은 그 결과를
# 전혀 쓰지 않고 있었다 — 이제는 /api/monitoring/*가 내부적으로
# /api/faceguard/scans/*를 그대로 호출해서 진짜 값을 돌려준다.
#
# referenceJobIds: 지금 앱에는 "이 사진이 내 등록 사진이다"라는 개념이 없다
# (서버 인스턴스 하나 = 사용자 한 명 전제, #77과 동일). 그래서 가장 최근
# 완료된 job을 자동으로 등록 사진으로 취급한다.
#
# 스캔은 Vision·모델 API를 오가는 비동기 작업이라 완료까지 몇 초~수십 초
# 걸릴 수 있다. 이번 변경은 앱 쪽 코드를 건드리지 않는 "서버측 브리지"라
# 폴링 UI가 없다 — 완료 전에는 status="scanning"으로 빈 후보 목록을
# 돌려주고, 다음 요청 때 완료돼 있으면 실제 후보가 채워진다(#80 후속:
# 앱이 직접 새 엔드포인트로 폴링하도록 바꾸는 건 별도 작업).
# ---------------------------------------------------------------------------

MONITORING_SCAN_BY_JOB: dict[str, str] = {}


async def _get_active_scan() -> dict | None:
    """가장 최근 완료된 job에 대한 얼굴가드 스캔 상태를 얻는다.

    보호사진이 아직 없으면 None. 있으면 {"status": "scanning"|"ready"|"error",
    "candidates": [...]}를 돌려준다("ready"일 때만 candidates가 채워진다).
    """
    latest = db.get_latest_completed_job()
    if latest is None:
        return None
    job_id, _job = latest

    cached = db.get_scan_cache(job_id)
    if cached is not None:
        return {"status": "ready", "candidates": cached}

    scan_id = MONITORING_SCAN_BY_JOB.get(job_id)
    if scan_id is None:
        try:
            started = await start_faceguard_scan(
                StartFaceGuardScanBody(
                    referenceJobIds=[job_id], webMonitoringConsent=True, maximumResults=10
                )
            )
        except HTTPException:
            logger.exception("얼굴가드 자동 스캔 시작 실패 (jobId=%s)", job_id)
            return {"status": "error", "candidates": []}
        scan_id = started["scanId"]
        MONITORING_SCAN_BY_JOB[job_id] = scan_id
        if started["status"] == "completed":
            # Vision이 공개 후보를 아예 못 찾은 경우 start_faceguard_scan이
            # 모델 API까지 갈 것도 없이 바로 completed로 기록해둔다.
            db.set_scan_cache(job_id, [])
            return {"status": "ready", "candidates": []}

    try:
        status_payload = await get_faceguard_scan(scan_id)
    except HTTPException:
        logger.exception("얼굴가드 스캔 상태 조회 실패 (scanId=%s)", scan_id)
        return {"status": "error", "candidates": []}

    if status_payload["status"] == "failed":
        # 모델 API가 스캔 자체를 실패로 종결한 경우 — "scanning"으로 두면
        # 영영 안 끝나는 것처럼 보인다. 별도 스캔을 다시 시작할 수 있게
        # 매핑을 지운다(다음 요청에서 새 스캔을 시도).
        MONITORING_SCAN_BY_JOB.pop(job_id, None)
        return {"status": "error", "candidates": []}
    if status_payload["status"] not in ("completed", "partial_failed"):
        return {"status": "scanning", "candidates": []}

    try:
        candidates_payload = await get_faceguard_candidates(scan_id)
    except HTTPException:
        logger.exception("얼굴가드 후보 조회 실패 (scanId=%s)", scan_id)
        return {"status": "error", "candidates": []}

    candidates = candidates_payload["candidates"]
    db.set_scan_cache(job_id, candidates)
    return {"status": "ready", "candidates": candidates}


def _source_label(provider: str | None) -> str:
    return {"google_vision_web_detection": "Google 이미지 검색"}.get(provider, provider or "기타")


def _risk_from_candidate(candidate: dict) -> tuple[str, str]:
    action = candidate.get("recommendedAction")
    if action == "review_required":
        return "high", "딥페이크 위험도 · 높음"
    if action == "monitor":
        return "low", "딥페이크 위험도 · 낮음"
    if action == "exclude_recommended":
        return "exclude-recommended", "제외 권장"
    return "medium", "수동 확인 필요"


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
async def get_monitoring_summary():
    scan = await _get_active_scan()
    if scan is None:
        last_checked = "아직 보호사진 없음"
        candidates: list[dict] = []
    elif scan["status"] == "scanning":
        last_checked = "스캔 진행 중..."
        candidates = []
    elif scan["status"] == "error":
        last_checked = "확인 실패 — 잠시 후 다시 시도해 주세요"
        candidates = []
    else:
        last_checked = "방금 확인"
        candidates = scan["candidates"]

    counts: dict[str, int] = {}
    for c in candidates:
        label = _source_label(c.get("sourceProvider"))
        counts[label] = counts.get(label, 0) + 1
    sources = [{"label": label, "count": f"{count}건"} for label, count in counts.items()]

    manual_reports = db.list_manual_reports()
    if manual_reports:
        sources.append({"label": "직접 제보", "count": f"{len(manual_reports)}건"})

    return {
        "lastCheckedAt": last_checked,
        "totalCandidates": len(candidates) + len(manual_reports),
        "sources": sources,
    }


@app.get("/api/monitoring/candidates")
async def get_candidates():
    scan = await _get_active_scan()
    candidates = scan["candidates"] if scan is not None and scan["status"] == "ready" else []

    result = []
    for i, c in enumerate(candidates, start=1):
        risk_level, risk_label = _risk_from_candidate(c)
        similarity = c.get("faceSimilarity")
        result.append({
            "id": f"c{i}",
            "label": f"후보 {i}",
            "similarityPercent": round(similarity * 100) if similarity is not None else 0,
            "riskLabel": risk_label,
            "riskLevel": risk_level,
            "sourceLabel": _source_label(c.get("sourceProvider")),
            "thumbnailUrl": c.get("thumbnailUrl") or c.get("mediaUrl"),
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


@app.get("/api/monitoring/candidates/{candidate_id}")
async def get_candidate_detail(candidate_id: str):
    base = next((c for c in await get_candidates() if c["id"] == candidate_id), None)
    if base is None:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")

    scan = await _get_active_scan()
    candidates = scan["candidates"] if scan is not None and scan["status"] == "ready" else []
    index = int(candidate_id[1:]) - 1

    if index >= len(candidates):
        rep = db.list_manual_reports()[index - len(candidates)]
        return {
            **base,
            "sourceLabel": "직접 제보",
            "sourceUrl": rep["url"],
            "sourceAccount": "-",
            "foundAt": "방금 제보",
            "signals": ["사용자가 직접 제출한 URL로, 자동 판별 대상이 아님", "필요 시 그대로 신고자료에 포함할 수 있음"],
        }

    c = candidates[index]
    signals = []
    similarity = c.get("faceSimilarity")
    if c.get("isSamePerson") is True:
        signals.append(
            f"ArcFace 동일인 판별: 일치 (코사인 유사도 {similarity:.3f})"
            if similarity is not None else "ArcFace 동일인 판별: 일치"
        )
    elif c.get("isSamePerson") is False:
        signals.append("ArcFace 동일인 판별: 불일치")
    else:
        signals.append("ArcFace 동일인 판별: 미완료")

    deepfake_score = c.get("deepfakeScore")
    if c.get("isSuspectedDeepfake") is True:
        signals.append(
            f"EfficientNet-B4 딥페이크 신호: 의심됨 (원점수 {deepfake_score:.4f})"
            if deepfake_score is not None else "EfficientNet-B4 딥페이크 신호: 의심됨"
        )
    elif c.get("isSuspectedDeepfake") is False:
        signals.append("EfficientNet-B4 딥페이크 신호: 의심 안 됨")
    else:
        signals.append("EfficientNet-B4 딥페이크 신호: 분석 미완료")
    signals.append(c.get("warning") or model_api.RESEARCH_WARNING)

    return {
        **base,
        "sourceLabel": _source_label(c.get("sourceProvider")),
        "sourceUrl": c.get("sourceUrl") or c.get("mediaUrl") or "-",
        "sourceAccount": "-",
        "foundAt": "방금 확인",
        "signals": signals,
    }


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


async def _build_report_draft() -> list[dict]:
    draft_overrides = db.get_draft_overrides()
    if draft_overrides is not None:
        return draft_overrides

    scan = await _get_active_scan()
    candidates = scan["candidates"] if scan is not None and scan["status"] == "ready" else []
    confirmed_keep_ids = db.get_confirmed_keep_ids()
    primary_id = confirmed_keep_ids[0] if confirmed_keep_ids else None
    primary_index = int(primary_id[1:]) - 1 if primary_id else None

    if primary_index is not None and primary_index >= len(candidates):
        rep = db.list_manual_reports()[primary_index - len(candidates)]
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

    if primary_index is None or not (0 <= primary_index < len(candidates)):
        return [
            {"key": "postUrl", "label": "게시물 URL", "value": "-"},
            {"key": "account", "label": "게시 계정", "value": "-"},
            {"key": "foundAt", "label": "발견 시각", "value": "-"},
            {"key": "capture", "label": "캡처 또는 파일", "value": "-"},
            {"key": "sha256", "label": "SHA-256", "value": "-"},
            {"key": "phash", "label": "pHash", "value": "-"},
            {"key": "c2pa", "label": "C2PA 확인 상태", "value": "-"},
            {"key": "aiResult", "label": "AI 분석 결과", "value": "확정된 후보 없음"},
        ]

    c = candidates[primary_index]
    _, risk_label = _risk_from_candidate(c)
    return [
        {"key": "postUrl", "label": "게시물 URL", "value": c.get("sourceUrl") or c.get("mediaUrl") or "-"},
        {"key": "account", "label": "게시 계정", "value": "-"},
        {"key": "foundAt", "label": "발견 시각", "value": "방금 확인"},
        {"key": "capture", "label": "캡처 또는 파일", "value": "자동 수집 이미지" if c.get("mediaUrl") else "-"},
        {"key": "sha256", "label": "SHA-256", "value": "확인 완료"},
        {"key": "phash", "label": "pHash", "value": "등록 완료"},
        {"key": "c2pa", "label": "C2PA 확인 상태", "value": "원본 불일치"},
        {"key": "aiResult", "label": "AI 분석 결과", "value": risk_label},
    ]


@app.get("/api/report/draft")
async def get_report_draft():
    return await _build_report_draft()


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
async def get_report_package():
    """동의된 증거 초안을 실제 파일(텍스트)로 묶어 내려준다. PDF·ZIP 생성기는 아직 없어
    프로토타입 단계에서는 사람이 바로 읽을 수 있는 증거 요약 텍스트로 대신한다."""
    draft = await _build_report_draft()
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
async def get_home_summary():
    monitoring = await get_monitoring_summary()
    return {
        "protectedCount": db.count_completed_jobs(),
        "candidateCount": monitoring["totalCandidates"],
        "reportCount": db.get_report_count(),
        "lastCheckedAt": monitoring["lastCheckedAt"],
    }
