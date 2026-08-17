"""data/raw/<dataset>를 훑어 subject-level split이 붙은 매니페스트 CSV를 만든다.

사용법:
    python -m deepfake_training.build_manifest --dataset ffpp --dry-run
    python -m deepfake_training.build_manifest --dataset ffpp --config configs/default.yaml
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .common.manifest import (
    ManifestRow,
    assert_no_subject_leakage,
    assign_subject_level_split,
    write_manifest,
)
from .config import Config
from .datasets import celebdf, deeperforensics, ffpp, kodf, self_check
from .datasets.base import RawSample

DATASET_ADAPTERS = {
    ffpp.name: ffpp,
    celebdf.name: celebdf,
    kodf.name: kodf,
    deeperforensics.name: deeperforensics,
    self_check.name: self_check,
}


def _to_manifest_row(sample: RawSample) -> ManifestRow:
    return ManifestRow(
        path=str(sample.path),
        subject_id=sample.subject_id,
        group_id=sample.group_id,
        label=sample.label,
        dataset=sample.dataset,
    )


def build_manifest(
    dataset: str,
    data_root: Path,
    *,
    val_fraction: float,
    seed: int,
    raw_dir: Path | None = None,
) -> list[ManifestRow]:
    if dataset not in DATASET_ADAPTERS:
        raise ValueError(
            f"알 수 없는 데이터셋: {dataset!r} (선택 가능: {sorted(DATASET_ADAPTERS)})"
        )

    adapter = DATASET_ADAPTERS[dataset]
    raw_dir = raw_dir if raw_dir is not None else data_root / "raw" / dataset
    samples = adapter.list_samples(raw_dir)

    if not samples:
        raise RuntimeError(
            f"{raw_dir} 아래에서 샘플을 하나도 찾지 못했습니다. 폴더 구조가 어댑터가 "
            f"기대하는 형태인지 확인하세요."
        )

    rows = [_to_manifest_row(s) for s in samples]
    rows = assign_subject_level_split(rows, val_fraction=val_fraction, seed=seed)
    assert_no_subject_leakage(rows)
    return rows


def _print_summary(dataset: str, rows: list[ManifestRow]) -> None:
    label_counts = Counter(row.label for row in rows)
    split_counts = Counter(row.split for row in rows)
    subject_count = len({row.subject_id for row in rows})

    print(f"[{dataset}] 샘플 {len(rows)}개, subject {subject_count}명")
    print(f"  label: real(0)={label_counts.get(0, 0)}, fake(1)={label_counts.get(1, 0)}")
    print(f"  split: {dict(split_counts)}")
    print("  subject_id 미리보기 (앞 10개):")
    seen: list[str] = []
    for row in rows:
        if row.subject_id not in seen:
            seen.append(row.subject_id)
        if len(seen) >= 10:
            break
    for subject_id in seen:
        example = next(r for r in rows if r.subject_id == subject_id)
        print(f"    subject_id={subject_id!r} <- {Path(example.path).name}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=sorted(DATASET_ADAPTERS))
    parser.add_argument("--config", type=Path, default=Path(__file__).parent.parent / "configs" / "default.yaml")
    parser.add_argument("--data-root", type=Path, default=None, help="config의 data_root를 덮어쓴다")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="원본 폴더를 data_root/raw/<dataset> 관례 대신 직접 지정한다 "
        "(예: 외장 드라이브에 다른 구조로 받아둔 경우)",
    )
    parser.add_argument("--val-fraction", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="아무것도 쓰지 않고 subject_id 추출 결과만 사람이 확인할 수 있게 출력한다",
    )
    args = parser.parse_args(argv)

    config = Config.load(args.config)
    data_root = args.data_root or config.data_root
    val_fraction = args.val_fraction if args.val_fraction is not None else config.train.val_fraction
    seed = args.seed if args.seed is not None else config.train.seed

    rows = build_manifest(
        args.dataset, data_root, val_fraction=val_fraction, seed=seed, raw_dir=args.raw_dir
    )
    _print_summary(args.dataset, rows)

    if args.dry_run:
        print("\n--dry-run 이라 매니페스트 파일은 쓰지 않았습니다.")
        return

    out_path = args.out or (data_root / "processed" / "manifests" / f"{args.dataset}.csv")
    write_manifest(out_path, rows)
    print(f"\n매니페스트 저장: {out_path}")


if __name__ == "__main__":
    main()
