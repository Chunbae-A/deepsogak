import tempfile
import unittest
from pathlib import Path

import torch

from deepfake_training.align_faces import align_manifest
from deepfake_training.common.manifest import assign_subject_level_split
from deepfake_training.dataset_torch import AlignedFaceDataset, split_rows

from .fakes import FakeAligner, make_synthetic_manifest


def _build_aligned_rows(root: Path, seed: int):
    raw_rows = make_synthetic_manifest(
        root / "raw", num_subjects_per_label=2, groups_per_subject=1, frames_per_group=1, seed=seed
    )
    rows = assign_subject_level_split(raw_rows, val_fraction=0.3, seed=seed)
    aligned_rows, _ = align_manifest(
        rows, FakeAligner(), aligned_face_size=32, frame_count=16, out_dir=root / "aligned"
    )
    return aligned_rows


class AlignedFaceDatasetTests(unittest.TestCase):
    def test_item_shape_and_label_dtype(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = _build_aligned_rows(Path(tmp), seed=5)
            dataset = AlignedFaceDataset(rows, input_size=48, mode="eval")

            image, label = dataset[0]

            self.assertEqual(tuple(image.shape), (3, 48, 48))
            self.assertEqual(image.dtype, torch.float32)
            self.assertIn(float(label), (0.0, 1.0))

    def test_eval_mode_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = _build_aligned_rows(Path(tmp), seed=6)
            dataset = AlignedFaceDataset(rows, input_size=48, mode="eval")

            first, _ = dataset[0]
            second, _ = dataset[0]

            self.assertTrue(torch.equal(first, second))

    def test_split_rows_separates_train_and_val(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = _build_aligned_rows(Path(tmp), seed=7)
            train_rows, val_rows = split_rows(rows)

            self.assertTrue(all(r.split == "train" for r in train_rows))
            self.assertTrue(all(r.split == "val" for r in val_rows))
            self.assertEqual(len(train_rows) + len(val_rows), len(rows))


if __name__ == "__main__":
    unittest.main()
