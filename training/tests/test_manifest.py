import tempfile
import unittest
from pathlib import Path

from deepfake_training.common.manifest import (
    ManifestRow,
    assert_no_subject_leakage,
    assign_subject_level_split,
    read_manifest,
    write_manifest,
)

from .fakes import make_synthetic_manifest


class AssignSubjectLevelSplitTests(unittest.TestCase):
    def test_no_subject_leakage_between_train_and_val(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = make_synthetic_manifest(Path(tmp), seed=1)
            rows = assign_subject_level_split(rows, val_fraction=0.3, seed=1)

            assert_no_subject_leakage(rows)  # raise 안 하면 통과

    def test_val_fraction_is_roughly_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = make_synthetic_manifest(Path(tmp), seed=2, groups_per_subject=1, frames_per_group=1)
            rows = assign_subject_level_split(rows, val_fraction=0.5, seed=2)

            val_count = sum(1 for r in rows if r.split == "val")
            train_count = sum(1 for r in rows if r.split == "train")

            self.assertGreater(val_count, 0)
            self.assertGreater(train_count, 0)
            self.assertEqual(val_count + train_count, len(rows))

    def test_rejects_invalid_val_fraction(self) -> None:
        with self.assertRaises(ValueError):
            assign_subject_level_split([], val_fraction=1.5, seed=0)


class ManifestRoundTripTests(unittest.TestCase):
    def test_write_then_read_preserves_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.csv"
            rows = [
                ManifestRow(
                    path="a.png", subject_id="s1", group_id="g1", label=0, dataset="d", split="train"
                ),
                ManifestRow(
                    path="b.png", subject_id="s2", group_id="g2", label=1, dataset="d", split="val"
                ),
            ]

            write_manifest(manifest_path, rows)
            loaded = read_manifest(manifest_path)

            self.assertEqual(loaded, rows)

    def test_invalid_label_raises(self) -> None:
        with self.assertRaises(ValueError):
            ManifestRow(path="a.png", subject_id="s1", group_id="g1", label=2, dataset="d")


if __name__ == "__main__":
    unittest.main()
