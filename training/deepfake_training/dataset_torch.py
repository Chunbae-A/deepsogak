"""정렬된 얼굴 PNG 매니페스트를 읽는 torch Dataset.

train 모드는 좌우 반전 같은 가벼운 증강을 넣고, eval 모드는 결정적(같은 입력이면
항상 같은 텐서)으로 만든다 — 검증·평가 지표가 매번 흔들리지 않게 하기 위함.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

from .common.manifest import ManifestRow

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def _build_transform(input_size: int, mode: Literal["train", "eval"]) -> transforms.Compose:
    ops: list = [transforms.Resize((input_size, input_size))]
    if mode == "train":
        ops.append(transforms.RandomHorizontalFlip(p=0.5))
    ops.append(transforms.ToTensor())
    ops.append(transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD))
    return transforms.Compose(ops)


class AlignedFaceDataset(Dataset):
    def __init__(
        self,
        rows: list[ManifestRow],
        *,
        input_size: int,
        mode: Literal["train", "eval"],
    ) -> None:
        self.rows = rows
        self.transform = _build_transform(input_size, mode)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        image = Image.open(row.path).convert("RGB")
        tensor = self.transform(image)
        return tensor, np.float32(row.label)


def split_rows(rows: list[ManifestRow]) -> tuple[list[ManifestRow], list[ManifestRow]]:
    train_rows = [r for r in rows if r.split == "train"]
    val_rows = [r for r in rows if r.split == "val"]
    return train_rows, val_rows
