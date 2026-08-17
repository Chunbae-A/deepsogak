#!/usr/bin/env bash
# AI-Hub 데이터셋을 filekey 단위로 선택 다운로드한다.
# 전체(KoDF datasetkey=55는 약 2.8TB)를 받으면 안 되므로, data/inventory/55_inventory.md에서
# 필요한 filekey만 골라 넘길 것.
#
# 사용법:
#   AIHUB_API_KEY=xxxx ./scripts/aihub_download.sh 55 38522,38523
#
# AIHUB_API_KEY는 aihub.or.kr 회원가입 후 마이페이지에서 자체 발급하는 셀프서비스 키다
# (사람 검토를 기다리는 승인 절차가 아님).

set -euo pipefail

DATASET_KEY="${1:?사용법: aihub_download.sh <datasetkey> <filekey1,filekey2,...>}"
FILE_KEYS="${2:?filekey를 쉼표로 구분해 지정하세요. data/inventory/<datasetkey>_inventory.md 참고}"
: "${AIHUB_API_KEY:?AIHUB_API_KEY 환경변수를 설정하세요}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_BIN="$SCRIPT_DIR/aihubshell"

if [ ! -f "$SHELL_BIN" ]; then
  curl -sL -o "$SHELL_BIN" "https://api.aihub.or.kr/api/aihubshell.do"
  chmod +x "$SHELL_BIN"
fi

DEST_DIR="$SCRIPT_DIR/../data/raw/kodf"
mkdir -p "$DEST_DIR"

cd "$DEST_DIR"
bash "$SHELL_BIN" -mode d -datasetkey "$DATASET_KEY" -filekey "$FILE_KEYS" -aihubapikey "$AIHUB_API_KEY"
