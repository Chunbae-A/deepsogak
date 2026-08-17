"""영상에서 프레임을 균등 간격으로 뽑아온다. FF++/Celeb-DF/KoDF 모두 mp4 원본이라
이 모듈로 정렬 전 원본 프레임(BGR uint8)을 얻은 뒤 align.py에 넘긴다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def sample_frame_indices(total_frames: int, count: int) -> list[int]:
    """영상 앞뒤 8%를 제외한 구간에서 count개를 균등 간격으로 뽑는다.
    (인트로/아웃트로 프레임은 조작 흔적이 약하거나 화면 전환으로 얼굴이 없는
    경우가 많아 제외한다.)
    """

    if total_frames <= 0:
        raise ValueError(f"total_frames는 양수여야 합니다: {total_frames!r}")
    if count <= 0:
        raise ValueError(f"count는 양수여야 합니다: {count!r}")

    margin = max(1, round(total_frames * 0.08))
    start = min(margin, total_frames - 1)
    end = max(start, total_frames - 1 - margin)

    if start >= end:
        return [start] * min(count, total_frames)

    step = (end - start) / max(1, count - 1) if count > 1 else 0
    indices = sorted({round(start + i * step) for i in range(count)})
    return indices


def extract_frames(video_path: Path, indices: list[int]) -> list[np.ndarray]:
    """지정한 인덱스의 프레임을 BGR uint8 배열로 반환한다. 읽기 실패한 프레임은
    건너뛴다 (반환 길이가 len(indices)보다 짧을 수 있음).
    """

    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise OSError(f"영상을 열 수 없습니다: {video_path}")

    frames: list[np.ndarray] = []
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if ok and frame is not None:
                frames.append(frame)
    finally:
        capture.release()

    return frames


def count_frames(video_path: Path) -> int:
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise OSError(f"영상을 열 수 없습니다: {video_path}")
    try:
        return int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
