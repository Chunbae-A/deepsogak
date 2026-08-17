# 딥페이크 판별 모델 학습 파이프라인

`services/faceguard-model-api/`는 **추론(서빙)** 만 담당한다. 그 서비스가 쓰는 EfficientNet-B4
ONNX 모델을 실제로 만드는(학습·평가·변환·보정) 코드가 이 디렉터리다.

## 왜 별도 디렉터리인가

`app/`·`server/`·`services/`와 완전히 다른 의존성(torch/timm vs FastAPI/onnxruntime-only)이라
분리했다. **서빙 서비스 코드는 이 파이프라인 작업 중 한 줄도 바뀌지 않는다** — 결과물(ONNX +
보정 JSON)을 `.env` 값만 바꿔서 꽂는 구조.

## 설치

```bash
cd training
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# GPU가 있으면:
python -m pip install -r requirements-train-gpu.txt
# 없으면:
python -m pip install -r requirements-train-cpu.txt
```

CI/스모크 테스트만 돌릴 거면 `requirements-train-test.txt` 하나면 충분하다(InsightFace/OpenCV
불필요 — 정렬 단계를 fake로 대체).

## 데이터 위치

기본은 저장소 루트의 `data/raw/<name>/`, `data/processed/<name>/`를 본다(`data` 브랜치가 만든
스켈레톤 + `../DATA_PLAN.md` 참고). 대용량 데이터를 다른 드라이브에 뒀다면
`configs/default.yaml`의 `data_root`를 절대경로로 바꾸면 된다 — 나머지 코드는 경로 하나만
보고 동작하므로 그대로 쓸 수 있다.

| 데이터셋 | 용도 | 원본 폴더 예상 구조 |
|---|---|---|
| FF++ | 1차 베이스라인 | `original_sequences/youtube/c23/videos`, `manipulated_sequences/<Method>/c23/videos` (공식 `download-FaceForensics.py` 산출물 그대로) |
| Celeb-DF v2 | 1차 베이스라인 | `Celeb-real/`, `Celeb-synthesis/`, `YouTube-real/` |
| KoDF | 한국인 파인튜닝 (★핵심) | AI-Hub 원본 zip 구조 — `../scripts/aihub_download.sh` + `../scripts/aihub_merge_zip_parts.sh` 참고 |
| DeeperForensics-1.0 | 강건성 테스트 전용(학습 제외) | — |
| self_check | 정성적 테스트 전용(팀원 본인 얼굴) | — |

K-FACE는 이 파이프라인 범위 밖이다(ArcFace 얼굴 유사도 임계값 재보정용, 별도 트랙).

## 파이프라인 단계

```
build_manifest.py   data/raw/<name>/ 를 훑어 subject_id·label·split이 붙은
                     data/processed/manifests/<name>.csv 를 만든다.
                     --dry-run 으로 subject_id 추출 결과를 먼저 눈으로 확인할 것.

align_faces.py       매니페스트 기준으로 InsightFace buffalo_l + norm_crop(224)를 돌려
                     오프라인 정렬 캐시를 만든다.

train.py              timm tf_efficientnet_b4(ImageNet 사전학습) 파인튜닝.

evaluate.py           per-frame과 video-mean-16(서빙이 실제로 쓰는 스코프) 두 기준으로
                     AUC/재현율/정밀도를 낸다.

export_onnx.py        torch → ONNX. 입력 1개 (N,3,380,380), 출력 1개(raw logit) 계약을
                     그대로 지킨다.

check_parity.py       torch 출력과 onnxruntime 출력이 일치하는지, 그래프 계약을 만족하는지
                     검증한다.

calibrate.py           video-mean-16 검증 점수로 보정(JSON) 산출 + Gate(공개 승인) 판정.
```

## 서빙 계약과의 정합성

전처리(`preprocess_aligned_face`, ImageNet 정규화 상수)는 재구현하지 않고
`services/faceguard-model-api/faceguard_api/deepfake.py`에서 그대로 import한다
(`deepfake_training/common/faceguard_bridge.py`). 정렬(`norm_crop`)·리사이즈(PIL BILINEAR)
동작을 학습·추론 시점에 비트 단위로 맞추기 위해 `insightface`/`opencv-python`/`Pillow`/
`numpy`/`onnxruntime` 버전도 `services/faceguard-model-api/requirements-api-base.txt`와
동일하게 고정했다.

보정 JSON은 서빙 코드가 실제로 소비하는 `scope="deepfake_video_mean_16_frames"` 하나만
타깃으로 한다(단일 이미지 엔드포인트는 보정 파일을 아예 안 봄).

## 서빙 서비스로 결과물 반영 (코드 변경 0)

```bash
cp training/runs/<run_name>/model.onnx services/faceguard-model-api/.models/deepfake/efficientnet_b4.onnx
cp training/runs/<run_name>/calibration.json services/faceguard-model-api/.models/deepfake/deepfake_video_calibration.json
sha256sum services/faceguard-model-api/.models/deepfake/efficientnet_b4.onnx
# → services/faceguard-model-api/.env 의 FACEGUARD_DEEPFAKE_MODEL_SHA256 갱신
```

## 스모크 테스트 (실 데이터 없이 검증)

```bash
python -m pip install -r requirements-train-test.txt
python -m unittest discover -s tests -t .
```

`tests/test_smoke_pipeline.py`가 합성 데이터로 전체 체인(매니페스트→정렬(fake)→학습(2
step)→평가→변환→parity→보정)을 CPU에서 60초 안에 통과시킨다. `test_calibration_schema.py`는
산출된 보정 JSON을 실제 `faceguard_api.calibration.ScoreCalibration.load()`로 왕복 검증하므로,
이게 통과하면 "서빙 코드 무변경 드롭인" 요건이 코드로 증명된 것이다.

## 실 데이터로 첫 검증

```bash
python -m deepfake_training.build_manifest --dataset ffpp --dry-run
python -m deepfake_training.build_manifest --dataset celebdf --dry-run
```

`--dry-run`은 subject_id 추출 결과만 출력하고 아무것도 쓰지 않는다 — 실제 폴더 구조를 보고
어댑터의 subject_id 규칙이 말이 되는지 사람이 먼저 확인하는 단계.
