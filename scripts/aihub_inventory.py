"""AI-Hub 데이터셋(기본값: KoDF/딥페이크 변조영상, datasetkey=55)의 파일 트리를 조회해
data/inventory/에 JSON·마크다운 인벤토리를 생성한다.

이 조회(-mode l)는 API 키 없이도 동작하는 공개 조회라 로그인 없이 실행 가능하다.
실제 파일 다운로드(-mode d)는 API 키가 필요하며 aihub_download.sh에서 다룬다.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AIHUBSHELL = REPO_ROOT / "scripts" / "aihubshell"
AIHUBSHELL_URL = "https://api.aihub.or.kr/api/aihubshell.do"

LEADING_RE = re.compile(r"^[\s│├└─]+")


def ensure_aihubshell() -> Path:
    if not AIHUBSHELL.exists():
        subprocess.run(
            ["curl", "-sL", "-o", str(AIHUBSHELL), AIHUBSHELL_URL], check=True
        )
        AIHUBSHELL.chmod(0o755)
    return AIHUBSHELL


def fetch_listing(dataset_key: str) -> str:
    shell = ensure_aihubshell()
    result = subprocess.run(
        ["bash", str(shell), "-mode", "l", "-datasetkey", dataset_key],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def parse(raw: str) -> list[dict]:
    entries = []
    stack: list[tuple[int, str]] = []
    for line in raw.splitlines():
        if "─" not in line:
            continue
        m = LEADING_RE.match(line)
        prefix = m.group(0) if m else ""
        depth = len(prefix)
        content = line[len(prefix):]
        if ".zip" in content and "|" in content:
            parts = [p.strip() for p in content.split("|")]
            name, size, filekey = parts[0], parts[1], parts[2]
            category = "/".join(n for _, n in stack)
            entries.append(
                {"category": category, "name": name, "size": size, "filekey": filekey}
            )
        else:
            name = content.strip()
            if not name:
                continue
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, name))
    return entries


def to_gb(size: str) -> float:
    num, unit = size.split()
    num = float(num)
    return num / 1024 if unit == "MB" else (num / 1024 / 1024 if unit == "KB" else num)


def write_outputs(entries: list[dict], dataset_key: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{dataset_key}_files.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total_gb = sum(to_gb(e["size"]) for e in entries)
    lines = [
        f"# AI-Hub datasetkey={dataset_key} 파일 인벤토리",
        "",
        f"- 총 파일 수: {len(entries)}개",
        f"- 총 용량: 약 {total_gb:.0f} GB (~{total_gb / 1024:.2f} TB)",
        "- 이 표는 `aihub_inventory.py`로 자동 생성됨. 전체를 받지 말고 "
        "`filekey` 컬럼을 골라 `aihub_download.sh`에 넘길 것.",
        "",
        "| category | name | size | filekey |",
        "|---|---|---|---|",
    ]
    for e in entries:
        lines.append(f"| {e['category']} | {e['name']} | {e['size']} | {e['filekey']} |")
    (out_dir / f"{dataset_key}_inventory.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset-key", default="55", help="AI-Hub datasetkey (기본: 55 = 딥페이크 변조영상/KoDF)")
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "inventory"))
    args = ap.parse_args()

    raw = fetch_listing(args.dataset_key)
    entries = parse(raw)
    if not entries:
        print("파일을 찾지 못했습니다 — datasetkey를 확인하세요.", file=sys.stderr)
        sys.exit(1)
    write_outputs(entries, args.dataset_key, Path(args.out_dir))
    print(f"datasetkey={args.dataset_key}: {len(entries)}개 파일 인벤토리 생성 완료")


if __name__ == "__main__":
    main()
