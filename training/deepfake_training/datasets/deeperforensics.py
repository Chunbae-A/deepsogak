"""DeeperForensics-1.0 어댑터 — 학습에는 안 쓰고 강건성(압축·블러·조명 왜곡) 테스트
전용이다(DATA_PLAN.md 참고). 실 데이터 구조를 아직 못 봐서 스텁이다 — KoDF와 같은
이유로, 잘못된 규칙을 미리 만들지 않고 명확히 멈춘다.
"""

from __future__ import annotations

from pathlib import Path

from .base import RawSample

name = "deeperforensics"


def list_samples(raw_dir: Path) -> list[RawSample]:
    raise NotImplementedError(
        "DeeperForensics 어댑터는 아직 구현되지 않았습니다. 실제로 다운로드받은 "
        "data/raw/deeperforensics 폴더 구조를 확인한 뒤 datasets/deeperforensics.py를 "
        "채워주세요. 이 데이터셋은 강건성 테스트 전용이라 train split에는 쓰지 않는다."
    )
