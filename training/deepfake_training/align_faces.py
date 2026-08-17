"""매니페스트의 각 영상/이미지에서 얼굴을 뽑아 정렬한 뒤 PNG로 저장하고, 그 PNG를
가리키는 새 매니페스트(정렬 매니페스트)를 만든다.

사용법:
    python -m deepfake_training.align_faces --manifest data/processed/manifests/ffpp.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .common.align import FaceAligner, InsightFaceAligner
from .common.manifest import ManifestRow, read_manifest, write_manifest
from .common.video_frames import count_frames, extract_frames, sample_frame_indices
from .config import Config

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_VIDEO_SUFFIXES = {".mp4", ".mov"}


def _load_frames(path: Path, *, frame_count: int) -> list[np.ndarray]:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        # PIL로 읽는다(이미지 경로는 cv2 없이도 동작하게) — 영상 디코딩만 cv2가 꼭 필요하다.
        from PIL import Image

        rgb = np.asarray(Image.open(path).convert("RGB"))
        return [np.ascontiguousarray(rgb[..., ::-1])]  # RGB -> BGR

    if suffix in _VIDEO_SUFFIXES:
        total = count_frames(path)
        if total <= 0:
            return []
        indices = sample_frame_indices(total, frame_count)
        return extract_frames(path, indices)

    raise ValueError(f"지원하지 않는 파일 형식: {path}")


def align_manifest(
    rows: list[ManifestRow],
    aligner: FaceAligner,
    *,
    aligned_face_size: int,
    frame_count: int,
    out_dir: Path,
) -> tuple[list[ManifestRow], int]:
    """정렬된 얼굴 PNG를 out_dir 아래에 쓰고, 그걸 가리키는 새 ManifestRow 목록을
    반환한다. 두 번째 반환값은 얼굴을 못 찾아 건너뛴 프레임 수.
    """

    from PIL import Image

    aligned_rows: list[ManifestRow] = []
    skipped = 0

    for row in rows:
        source_path = Path(row.path)
        frames = _load_frames(source_path, frame_count=frame_count)

        for frame_index, frame_bgr in enumerate(frames):
            result = aligner.align(frame_bgr, aligned_size=aligned_face_size)
            if result is None:
                skipped += 1
                continue

            dest_dir = out_dir / row.dataset / row.split / str(row.label)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / f"{row.group_id}_{frame_index:03d}.png"

            rgb = result.aligned_bgr[..., ::-1]
            Image.fromarray(rgb).save(dest_path)

            aligned_rows.append(
                ManifestRow(
                    path=str(dest_path),
                    subject_id=row.subject_id,
                    group_id=row.group_id,
                    label=row.label,
                    dataset=row.dataset,
                    split=row.split,
                )
            )

    return aligned_rows, skipped


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent.parent / "configs" / "default.yaml")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args(argv)

    config = Config.load(args.config)
    rows = read_manifest(args.manifest)
    out_dir = args.out_dir or (config.data_root / "processed" / "aligned")

    aligner = InsightFaceAligner(device=args.device)
    aligned_rows, skipped = align_manifest(
        rows,
        aligner,
        aligned_face_size=config.model.aligned_face_size,
        frame_count=config.video.frame_count,
        out_dir=out_dir,
    )

    aligned_manifest_path = args.manifest.with_name(args.manifest.stem + "_aligned.csv")
    write_manifest(aligned_manifest_path, aligned_rows)

    print(f"정렬된 얼굴 {len(aligned_rows)}개, 얼굴 못 찾아 건너뜀 {skipped}개")
    print(f"정렬 매니페스트 저장: {aligned_manifest_path}")


if __name__ == "__main__":
    main()
