#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODEL_DIR="${PROJECT_ROOT}/services/faceguard-model-api"
SERVER_DIR="${PROJECT_ROOT}/server"
APP_DIR="${PROJECT_ROOT}/app"
SERVER_VENV="${SERVER_DIR}/.venv"

MODEL_API_PORT=8001
SERVER_PORT=8002
APP_PORT=8082
RUNTIME_DIR="${TMPDIR:-/tmp}/deepsogak-demo-${UID}"
SERVER_PID_FILE="${RUNTIME_DIR}/server.pid"
APP_PID_FILE="${RUNTIME_DIR}/app.pid"
SERVER_LOG="${RUNTIME_DIR}/server.log"
APP_LOG="${RUNTIME_DIR}/app.log"

mkdir -p "${RUNTIME_DIR}"

info() {
  printf '[딥소각] %s\n' "$1"
}

fail() {
  printf '[딥소각] 오류: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "필수 명령을 찾지 못했습니다: $1"
}

pid_is_running() {
  local pid_file="$1"
  local expected_text="$2"
  local pid
  local command_text

  [ -f "${pid_file}" ] || return 1
  pid="$(sed -n '1p' "${pid_file}")"
  [ -n "${pid}" ] || return 1
  kill -0 "${pid}" >/dev/null 2>&1 || return 1
  command_text="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
  case "${command_text}" in
    *"${expected_text}"*) return 0 ;;
    *) return 1 ;;
  esac
}

port_is_listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="$3"
  local attempt=1

  while [ "${attempt}" -le "${attempts}" ]; do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      info "${name} 준비 완료"
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

find_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
    return
  fi
  if [ -x /opt/homebrew/bin/python3.11 ]; then
    printf '%s\n' /opt/homebrew/bin/python3.11
    return
  fi
  fail "Python 3.11이 필요합니다. Homebrew에서 python@3.11을 설치해 주세요."
}

check_model_prerequisites() {
  if [ ! -f "${MODEL_DIR}/.env" ]; then
    cp "${MODEL_DIR}/.env.example" "${MODEL_DIR}/.env"
    fail "모델 .env를 만들었습니다. FACEGUARD_ACCEPT_NONCOMMERCIAL_MODEL_LICENSE=true로 직접 확인한 뒤 다시 실행해 주세요."
  fi
  if ! grep -Eq '^FACEGUARD_ACCEPT_NONCOMMERCIAL_MODEL_LICENSE=true[[:space:]]*$' "${MODEL_DIR}/.env"; then
    fail "InsightFace 비상업 연구용 모델 조건 확인 후 .env의 FACEGUARD_ACCEPT_NONCOMMERCIAL_MODEL_LICENSE를 true로 변경해 주세요."
  fi
  if [ ! -f "${MODEL_DIR}/.models/deepfake/efficientnet_b4.onnx" ]; then
    fail "딥페이크 ONNX 파일이 없습니다: services/faceguard-model-api/.models/deepfake/efficientnet_b4.onnx"
  fi
}

ensure_server_dependencies() {
  local python_bin
  python_bin="$(find_python)"

  if [ ! -x "${SERVER_VENV}/bin/python" ]; then
    info "딥소각 서버 Python 환경을 처음 한 번 준비합니다."
    "${python_bin}" -m venv "${SERVER_VENV}"
  fi
  if ! "${SERVER_VENV}/bin/python" -c 'import fastapi, httpx, imagehash, requests, uvicorn; from fastapi.testclient import TestClient' >/dev/null 2>&1; then
    info "딥소각 서버 라이브러리를 설치합니다."
    "${SERVER_VENV}/bin/python" -m pip install --disable-pip-version-check -r "${SERVER_DIR}/requirements.txt"
  fi
}

ensure_app_dependencies() {
  if [ ! -x "${APP_DIR}/node_modules/.bin/expo" ]; then
    info "프론트 라이브러리를 처음 한 번 설치합니다."
    (cd "${APP_DIR}" && npm ci --no-audit --no-fund)
  fi
}

start_model_services() {
  if port_is_listening "${MODEL_API_PORT}"; then
    if [ -z "$(cd "${MODEL_DIR}" && docker compose -f docker-compose.yml -f docker-compose.searxng.yml ps -q faceguard-model-api 2>/dev/null)" ]; then
      fail "포트 ${MODEL_API_PORT}을 다른 프로그램이 사용 중입니다. 해당 프로그램을 종료한 뒤 다시 실행해 주세요."
    fi
  fi

  info "모델 API와 SearXNG을 시작합니다."
  (
    cd "${MODEL_DIR}"
    docker compose -f docker-compose.yml -f docker-compose.searxng.yml up --build --detach
  )
  if ! wait_for_url "모델 API" "http://127.0.0.1:${MODEL_API_PORT}/health" 90; then
    (cd "${MODEL_DIR}" && docker compose -f docker-compose.yml -f docker-compose.searxng.yml logs --no-color --tail=80)
    fail "모델 API가 시간 안에 준비되지 않았습니다."
  fi
}

start_server() {
  if pid_is_running "${SERVER_PID_FILE}" 'uvicorn'; then
    info "딥소각 서버가 이미 실행 중입니다."
    return
  fi
  rm -f "${SERVER_PID_FILE}"
  if port_is_listening "${SERVER_PORT}"; then
    fail "포트 ${SERVER_PORT}을 다른 프로그램이 사용 중입니다."
  fi

  info "딥소각 서버를 시작합니다."
  (
    cd "${SERVER_DIR}"
    nohup env FACEGUARD_MODEL_API_URL="http://127.0.0.1:${MODEL_API_PORT}" \
      "${SERVER_VENV}/bin/uvicorn" main:app --host 127.0.0.1 --port "${SERVER_PORT}" \
      >"${SERVER_LOG}" 2>&1 &
    printf '%s\n' "$!" >"${SERVER_PID_FILE}"
  )
  if ! wait_for_url "딥소각 서버" "http://127.0.0.1:${SERVER_PORT}/api/model/health" 30; then
    tail -n 80 "${SERVER_LOG}" 2>/dev/null || true
    fail "딥소각 서버가 시간 안에 준비되지 않았습니다."
  fi
}

start_app() {
  if pid_is_running "${APP_PID_FILE}" 'expo'; then
    info "딥소각 프론트가 이미 실행 중입니다."
    return
  fi
  rm -f "${APP_PID_FILE}"
  if port_is_listening "${APP_PORT}"; then
    fail "포트 ${APP_PORT}을 다른 프로그램이 사용 중입니다."
  fi

  info "딥소각 프론트를 시작합니다."
  (
    cd "${APP_DIR}"
    nohup env EXPO_PUBLIC_API_BASE_URL="http://127.0.0.1:${SERVER_PORT}" \
      EXPO_NO_TELEMETRY=1 BROWSER=none "${APP_DIR}/node_modules/.bin/expo" \
      start --web --port "${APP_PORT}" \
      >"${APP_LOG}" 2>&1 &
    printf '%s\n' "$!" >"${APP_PID_FILE}"
  )
  if ! wait_for_url "딥소각 프론트" "http://127.0.0.1:${APP_PORT}" 60; then
    tail -n 80 "${APP_LOG}" 2>/dev/null || true
    fail "딥소각 프론트가 시간 안에 준비되지 않았습니다."
  fi
}

show_status() {
  printf '\n'
  info "실행 상태"
  if curl -fsS "http://127.0.0.1:${MODEL_API_PORT}/health" >/dev/null 2>&1; then
    printf '  모델 API·SearXNG: 정상  http://127.0.0.1:%s/docs\n' "${MODEL_API_PORT}"
  else
    printf '  모델 API·SearXNG: 중지\n'
  fi
  if curl -fsS "http://127.0.0.1:${SERVER_PORT}/api/model/health" >/dev/null 2>&1; then
    printf '  딥소각 서버:       정상  http://127.0.0.1:%s/docs\n' "${SERVER_PORT}"
  else
    printf '  딥소각 서버:       중지\n'
  fi
  if curl -fsS "http://127.0.0.1:${APP_PORT}" >/dev/null 2>&1; then
    printf '  딥소각 프론트:     정상  http://127.0.0.1:%s\n' "${APP_PORT}"
  else
    printf '  딥소각 프론트:     중지\n'
  fi
  printf '  로그 폴더:         %s\n\n' "${RUNTIME_DIR}"
}

stop_managed_process() {
  local name="$1"
  local pid_file="$2"
  local expected_text="$3"
  local pid
  local attempt=1

  if ! pid_is_running "${pid_file}" "${expected_text}"; then
    rm -f "${pid_file}"
    info "${name}는 실행 중이 아닙니다."
    return
  fi
  pid="$(sed -n '1p' "${pid_file}")"
  info "${name}를 종료합니다."
  kill "${pid}"
  while kill -0 "${pid}" >/dev/null 2>&1 && [ "${attempt}" -le 10 ]; do
    sleep 1
    attempt=$((attempt + 1))
  done
  rm -f "${pid_file}"
}

start_all() {
  require_command docker
  require_command curl
  require_command lsof
  require_command npm
  docker info >/dev/null 2>&1 || fail "Docker Desktop을 먼저 실행해 주세요."
  check_model_prerequisites
  ensure_server_dependencies
  ensure_app_dependencies
  start_model_services
  start_server
  start_app
  show_status
  if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:${APP_PORT}"
  fi
  info "브라우저에서 사진 등록 → 공개 검색 동의 → 후보 확인 순서로 테스트하세요."
  info "이 터미널을 열어 두세요. 데모를 종료하려면 Ctrl+C를 누르세요."

  trap 'printf "\n"; info "종료 요청을 받았습니다."; stop_all; exit 0' HUP INT TERM
  while pid_is_running "${SERVER_PID_FILE}" 'uvicorn' && pid_is_running "${APP_PID_FILE}" 'expo'; do
    sleep 2
  done
  show_logs
  stop_all
  fail "딥소각 서버 또는 프론트가 예기치 않게 종료됐습니다. 위 로그를 확인해 주세요."
}

stop_all() {
  stop_managed_process "딥소각 프론트" "${APP_PID_FILE}" 'expo'
  stop_managed_process "딥소각 서버" "${SERVER_PID_FILE}" 'uvicorn'
  info "모델 API와 SearXNG을 종료합니다. 모델 볼륨은 삭제하지 않습니다."
  (
    cd "${MODEL_DIR}"
    docker compose -f docker-compose.yml -f docker-compose.searxng.yml down
  )
  show_status
}

show_logs() {
  info "모델 API·SearXNG 최근 로그"
  (cd "${MODEL_DIR}" && docker compose -f docker-compose.yml -f docker-compose.searxng.yml logs --no-color --tail=40) || true
  info "딥소각 서버 최근 로그: ${SERVER_LOG}"
  tail -n 40 "${SERVER_LOG}" 2>/dev/null || true
  info "딥소각 프론트 최근 로그: ${APP_LOG}"
  tail -n 40 "${APP_LOG}" 2>/dev/null || true
}

show_help() {
  cat <<'EOF'
딥소각 데모 통합 실행기

사용법:
  ./scripts/demo.sh start    전체 실행 후 브라우저 열기(Ctrl+C로 종료)
  ./scripts/demo.sh status   현재 상태 확인
  ./scripts/demo.sh logs     최근 로그 확인
  ./scripts/demo.sh stop     전체 종료
  ./scripts/demo.sh restart  전체 재시작
EOF
}

COMMAND="${1:-start}"
case "${COMMAND}" in
  start) start_all ;;
  status) show_status ;;
  logs) show_logs ;;
  stop) stop_all ;;
  restart) stop_all; start_all ;;
  help|-h|--help) show_help ;;
  *) show_help; fail "지원하지 않는 명령입니다: ${COMMAND}" ;;
esac
