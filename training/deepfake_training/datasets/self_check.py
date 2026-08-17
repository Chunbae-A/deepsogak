"""팀원 본인 얼굴 자기 검증 셋 — 정성적 테스트 전용(DATA_PLAN.md 5번 표). 전부 실제
본인 촬영이라 label은 항상 0(real)이고, 딥페이크 판정에 대한 정량 지표(AUC 등)보다는
"내 얼굴로 돌려봤을 때 그럴듯한가"를 사람이 확인하는 용도다.

폴더 구조 규칙(팀에서 촬영본을 넣을 때 이 형태로 정리):

    <raw_dir>/<팀원이름 또는 코드>/*.{jpg,jpeg,png,mp4}

하나의 하위 폴더 = 한 사람 = 하나의 subject_id. 사진은 파일 하나가 곧 group_id(정지
이미지라 프레임 집계 대상이 아님), 영상은 파일명이 group_id(다른 데이터셋과 동일하게
프레임을 뽑아 정렬).
"""

from __future__ import annotations

from pathlib import Path

from .base import RawSample

name = "self_check"

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_VIDEO_SUFFIXES = {".mp4", ".mov"}


def list_samples(raw_dir: Path) -> list[RawSample]:
    samples: list[RawSample] = []

    if not raw_dir.is_dir():
        return samples

    for person_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        subject_id = person_dir.name
        for media_path in sorted(person_dir.iterdir()):
            suffix = media_path.suffix.lower()
            if suffix not in _IMAGE_SUFFIXES and suffix not in _VIDEO_SUFFIXES:
                continue
            samples.append(
                RawSample(
                    path=media_path,
                    subject_id=subject_id,
                    group_id=media_path.stem,
                    label=0,
                    dataset=name,
                )
            )

    return samples
