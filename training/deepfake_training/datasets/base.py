"""데이터셋별 어댑터가 공통으로 만족해야 하는 인터페이스.

각 어댑터는 원본 폴더(data_root/raw/<name>/...)를 훑어 RawSample 목록을 만든다.
subject_id 규칙은 데이터셋마다 다르고, 실제 데이터를 눈으로 봐야 확신할 수 있는
부분이 있어(특히 KoDF·DeeperForensics), build_manifest.py --dry-run으로 사람이
먼저 확인하는 걸 전제로 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RawSample:
    path: Path
    subject_id: str  # train/val 분할이 절대 갈라놓으면 안 되는 단위 (동일 인물/동일 원본 영상)
    group_id: str  # video-level 집계용 — 보통 파일(영상) 하나당 하나
    label: int  # 0 = real, 1 = fake
    dataset: str


class DatasetAdapter(Protocol):
    name: str

    def list_samples(self, raw_dir: Path) -> list[RawSample]:
        """raw_dir(예: data_root/raw/ffpp) 아래를 훑어 RawSample 목록을 만든다."""
        ...
