#!/bin/sh
set -eu

SERVER_BASE_URL=${FACEGUARD_SERVER_BASE_URL:-http://127.0.0.1:8000}
MODEL_BASE_URL=${FACEGUARD_MODEL_BASE_URL:-http://127.0.0.1:8001}

if ! command -v curl >/dev/null 2>&1; then
  echo "오류: curl 명령이 필요합니다." >&2
  exit 1
fi

echo "[1/3] 딥소각 서버와 Google Vision 설정 상태"
curl -fsS "$SERVER_BASE_URL/api/faceguard/health"
printf '\n\n'

echo "[2/3] 클라이언트용 얼굴가드 기능 계약"
curl -fsS "$SERVER_BASE_URL/api/faceguard/capabilities"
printf '\n\n'

echo "[3/3] 내부 모델 API 상태"
curl -fsS "$MODEL_BASE_URL/health"
printf '\n\n'

echo "연결 확인이 끝났습니다. health의 not_ready는 키나 모델 설정이 빠졌다는 뜻이며 가짜 성공으로 처리하지 않습니다."

