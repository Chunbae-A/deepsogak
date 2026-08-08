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
