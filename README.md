# deepsogak

딥소각은 공개 웹에서 본인 얼굴이 포함된 후보를 찾고, 동일인 여부와 딥페이크 의심 여부를 분석해 대응 자료 작성을 돕는 것을 목표로 한 프로토타입입니다.

## 프로젝트 상태

**2026년 제8회 K-디지털 트레이닝 해커톤 아이디어상 수상으로 프로젝트를 마무리합니다.** 이 저장소는 예선심사 기획안을 바탕으로 핵심 기능(딥백신 노이즈, 얼굴가드 파이프라인 등)을 프로토타입 수준으로 구현해본 결과물이며, 운영 배포가 가능한 완성된 서비스는 아닙니다. 심사에 제출한 기획안은 [`docs/`](docs/)에서 확인할 수 있습니다.

## 저장소 구성

| 경로 | 역할 |
|---|---|
| [`docs/`](docs/) | 해커톤 예선심사 제출 기획안 |
| [`app/`](app/) | Expo 기반 사용자 앱 |
| [`server/`](server/) | 보호·모니터링·신고 흐름을 제공하는 FastAPI 서버 |
| [`services/faceguard-model-api/`](services/faceguard-model-api/) | ArcFace 얼굴 비교와 EfficientNet-B4 ONNX 딥페이크 분석 API |
| [`training/`](training/) | 딥페이크 판별 모델(EfficientNet-B4) 학습 파이프라인 |

앱과 기존 서버의 실행 방법은 각 디렉터리의 설정을 따릅니다. 모델 API를 처음 실행하는 사람은 [모델 API 시작 안내](services/faceguard-model-api/README.md)를 확인하세요.

## 얼굴가드를 왜 이렇게 나눴나요?

앱이 AI 모델이나 Google API 키를 직접 다루면 비밀값이 노출되고, 모델이 바뀔 때마다 앱도 함께 수정해야 합니다. 그래서 역할을 다음처럼 분리했습니다.

```text
앱 또는 API 사용자
        ↓
딥소각 서버: 동의 확인·Google Vision 공개 후보 수집·화면용 응답 변환
        ↓
모델 API: ArcFace 동일인 선별·EfficientNet-B4 ONNX 딥페이크 분석
```

이 구조로 해결한 것은 세 가지입니다.

1. Google Vision 키와 모델 파일을 클라이언트에 노출하지 않습니다.
2. 얼굴 유사도와 딥페이크 원점수를 확률처럼 오해하지 않도록 연구 상태와 사람 검토 행동값을 함께 반환합니다.
3. `face-image`의 실험 코드는 그대로 두고, 서비스에 필요한 추론 코드와 API 계약만 모노레포에서 실행할 수 있습니다.

## 얼굴가드만 한 번에 실행

Docker Desktop을 켠 뒤 저장소 루트에서 실행합니다.

```bash
./scripts/run-faceguard-demo.sh
```

첫 실행은 `.env`를 자동 생성하고 중단됩니다. `.env`에서 라이선스 확인값과 `GOOGLE_VISION_API_KEY`를 설정하고 같은 명령을 다시 실행하면 됩니다. 직접 실행하려면 `docker compose --env-file .env -f docker-compose.faceguard.yml up --build`를 사용합니다.

딥페이크 모델 파일은 GitHub에 포함하지 않습니다. 실행 전에 다음 위치에 둡니다.

```text
services/faceguard-model-api/.models/deepfake/efficientnet_b4.onnx
services/faceguard-model-api/.models/deepfake/deepfake_video_calibration.json
```

실행 후 확인 주소는 다음과 같습니다.

| 주소 | 확인 내용 |
|---|---|
| [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | 딥소각 서버 API 테스트 화면 |
| [http://127.0.0.1:8000/api/faceguard/capabilities](http://127.0.0.1:8000/api/faceguard/capabilities) | 클라이언트가 사용할 수 있는 기능과 안전 상태 |
| [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) | 내부 모델 API 테스트 화면 |

`POST /api/faceguard/scans`에 보호사진 처리 결과의 `jobId`를 보내면 Google Vision 후보 수집부터 ArcFace·ONNX 분석까지 시작합니다. 브라우저 앱은 모델 API의 `8001` 포트를 직접 호출하지 않고 항상 서버의 `8000` 포트만 호출해야 합니다.

다른 터미널에서 다음 명령을 실행하면 서버·모델 API 연결과 기능 상태를 한 번에 확인할 수 있습니다.

```bash
./scripts/check-faceguard-demo.sh
```

서버 health가 `not_ready`이면 오류를 숨긴 것이 아니라 Google Vision 키 또는 모델 준비가 빠졌다는 뜻입니다. `capabilities`의 점수 비확률·자동 조치 금지 상태도 함께 확인하세요.

## 모델 API 상태

모델 API 코드는 저장소에 포함하지만, 얼굴·영상 원본과 ONNX 가중치는 포함하지 않습니다. 현재 얼굴 비교 및 딥페이크 판정 기준값은 연구용이며 운영 승인을 받은 정확도나 확률을 뜻하지 않습니다.

서버의 얼굴가드 파이프라인은 `Google Vision 후보 수집 → ArcFace 동일인 선별 → EfficientNet-B4 ONNX 분석` 순서로 구성합니다. Google Vision API 키는 서버에서만 사용하며 클라이언트에는 전달하지 않습니다. 자세한 실행 방법과 API 계약은 [모델 API 시작 안내](services/faceguard-model-api/README.md)를 확인하세요.

현재 저장소가 제공하는 것은 시연 가능한 연구용 API입니다. 공개 웹 전체를 자동 순회하는 검색 엔진, 영구 DB·S3 저장, 운영 인증·요금 제한, 운영 승인된 판정 기준값은 후속 작업입니다.
