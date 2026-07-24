"""data/raw, data/processed 아래 데이터셋별 폴더를 만든다. 실제 다운로드는 각 데이터셋의
승인 절차를 거쳐 수동으로 진행한 뒤, 여기 생성된 폴더에 압축을 풀어두면 된다."""

from pathlib import Path

DATASETS = ["ffpp", "celebdf", "kodf", "deeperforensics", "kface", "self_check"]

ROOT = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    for base in ("raw", "processed"):
        for name in DATASETS:
            path = ROOT / base / name
            path.mkdir(parents=True, exist_ok=True)
            (path / ".gitkeep").touch()
    print(f"완료: {ROOT} 아래 {len(DATASETS)}개 데이터셋 x raw/processed 폴더 생성")


if __name__ == "__main__":
    main()
