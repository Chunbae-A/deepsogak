"""검증셋으로 모델을 평가한다. 프레임 단위와 영상(그룹) 단위 두 가지 기준을 낸다 —
영상 단위는 같은 영상에서 뽑은 여러 프레임의 점수를 평균 낸 것으로, 실제 서비스가
영상을 판단할 때와 더 가까운 지표다.

사용법:
    python -m deepfake_training.evaluate --config configs/default.yaml --checkpoint runs/model.pt
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import timm
import torch
from torch.utils.data import DataLoader

from .common.manifest import ManifestRow, read_manifest
from .config import Config
from .dataset_torch import AlignedFaceDataset
from .train import resolve_device


def predict_scores(
    model: torch.nn.Module,
    rows: list[ManifestRow],
    *,
    input_size: int,
    device: torch.device,
    batch_size: int = 32,
) -> np.ndarray:
    """rows 순서와 정확히 같은 순서로 시그모이드 점수를 반환한다(shuffle 없음)."""

    dataset = AlignedFaceDataset(rows, input_size=input_size, mode="eval")
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)

    model.eval()
    scores: list[np.ndarray] = []
    with torch.no_grad():
        for images, _ in loader:
            logits = model(images.to(device))
            probs = torch.sigmoid(logits).squeeze(1).cpu().numpy()
            scores.append(probs)

    return np.concatenate(scores) if scores else np.array([], dtype=np.float32)


def frame_level_metrics(scores: np.ndarray, labels: np.ndarray, *, threshold: float = 0.5) -> dict:
    from sklearn.metrics import precision_score, recall_score, roc_auc_score

    preds = (scores >= threshold).astype(int)
    auc = roc_auc_score(labels, scores) if len(set(labels.tolist())) > 1 else float("nan")

    return {
        "n": int(len(labels)),
        "auc": float(auc),
        "recall": float(recall_score(labels, preds, zero_division=0)),
        "precision": float(precision_score(labels, preds, zero_division=0)),
        "threshold": threshold,
    }


def aggregate_video_scores(
    rows: list[ManifestRow], scores: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """같은 group_id(영상)의 프레임 점수를 평균낸다 — faceguard_api가 16프레임
    평균으로 영상을 판단하는 것과 같은 원리."""

    by_group: dict[str, list[float]] = defaultdict(list)
    group_label: dict[str, int] = {}
    for row, score in zip(rows, scores):
        by_group[row.group_id].append(float(score))
        group_label[row.group_id] = row.label

    group_ids = sorted(by_group)
    video_scores = np.array([np.mean(by_group[g]) for g in group_ids], dtype=np.float32)
    video_labels = np.array([group_label[g] for g in group_ids], dtype=np.int64)
    return video_scores, video_labels, group_ids


def evaluate(
    model: torch.nn.Module,
    rows: list[ManifestRow],
    *,
    input_size: int,
    device: torch.device,
    threshold: float = 0.5,
) -> dict:
    scores = predict_scores(model, rows, input_size=input_size, device=device)
    labels = np.array([row.label for row in rows], dtype=np.int64)

    frame_metrics = frame_level_metrics(scores, labels, threshold=threshold)

    video_scores, video_labels, group_ids = aggregate_video_scores(rows, scores)
    video_metrics = frame_level_metrics(video_scores, video_labels, threshold=threshold)
    video_metrics["video_group_count"] = len(group_ids)

    return {"frame": frame_metrics, "video_mean": video_metrics}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent.parent / "configs" / "default.yaml")
    parser.add_argument("--manifests", type=Path, nargs="+", default=None)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args(argv)

    config = Config.load(args.config)

    manifest_paths = args.manifests or [
        config.data_root / "processed" / "manifests" / f"{name}_aligned.csv"
        for name in config.datasets.train
    ]
    rows: list[ManifestRow] = []
    for path in manifest_paths:
        rows.extend(read_manifest(path))
    val_rows = [r for r in rows if r.split == "val"]

    device = resolve_device(args.device)
    model = timm.create_model(
        config.model.arch, pretrained=False, num_classes=config.model.num_classes
    )
    model.load_state_dict(torch.load(args.checkpoint, map_location=device))
    model.to(device)

    metrics = evaluate(model, val_rows, input_size=config.model.input_size, device=device, threshold=args.threshold)

    print("[frame-level]")
    print(f"  n={metrics['frame']['n']} auc={metrics['frame']['auc']:.4f} "
          f"recall={metrics['frame']['recall']:.4f} precision={metrics['frame']['precision']:.4f}")
    print("[video-mean-level]")
    print(f"  video_groups={metrics['video_mean']['video_group_count']} "
          f"auc={metrics['video_mean']['auc']:.4f} recall={metrics['video_mean']['recall']:.4f} "
          f"precision={metrics['video_mean']['precision']:.4f}")

    gate = config.gate
    passes_gate = (
        metrics["video_mean"]["video_group_count"] >= gate.min_val_video_groups
        and metrics["video_mean"]["auc"] >= gate.min_auc
        and metrics["video_mean"]["recall"] >= gate.min_recall_at_threshold
    )
    print(f"\nGate 통과 여부(min_auc={gate.min_auc}, min_recall={gate.min_recall_at_threshold}, "
          f"min_val_video_groups={gate.min_val_video_groups}): {passes_gate}")


if __name__ == "__main__":
    main()
