"""configs/*.yaml을 읽어 학습 파이프라인 전체가 공유하는 설정 객체를 만든다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ModelConfig:
    arch: str
    pretrained: bool
    num_classes: int
    aligned_face_size: int
    input_size: int


@dataclass(frozen=True)
class TrainConfig:
    epochs: int
    batch_size: int
    lr: float
    weight_decay: float
    num_workers: int
    seed: int
    val_fraction: float


@dataclass(frozen=True)
class VideoConfig:
    frame_count: int
    minimum_valid_frames: int


@dataclass(frozen=True)
class GateConfig:
    min_auc: float
    min_recall_at_threshold: float
    min_val_video_groups: int


@dataclass(frozen=True)
class DatasetsConfig:
    train: list[str]
    test: list[str]


@dataclass(frozen=True)
class Config:
    data_root: Path
    run_dir: Path
    model: ModelConfig
    train: TrainConfig
    video: VideoConfig
    gate: GateConfig
    datasets: DatasetsConfig

    @classmethod
    def load(cls, path: Path) -> "Config":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        config_dir = path.parent

        return cls(
            data_root=(config_dir / payload["data_root"]).resolve(),
            run_dir=(config_dir / payload["run_dir"]).resolve(),
            model=ModelConfig(**payload["model"]),
            train=TrainConfig(**payload["train"]),
            video=VideoConfig(**payload["video"]),
            gate=GateConfig(**payload["gate"]),
            datasets=DatasetsConfig(**payload["datasets"]),
        )
