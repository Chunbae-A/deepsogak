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
