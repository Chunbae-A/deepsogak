import hashlib
import io
import time
import uuid
from pathlib import Path

import imagehash
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

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
)
app.mount("/static", StaticFiles(directory=STORAGE_DIR), name="static")

# 프로토타입용 인메모리 저장소. 실서비스에서는 DB로 교체한다.
JOBS: dict[str, dict] = {}


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

    JOBS[job_id] = {
        "originalPath": original_path,
        "protectedPath": protected_path,
        "sha256": sha256,
        "phash": phash,
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
        "appliedChecks": [
            "딥백신 Beta 적용 완료",
            "불필요한 위치정보 제거 완료",
            "C2PA 출처정보 생성 완료",
            "SHA-256·pHash 등록 완료",
        ],
    }


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
# 아래 모니터링/후보검토/신고서 엔드포인트는 아직 실제 얼굴 인식(ArcFace)·
# 딥페이크 판별(EfficientNet-B4)·이미지 검색(SerpApi) 모델/키가 없어 고정된
# 시뮬레이션 데이터를 반환한다. 실제 모델이 준비되면 이 함수들 내부만 교체한다.
# ---------------------------------------------------------------------------


@app.get("/api/monitoring/summary")
def get_monitoring_summary():
    return {
        "lastCheckedAt": "2026.08.02 14:32",
        "totalCandidates": 6,
        "sources": [
            {"label": "검색엔진", "count": "3건"},
            {"label": "공개 SNS", "count": "2건"},
            {"label": "기타 웹사이트", "count": "1건"},
        ],
    }


@app.get("/api/monitoring/candidates")
def get_candidates():
    return [
        {"id": "c1", "label": "후보 1", "similarityPercent": 92, "riskLabel": "딥페이크 위험도 · 높음", "riskLevel": "high"},
        {"id": "c2", "label": "후보 2", "similarityPercent": 71, "riskLabel": "딥페이크 위험도 · 낮음", "riskLevel": "low"},
        {"id": "c3", "label": "후보 3", "similarityPercent": 38, "riskLabel": "제외 권장", "riskLevel": "exclude-recommended"},
    ]


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
    detail = CANDIDATE_DETAILS.get(candidate_id)
    if base is None or detail is None:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")
    return {**base, **detail}


class ConfirmCandidatesBody(BaseModel):
    keepIds: list[str]


@app.post("/api/monitoring/candidates/confirm")
def confirm_candidates(body: ConfirmCandidatesBody):
    return {"ok": True, "keepIds": body.keepIds}


@app.get("/api/report/draft")
def get_report_draft():
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


@app.post("/api/report/consent")
def submit_report_consent():
    return {"ok": True}
