"""매니페스트 → 정렬(fake) → 학습(1 epoch, 배치 2개) → 평가 전체 체인이 CPU에서
기계적으로 동작하는지만 확인한다. 여기서 나오는 AUC/재현율 숫자는 무의미하다 —
합성 랜덤 이미지라 실제 성능과 아무 상관 없다. configs/smoke.yaml의 gate 기준을
절대 못 넘도록 설계돼 있어(min_val_video_groups=30) display_approved은 항상
false가 나온다(이 단계에선 별도로 확인하지 않는다 — calibrate.py는 태스크 #10에서
다룬다).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from deepfake_training.align_faces import align_manifest
from deepfake_training.common.manifest import assign_subject_level_split
from deepfake_training.dataset_torch import AlignedFaceDataset, split_rows
from deepfake_training.evaluate import evaluate
from deepfake_training.train import build_model, train_model

from .fakes import FakeAligner, make_synthetic_manifest


class SmokePipelineTests(unittest.TestCase):
    def test_full_chain_runs_on_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1. 매니페스트: label당 subject 2명, subject당 영상(group) 1개, 프레임 2장
            raw_rows = make_synthetic_manifest(
                root / "raw",
                num_subjects_per_label=2,
                groups_per_subject=1,
                frames_per_group=2,
                seed=42,
            )
            rows = assign_subject_level_split(raw_rows, val_fraction=0.3, seed=42)

            # 2. 정렬 (FakeAligner — cv2/insightface 불필요)
            aligned_rows, skipped = align_manifest(
                rows, FakeAligner(), aligned_face_size=48, frame_count=16, out_dir=root / "aligned"
            )
            self.assertEqual(skipped, 0)
            self.assertGreater(len(aligned_rows), 0)

            train_rows, val_rows = split_rows(aligned_rows)
            self.assertGreater(len(train_rows), 0)
            self.assertGreater(len(val_rows), 0)

            # 3. 학습 (1 epoch, 아주 작은 배치)
            train_dataset = AlignedFaceDataset(train_rows, input_size=64, mode="train")
            val_dataset = AlignedFaceDataset(val_rows, input_size=64, mode="eval")
            train_loader = DataLoader(train_dataset, batch_size=2, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=2, shuffle=False)

            device = torch.device("cpu")
            model = build_model("tf_efficientnet_b4", pretrained=False, num_classes=1)

            run_dir = root / "runs"
            history = train_model(
                model,
                train_loader,
                val_loader,
                epochs=1,
                lr=1e-3,
                weight_decay=0.0,
                device=device,
                run_dir=run_dir,
            )

            self.assertEqual(len(history["train_loss"]), 1)
            self.assertTrue((run_dir / "model.pt").is_file())

            # 4. 평가 — 예외 없이 두 스코프(frame/video_mean) 다 나오는지만 확인
            metrics = evaluate(model, val_rows, input_size=64, device=device)

            self.assertIn("frame", metrics)
            self.assertIn("video_mean", metrics)
            self.assertEqual(metrics["frame"]["n"], len(val_rows))
            self.assertGreater(metrics["video_mean"]["video_group_count"], 0)


if __name__ == "__main__":
    unittest.main()
