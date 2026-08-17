#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.faceguard.example"
MODEL_FILE="$REPO_ROOT/services/faceguard-model-api/.models/deepfake/efficientnet_b4.onnx"

if ! command -v docker >/dev/null 2>&1; then
  echo "오류: Docker Desktop을 설치하고 실행한 뒤 다시 시도하세요." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "설정 파일을 만들었습니다: $ENV_FILE"
  echo "라이선스 확인값과 GOOGLE_VISION_API_KEY를 입력한 뒤 다시 실행하세요." >&2
  exit 1
fi

if ! grep -Eq '^FACEGUARD_ACCEPT_NONCOMMERCIAL_MODEL_LICENSE=true$' "$ENV_FILE"; then
  echo "오류: InsightFace 사용 조건을 직접 확인한 뒤 .env 값을 true로 바꾸세요." >&2
  exit 1
fi

if [ ! -f "$MODEL_FILE" ]; then
  echo "오류: 딥페이크 ONNX 모델 파일이 없습니다." >&2
  echo "필요한 위치: $MODEL_FILE" >&2
  exit 1
fi

cd "$REPO_ROOT"
exec docker compose --env-file "$ENV_FILE" -f docker-compose.faceguard.yml up --build

