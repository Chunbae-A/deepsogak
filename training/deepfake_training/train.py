"""timm EfficientNet-B4(ImageNet 사전학습)를 정렬된 얼굴 이미지로 파인튜닝한다.

사용법:
    python -m deepfake_training.train --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import timm
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from .common.manifest import ManifestRow, read_manifest
from .config import Config
from .dataset_torch import AlignedFaceDataset, split_rows


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def resolve_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(requested)


def build_model(arch: str, *, pretrained: bool, num_classes: int) -> nn.Module:
    return timm.create_model(arch, pretrained=pretrained, num_classes=num_classes)


def load_manifests(paths: list[Path]) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    for path in paths:
        rows.extend(read_manifest(path))
    return rows


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    *,
    epochs: int,
    lr: float,
    weight_decay: float,
    device: torch.device,
    run_dir: Path | None = None,
) -> dict[str, list[float]]:
    """훈련 루프의 핵심. 스모크 테스트에서 작은 합성 로더로 바로 호출할 수 있도록
    argparse/설정 파일과 분리해뒀다.
    """

    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    criterion = nn.BCEWithLogitsLoss()

    history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}

    for epoch in range(epochs):
        model.train()
        train_losses = []
        for images, labels in tqdm(train_loader, desc=f"epoch {epoch + 1}/{epochs} train"):
            images = images.to(device)
            labels = labels.to(device).unsqueeze(1)

            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for images, labels in val_loader:
                images = images.to(device)
                labels = labels.to(device).unsqueeze(1)
                logits = model(images)
                val_losses.append(criterion(logits, labels).item())

        train_loss = sum(train_losses) / max(1, len(train_losses))
        val_loss = sum(val_losses) / max(1, len(val_losses)) if val_losses else float("nan")
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        print(f"epoch {epoch + 1}/{epochs}: train_loss={train_loss:.4f} val_loss={val_loss:.4f}")

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), run_dir / "model.pt")

    return history


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent.parent / "configs" / "default.yaml")
    parser.add_argument(
        "--manifests",
        type=Path,
        nargs="+",
        default=None,
        help="정렬 매니페스트 CSV 경로들. 생략하면 config의 datasets.train 목록 기준으로 찾는다.",
    )
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args(argv)

    config = Config.load(args.config)
    set_seed(config.train.seed)

    manifest_paths = args.manifests or [
        config.data_root / "processed" / "manifests" / f"{name}_aligned.csv"
        for name in config.datasets.train
    ]
    rows = load_manifests(manifest_paths)
    train_rows, val_rows = split_rows(rows)

    train_dataset = AlignedFaceDataset(train_rows, input_size=config.model.input_size, mode="train")
    val_dataset = AlignedFaceDataset(val_rows, input_size=config.model.input_size, mode="eval")

    train_loader = DataLoader(
        train_dataset,
        batch_size=config.train.batch_size,
        shuffle=True,
        num_workers=config.train.num_workers,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=config.train.batch_size,
        shuffle=False,
        num_workers=config.train.num_workers,
    )

    device = resolve_device(args.device)
    model = build_model(
        config.model.arch, pretrained=config.model.pretrained, num_classes=config.model.num_classes
    )

    train_model(
        model,
        train_loader,
        val_loader,
        epochs=config.train.epochs,
        lr=config.train.lr,
        weight_decay=config.train.weight_decay,
        device=device,
        run_dir=config.run_dir,
    )


if __name__ == "__main__":
    main()
