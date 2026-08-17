"""FaceForensics++ 어댑터.

폴더 구조는 공식 다운로드 스크립트(../../../scripts/download_ffpp_official.py)가
만드는 그대로를 가정한다:

    original_sequences/youtube/c23/videos/<id>.mp4                  (label=0)
    original_sequences/actors/c23/videos/<id>.mp4                   (label=0, DeepFakeDetection용 원본)
    manipulated_sequences/<Method>/c23/videos/<A>_<B>.mp4           (label=1)
    manipulated_sequences/DeepFakeDetection/c23/videos/<id>.mp4     (label=1)

<Method> ∈ {Deepfakes, Face2Face, FaceShifter, FaceSwap, NeuralTextures}.

subject_id 규칙: 조작 영상 파일명 "<A>_<B>.mp4"는 B의 원본 영상에 A의 얼굴을 입힌
것(공식 스크립트가 pair를 뒤집어서도 저장하므로 A/B 둘 다 등장함). B가 실제
바탕 영상(배경·움직임)의 정체성이므로 subject_id = B로 둔다 — 이러면 같은 바탕
영상에서 나온 원본과 조작본이 항상 같은 split에 들어간다. DeepFakeDetection
카테고리는 파일명 규칙이 달라(원본 스크립트가 pair 조인 없이 그대로 씀) 확신이
없다 — 실 데이터로 --dry-run 결과를 반드시 눈으로 확인할 것.
"""

from __future__ import annotations

from pathlib import Path

from .base import RawSample

name = "ffpp"

_COMPRESSION = "c23"

_ORIGINAL_DIRS = [
    ("original_sequences/youtube", 0),
    ("original_sequences/actors", 0),
]

_MANIPULATED_DIRS = [
    ("manipulated_sequences/Deepfakes", 1),
    ("manipulated_sequences/Face2Face", 1),
    ("manipulated_sequences/FaceShifter", 1),
    ("manipulated_sequences/FaceSwap", 1),
    ("manipulated_sequences/NeuralTextures", 1),
    ("manipulated_sequences/DeepFakeDetection", 1),
]


def _subject_id_for_manipulated(stem: str) -> str:
    parts = stem.split("_")
    if len(parts) == 2:
        return parts[1]  # B (바탕 영상 정체성)
    return stem  # DeepFakeDetection 등 pair 규칙이 아닌 경우 그대로


def list_samples(raw_dir: Path) -> list[RawSample]:
    samples: list[RawSample] = []

    for rel_dir, label in _ORIGINAL_DIRS:
        video_dir = raw_dir / rel_dir / _COMPRESSION / "videos"
        if not video_dir.is_dir():
            continue
        for video_path in sorted(video_dir.glob("*.mp4")):
            stem = video_path.stem
            samples.append(
                RawSample(
                    path=video_path,
                    subject_id=stem,
                    group_id=stem,
                    label=label,
                    dataset=name,
                )
            )

    for rel_dir, label in _MANIPULATED_DIRS:
        video_dir = raw_dir / rel_dir / _COMPRESSION / "videos"
        if not video_dir.is_dir():
            continue
        for video_path in sorted(video_dir.glob("*.mp4")):
            stem = video_path.stem
            samples.append(
                RawSample(
                    path=video_path,
                    subject_id=_subject_id_for_manipulated(stem),
                    group_id=stem,
                    label=label,
                    dataset=name,
                )
            )

    return samples
