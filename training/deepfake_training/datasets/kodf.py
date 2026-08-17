"""KoDF(AI-Hub datasetkey=55) 어댑터.

실제로 다운로드해서 구조를 확인한 결과(2026-08-17, validate_meta.zip +
vaild_dfl_data.zip):

- **라벨 메타데이터**: `<raw_dir>` 아래 어딘가에 `원본영상_*메타데이터*.csv`,
  `변조영상_*메타데이터*.csv`가 있다(예: `라벨링데이터/validate_meta.zip`을 풀면
  나오는 `validate_meta_data/{원본영상,변조영상}_validation_메타데이터.csv`. Training
  split은 `train_meta.zip` 안에 `*_training_메타데이터.csv`로 이름만 다르고 컬럼은 동일할
  것으로 예상 — 실제로 받으면 확인할 것).
  - 원본영상 CSV 컬럼: `영상ID, UUID, 인물성별, 촬영장소, 촬영시작, 스크립트파일, 시나리오번호`
  - 변조영상 CSV 컬럼: `영상ID, 타겟영상, 타겟UUID, 소스UUID, 변조모델, 촬영시작, 인물성별`
  - 두 CSV 모두 UTF-8.
- **영상 파일**: 조작 방법(zip)마다 내부 최상위 폴더명이 다르다(예: DeepFaceLab 데이터는
  `dfl/<타겟UUID>/<타겟UUID>_<소스UUID>_<변조모델번호>_<seq>.mp4`). 방법마다 폴더 구조가
  달라 경로로 매칭하지 않고, **raw_dir 전체를 재귀적으로 훑어 각 mp4 파일명(영상ID)을
  메타데이터 CSV와 매칭**하는 방식을 쓴다 — 나중에 다른 조작방법 zip(fo/fsgan/dffs/audio 등)을
  추가로 풀어도 이 코드를 안 고쳐도 된다.

subject_id 규칙: 원본영상은 `UUID` 컬럼, 변조영상은 `타겟UUID` 컬럼(바탕 영상 정체성) —
FF++/Celeb-DF와 같은 논리로, 같은 정체성의 원본·조작본이 항상 같은 split에 들어가게 한다.

메타데이터에 없는 mp4(다른 split의 파일이 raw_dir 밑에 섞여 있는 경우 등)는 조용히
건너뛴다.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .base import RawSample

name = "kodf"


def _load_metadata(raw_dir: Path) -> dict[str, tuple[int, str]]:
    """영상ID(파일명) -> (label, subject_id) 매핑을 만든다."""

    lookup: dict[str, tuple[int, str]] = {}

    for csv_path in raw_dir.rglob("*원본영상*메타데이터*.csv"):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                lookup[row["영상ID"]] = (0, row["UUID"])

    for csv_path in raw_dir.rglob("*변조영상*메타데이터*.csv"):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                lookup[row["영상ID"]] = (1, row["타겟UUID"])

    return lookup


def list_samples(raw_dir: Path) -> list[RawSample]:
    lookup = _load_metadata(raw_dir)
    if not lookup:
        raise RuntimeError(
            f"{raw_dir} 아래에서 KoDF 라벨 메타데이터(원본영상/변조영상 CSV)를 찾지 못했습니다. "
            f"validate_meta.zip(또는 train_meta.zip)을 먼저 압축 해제했는지 확인하세요."
        )

    samples: list[RawSample] = []
    for video_path in raw_dir.rglob("*.mp4"):
        entry = lookup.get(video_path.name)
        if entry is None:
            continue  # 메타데이터에 없는 영상은 건너뜀
        label, subject_id = entry
        samples.append(
            RawSample(
                path=video_path,
                subject_id=subject_id,
                group_id=video_path.stem,
                label=label,
                dataset=name,
            )
        )

    return samples
