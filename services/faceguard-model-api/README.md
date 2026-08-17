# 얼굴가드 모델 API

딥소각의 AI 추론을 담당하는 독립 FastAPI 서비스입니다. `face-image` 저장소의 `main` API 계약 커밋 `a625090`을 기준으로 운영 API 코드와 핵심 테스트만 모노레포에 이관했습니다. 학습 노트북·데이터·실험 보고서는 포함하지 않습니다.

## 무엇을 처리하나요?

```text
등록 얼굴 1~5장(3장 권장)
        ↓
ArcFace로 동일인 후보 선별
        ↓
EfficientNet-B4 ONNX로 이미지·영상 분석
        ↓
얼굴 유사도 원점수와 딥페이크 의심 원점수 반환
```

- `SCRFD-10GF`: 이미지에서 얼굴 위치를 찾습니다.
- `ArcFace`: 등록 얼굴과 후보 얼굴이 같은 사람인지 비교합니다.
- `EfficientNet-B4 ONNX`: 후보 얼굴의 딥페이크 의심 점수를 계산합니다.
- 비동기 노출 스캔: 공개 후보 URL 여러 개를 백그라운드에서 순서대로 처리합니다.

## 현재 주의사항

- `similarity`와 `deepfake_score`는 보정된 확률이 아닌 연구용 원점수입니다.
- 얼굴 기준값은 Celeb-real, 딥페이크 모델은 Celeb-DF-v2 실험에서 정했습니다.
- 외부 한국인 실제 촬영 데이터 검증과 운영 Gate를 통과하지 않았습니다.
- 결과만으로 피해를 확정하거나 자동 신고·삭제하면 안 됩니다.
- InsightFace 사전학습 가중치는 비상업 연구 조건을 직접 확인한 뒤 사용해야 합니다.

## 1. 로컬 실행

Python 3.11 이상이 필요합니다. 모델 API는 기존 `server`와 포트가 겹치지 않도록 로컬에서 `8001` 포트를 권장합니다.

```bash
cd services/faceguard-model-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-api.txt
cp .env.example .env
```

`.env`에서 InsightFace 가중치 조건을 확인한 뒤 다음 값을 변경합니다.

```dotenv
FACEGUARD_ACCEPT_NONCOMMERCIAL_MODEL_LICENSE=true
```

딥페이크 ONNX 파일은 GitHub가 아닌 다음 로컬 경로에 둡니다.

```text
services/faceguard-model-api/.models/deepfake/efficientnet_b4.onnx
```

파일 해시가 `.env`의 `FACEGUARD_DEEPFAKE_MODEL_SHA256`과 같은지 확인합니다.

```bash
shasum -a 256 .models/deepfake/efficientnet_b4.onnx
```

환경변수를 적용하고 API를 실행합니다.

```bash
set -a
source .env
set +a
uvicorn faceguard_api.app:app --host 127.0.0.1 --port 8001
```

브라우저에서 [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)를 열면 Swagger 테스트 화면이 나옵니다. 최초 얼굴 분석 때 InsightFace 모델 준비로 시간이 더 걸릴 수 있습니다.

## 2. Docker 실행

```bash
cd services/faceguard-model-api
cp .env.example .env
# 라이선스 확인 후 .env 값을 변경하고 ONNX 파일을 .models/deepfake에 배치
docker compose up --build
```

Docker도 호스트의 `127.0.0.1:8001`로만 공개합니다.

## 주요 API

| API | 용도 |
|---|---|
| `GET /health` | API와 모델 로딩 상태 확인 |
| `GET /v1/capabilities` | 사용 가능한 모델·기능과 연구/운영 승인 상태 확인 |
| `POST /v1/faceguard/verify` | 등록 얼굴과 확인 얼굴 비교 |
| `POST /v1/deepfake/analyze` | 이미지 한 장 딥페이크 분석 |
| `POST /v1/deepfake/analyze-video` | 영상 대표 프레임 딥페이크 분석 |
| `POST /v1/faceguard/enrollments` | 비동기 스캔용 얼굴 임시 등록 |
| `POST /v1/exposure-scans` | 공개 후보 URL 분석 시작 |
| `GET /v1/exposure-scans/{scan_id}` | 분석 진행 상태 확인 |
| `GET /v1/exposure-scans/{scan_id}/candidates` | 후보별 최종 결과 확인 |
| `GET /v1/exposure-scans/{scan_id}/client-candidates` | 화면에 안전하게 표시할 후보·행동 권고 확인 |

기존 `server`가 Google Vision으로 찾은 후보는 `POST /v1/exposure-scans`의 `candidates`에 넣습니다. 브라우저 앱이 모델 API를 직접 호출하지 않고, 기존 서버가 내부에서 호출하는 구조를 사용합니다.

## Google Vision 연동 흐름

이번 브랜치는 클라이언트 코드를 수정하지 않고 서버 계약까지만 연결합니다.

```text
사용자가 등록한 사진(명시적 웹 검색 동의)
    ↓ EXIF가 제거된 보호본 한 장만 외부 전송
Google Vision Web Detection
    ↓ 공개 페이지 URL·이미지 URL, 최대 10개
ArcFace 동일인 후보 선별
    ↓ 같은 사람으로 판단된 후보만
EfficientNet-B4 ONNX 딥페이크 분석
    ↓
얼굴 유사도·딥페이크 원점수·사람 검토 권고 반환
```

- Google Vision의 Web Detection 값은 딥페이크 확률이나 얼굴 신뢰도로 사용하지 않습니다.
- 전체 이미지 pHash로 후보를 먼저 제거하지 않습니다. 크롭·압축·합성으로 pHash가 달라져도 ArcFace가 얼굴을 비교할 수 있게 하기 위함입니다.
- API 키는 `server/.env`에만 두며 요청 URL이 아닌 `x-goog-api-key` 헤더로 전달합니다.
- 키 누락·외부 호출 실패·모델 실패 시 가짜 후보나 가짜 점수로 폴백하지 않습니다.
- Google Cloud Console에서 키의 API 사용 범위를 Cloud Vision API로 제한해야 합니다.

서버 측 API는 다음과 같습니다.

| API | 용도 |
|---|---|
| `GET /api/faceguard/health` | Vision 설정과 모델 API 연결 준비 상태 확인 |
| `GET /api/faceguard/capabilities` | 앱이 사용할 기능과 자동 조치 허용 여부 확인 |
| `POST /api/faceguard/scans` | Vision 후보 수집과 모델 분석 시작 |
| `GET /api/faceguard/scans/{scan_id}` | 모델 분석 진행률 확인 |
| `GET /api/faceguard/scans/{scan_id}/candidates` | 후보별 얼굴·딥페이크 원점수와 검토 행동값 확인 |

`POST /api/faceguard/scans` 예시는 다음과 같습니다. `referenceJobIds`는 기존 `POST /api/protection/process`가 반환한 `jobId`입니다.

```json
{
  "referenceJobIds": ["등록사진-job-id"],
  "webMonitoringConsent": true,
  "maximumResults": 10
}
```

## 테스트

모델 파일 없이도 핵심 도메인·HTTP 계약·후보 다운로드 안전성 테스트를 실행할 수 있습니다.

```bash
cd services/faceguard-model-api
python -m pip install -r requirements-api-test.txt
python -m unittest discover -s tests
```

## 저장 금지 항목

다음 항목은 저장소에 커밋하지 않습니다.

- 얼굴 및 영상 원본
- 정렬 얼굴 crop과 임베딩
- Celeb-DF-v2 등 원본 데이터셋
- `.onnx`, `.pt`, `.pth`, `.ckpt` 모델 파일
- `.env`와 서비스 비밀값
