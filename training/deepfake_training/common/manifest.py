"""매니페스트(어떤 이미지가 어느 subject/영상/라벨에 속하는지) 스키마와
subject-level train/val 분할.

subject-level 분할이 중요한 이유: 같은 사람(subject_id)의 얼굴이 train과 val에
동시에 들어가면 모델이 "이 얼굴 자체를 기억"해서 실제보다 성능이 부풀려 보인다
(DATA_PLAN.md가 강조하는 부분). 여기서는 반드시 subject 단위로 통째로 나눈다.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from pathlib import Path

FIELDNAMES = ["path", "subject_id", "group_id", "label", "dataset", "split"]


@dataclass
class ManifestRow:
    path: str
    subject_id: str
    group_id: str  # 같은 영상/시퀀스에서 뽑힌 프레임들을 묶는 키 (video-level 집계용)
    label: int  # 0 = real, 1 = fake
    dataset: str
    split: str = ""  # "train" / "val" — assign_subject_level_split이 채운다

    def __post_init__(self) -> None:
        if self.label not in (0, 1):
            raise ValueError(f"label은 0 또는 1이어야 합니다: {self.label!r}")


def write_manifest(path: Path, rows: list[ManifestRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def read_manifest(path: Path) -> list[ManifestRow]:
    field_names = {f.name for f in fields(ManifestRow)}
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            kwargs = {k: v for k, v in raw.items() if k in field_names}
            kwargs["label"] = int(kwargs["label"])
            rows.append(ManifestRow(**kwargs))
    return rows


def assign_subject_level_split(
    rows: list[ManifestRow], *, val_fraction: float, seed: int
) -> list[ManifestRow]:
    """subject_id를 통째로 섞어서 train/val에 배정한다. 같은 subject_id는 항상
    같은 split에만 들어간다.
    """

    if not 0.0 < val_fraction < 1.0:
        raise ValueError(f"val_fraction은 0과 1 사이여야 합니다: {val_fraction!r}")

    by_subject: dict[str, list[ManifestRow]] = defaultdict(list)
    for row in rows:
        by_subject[row.subject_id].append(row)

    subjects = list(by_subject.keys())
    random.Random(seed).shuffle(subjects)

    target_val_count = round(len(rows) * val_fraction)
    val_subjects: set[str] = set()
    val_count = 0
    for subject in subjects:
        if val_count >= target_val_count:
            break
        val_subjects.add(subject)
        val_count += len(by_subject[subject])

    for row in rows:
        row.split = "val" if row.subject_id in val_subjects else "train"

    return rows


def assert_no_subject_leakage(rows: list[ManifestRow]) -> None:
    """train/val 사이에 subject_id가 겹치지 않는지 확인한다. 겹치면 raise."""

    train_subjects = {row.subject_id for row in rows if row.split == "train"}
    val_subjects = {row.subject_id for row in rows if row.split == "val"}
    overlap = train_subjects & val_subjects
    if overlap:
        raise AssertionError(f"train/val에 동시에 등장하는 subject_id 발견: {sorted(overlap)}")
