#!/usr/bin/env bash
# AI-Hub가 분할압축(파일명.zip.part1, .part2, ...)으로 내려준 파일을 하나로 합친다.
# aihub_download.sh로 받은 뒤 이 스크립트를 돌려야 zip으로 풀 수 있다.
#
# 사용법:
#   ./scripts/aihub_merge_zip_parts.sh [디렉터리=data/raw/kodf] [--clean] [--extract]
#
#   --clean   : 병합 성공 후 원본 .partN 파일을 삭제한다 (기본은 보존 — 대용량에서 병합이
#               잘못됐을 때 재다운로드를 피하기 위함).
#   --extract : 병합된 zip을 같은 이름의 폴더에 풀고, --clean이 같이 있으면 zip 자체도 지운다.
#
# 이미 <파일명>.zip이 존재하는 항목은 건너뛴다 (재실행해도 안전).
# .part1이 없는 파일(용량이 작아 분할되지 않은 zip)은 그대로 두고 손대지 않는다.
#
# Windows에서는 WSL 대신 Git Bash로 실행하는 걸 권장한다 — Git for Windows에 번들된
# MSYS2 coreutils가 find/sort -V/xargs/cat을 그대로 지원하고, WSL2와 달리 NTFS 경로를
# 네이티브로 다뤄 대용량 파일에서 I/O 페널티가 없다.

set -euo pipefail

DIR="data/raw/kodf"
CLEAN=false
EXTRACT=false

for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=true ;;
    --extract) EXTRACT=true ;;
    *) DIR="$arg" ;;
  esac
done

if [ ! -d "$DIR" ]; then
  echo "디렉터리를 찾을 수 없습니다: $DIR" >&2
  exit 1
fi

MERGED_COUNT=0

while IFS= read -r -d '' first_part; do
  base="${first_part%.part1}"

  if [ -f "$base" ]; then
    echo "건너뜀 (이미 병합됨): $base"
    continue
  fi

  part_dir="$(dirname "$first_part")"
  base_name="$(basename "$base")"

  find "$part_dir" -maxdepth 1 -name "${base_name}.part*" -print0 \
    | sort -zt'.' -k2V \
    | xargs -0 cat > "$base"

  size="$(du -h "$base" | cut -f1)"
  echo "병합 완료 -> $base ($size)"
  MERGED_COUNT=$((MERGED_COUNT + 1))

  if $EXTRACT; then
    extract_dir="${base%.zip}"
    unzip -q "$base" -d "$extract_dir"
    echo "압축 해제 -> $extract_dir"
  fi

  if $CLEAN; then
    find "$part_dir" -maxdepth 1 -name "${base_name}.part*" -delete
    echo "파트 파일 삭제 완료: ${base_name}.part*"
    if $EXTRACT; then
      rm "$base"
      echo "병합 zip 삭제 완료 (압축 해제본만 남김): $base"
    fi
  fi
done < <(find "$DIR" -name '*.zip.part1' -print0)

if [ "$MERGED_COUNT" -eq 0 ]; then
  echo "병합할 분할 zip을 찾지 못했습니다 (이미 병합됐거나, 분할되지 않은 zip만 있을 수 있습니다)."
fi
