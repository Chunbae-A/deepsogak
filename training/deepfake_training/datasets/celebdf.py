"""Celeb-DF v2 어댑터.

폴더 구조(공식/Kaggle 미러 공통):

    Celeb-real/id<N>_<seq>.mp4          (label=0)
    YouTube-real/<seq>.mp4              (label=0, 정체성 표시 없는 별개 유튜버 영상)
    Celeb-synthesis/id<A>_id<B>_<seq>.mp4  (label=1)

subject_id 규칙: Celeb-synthesis는 "id<A>가 id<B>의 바탕 영상에 합성된" 영상이므로
바탕 정체성인 B를 subject_id로 쓴다(FF++와 동일한 논리 — Celeb-real/id<B>_*와
같은 split에 들어가게). YouTube-real은 정체성 코드가 없어 파일명 자체를
subject_id로 쓴다(영상마다 다른 사람일 가능성이 높아, 굳이 하나로 묶지 않는
쪽이 안전).
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import RawSample

name = "celebdf"

_ID_PREFIX_RE = re.compile(r"^id(\d+)_")
_SYNTHESIS_RE = re.compile(r"^id(\d+)_id(\d+)_")


def _real_subject_id(stem: str) -> str:
    match = _ID_PREFIX_RE.match(stem)
    if match:
        return f"id{match.group(1)}"
    return stem  # YouTube-real: 정체성 코드가 없음


def _synthesis_subject_id(stem: str) -> str:
    match = _SYNTHESIS_RE.match(stem)
    if match:
        return f"id{match.group(2)}"  # B (바탕 영상 정체성)
    return stem


def list_samples(raw_dir: Path) -> list[RawSample]:
    samples: list[RawSample] = []

    for sub_dir, subject_fn, label in [
        ("Celeb-real", _real_subject_id, 0),
        ("YouTube-real", _real_subject_id, 0),
        ("Celeb-synthesis", _synthesis_subject_id, 1),
    ]:
        video_dir = raw_dir / sub_dir
        if not video_dir.is_dir():
            continue
        for video_path in sorted(video_dir.glob("*.mp4")):
            stem = video_path.stem
            samples.append(
                RawSample(
                    path=video_path,
                    subject_id=subject_fn(stem),
                    group_id=stem,
                    label=label,
                    dataset=name,
                )
            )

    return samples
