# deepsogak

딥소각은 공개 웹에서 본인 얼굴이 포함된 후보를 찾고, 동일인 여부와 딥페이크 의심 여부를 분석해 대응 자료 작성을 돕는 서비스입니다.

## 저장소 구성

| 경로 | 역할 |
|---|---|
| [`app/`](app/) | Expo 기반 사용자 앱 |
| [`server/`](server/) | 보호·모니터링·신고 흐름을 제공하는 FastAPI 서버 |
| [`services/faceguard-model-api/`](services/faceguard-model-api/) | ArcFace 얼굴 비교와 EfficientNet-B4 ONNX 딥페이크 분석 API |

앱과 기존 서버의 실행 방법은 각 디렉터리의 설정을 따릅니다. 모델 API를 처음 실행하는 사람은 [모델 API 시작 안내](services/faceguard-model-api/README.md)를 확인하세요.

## 모델 API 상태

모델 API 코드는 저장소에 포함하지만, 얼굴·영상 원본과 ONNX 가중치는 포함하지 않습니다. 현재 얼굴 비교 및 딥페이크 판정 기준값은 연구용이며 운영 승인을 받은 정확도나 확률을 뜻하지 않습니다.

## 프론트 연동 데모

사진 한 장을 선택하면 다음 흐름을 실제로 실행합니다.

```text
Expo 앱 → 기존 FastAPI 서버 → ArcFace·ONNX 모델 API → 보호 결과 화면
```

기존 서버는 원본과 메타데이터를 제거한 보호본이 같은 얼굴인지 확인하고, 보호본의 딥페이크 원점수를 받아 화면에 표시합니다. 모델 API가 꺼져 있어도 보호본 생성은 유지하고, 임의의 점수를 만들지 않고 연결 실패를 표시합니다.

로컬에서는 세 프로세스를 각각 실행합니다.

1. [모델 API 안내](services/faceguard-model-api/README.md)에 따라 모델 API를 `127.0.0.1:8001`에서 실행합니다.
2. `server`에서 `uvicorn main:app --host 127.0.0.1 --port 8000`을 실행합니다.
3. `app`에서 `EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run web`을 실행합니다.

연결 상태는 기존 서버의 `GET /api/model/health`에서 확인할 수 있습니다.

## 공개 노출 모니터링 연결

얼굴가드의 새 모니터링 화면은 더 이상 고정된 후보 3개나 pHash 점수를 AI 위험도로 표시하지 않습니다. 다음 실제 API 흐름을 사용합니다.

```text
1. 보호 탭에서 등록 사진 업로드
2. 공개 검색어 입력 및 검색 동의
3. SearXNG이 키워드 기반 공개 이미지 후보 수집
4. ArcFace가 등록 얼굴과 같은 사람 후보 선별
5. EfficientNet-B4 ONNX가 딥페이크 의심 원점수 계산
6. 프론트가 작업 진행률과 검토 후보 표시
```

SearXNG은 얼굴 사진 역검색이 아닙니다. 사진을 검색엔진으로 보내지 않고 이름·활동명 같은 검색어만 전달합니다. 후보 화면의 `faceSimilarity`와 `deepfakeScore`는 확률이 아닌 연구용 원점수이며 자동 신고·삭제에 사용하지 않습니다.

로컬에서 공개 검색까지 함께 실행하려면 모델 API를 다음 명령으로 시작합니다.

```bash
cd services/faceguard-model-api
docker compose -f docker-compose.yml -f docker-compose.searxng.yml up --build
```

그다음 기존 서버와 앱을 각각 실행합니다.

```bash
cd server
python -m pip install -r requirements.txt
FACEGUARD_MODEL_API_URL=http://127.0.0.1:8001 uvicorn main:app --host 127.0.0.1 --port 8000
```

```bash
cd app
npm ci
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run web
```

연결에 사용하는 딥소각 서버 API는 다음과 같습니다.

| API | 용도 |
|---|---|
| `POST /api/monitoring/scans` | 등록 사진·동의·검색어로 공개 노출 분석 시작 |
| `GET /api/monitoring/scans/{scan_id}` | 검색·얼굴 선별·딥페이크 분석 진행률 확인 |
| `GET /api/monitoring/scans/{scan_id}/summary` | 출처별 공개 후보 개수 확인 |
| `GET /api/monitoring/scans/{scan_id}/candidates` | 프론트용 얼굴·딥페이크 원점수와 검토 행동값 확인 |

현재 작업과 결과는 메모리에만 저장되므로 서버를 재시작하면 사라집니다. 공개 영상 후보 자동 수집, 영구 작업 큐, 운영 기준값 승인은 다음 단계입니다.
