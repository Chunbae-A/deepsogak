"""KoDF(AI-Hub datasetkey=55) 어댑터 — 아직 실 데이터 구조를 못 봐서 스텁이다.

DATA_PLAN.md에 따르면 Training/Validation, 원본/변조영상/오디오, "탐지방해"(perturbation)
조건으로 세분화된 zip 102개(총 2.8TB)이고 라벨링 메타데이터(validate_meta.zip 등)가
별도로 딸려 있다고 되어 있지만, 정확한 내부 폴더/파일명 규칙과 메타데이터 스키마는
`scripts/aihub_download.sh` + `scripts/aihub_merge_zip_parts.sh`로 실제로 받아봐야
확인 가능하다.

여기서 잘못된 파싱 규칙을 미리 만들어두면 조용히 틀린 매니페스트를 만들 위험이 있으므로,
실 데이터가 준비될 때까지는 명확한 에러를 내고 멈춘다. KoDF를 실제로 받으면:
1. `data/raw/kodf` 아래 실제 폴더 구조를 확인한다.
2. 메타데이터 파일(라벨/피험자 ID)의 스키마를 확인한다.
3. 이 파일의 list_samples()를 그 구조에 맞게 채운다.
4. `python -m deepfake_training.build_manifest --dataset kodf --dry-run`으로 추출된
   subject_id가 말이 되는지 사람이 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from .base import RawSample

name = "kodf"


def list_samples(raw_dir: Path) -> list[RawSample]:
    raise NotImplementedError(
        "KoDF 어댑터는 아직 구현되지 않았습니다. 실제로 다운로드받은 data/raw/kodf 폴더 "
        "구조와 메타데이터 스키마를 확인한 뒤 datasets/kodf.py를 채워주세요. "
        "(DATA_PLAN.md의 '용도별 데이터셋 전체 지도' 참고)"
    )
