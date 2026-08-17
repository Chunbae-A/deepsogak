import tempfile
import unittest
from pathlib import Path

from deepfake_training.align_faces import align_manifest
from deepfake_training.common.manifest import assign_subject_level_split

from .fakes import FakeAligner, make_synthetic_manifest


class AlignManifestTests(unittest.TestCase):
    def test_produces_one_png_per_source_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_rows = make_synthetic_manifest(
                root / "raw", num_subjects_per_label=2, groups_per_subject=1, frames_per_group=1, seed=3
            )
            rows = assign_subject_level_split(raw_rows, val_fraction=0.3, seed=3)

            aligned_rows, skipped = align_manifest(
                rows,
                FakeAligner(),
                aligned_face_size=32,
                frame_count=16,
                out_dir=root / "aligned",
            )

            self.assertEqual(skipped, 0)
            self.assertEqual(len(aligned_rows), len(rows))
            for row in aligned_rows:
                self.assertTrue(Path(row.path).is_file())
                self.assertIn(row.split, {"train", "val"})

    def test_preserves_subject_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_rows = make_synthetic_manifest(
                root / "raw", num_subjects_per_label=1, groups_per_subject=1, frames_per_group=2, seed=4
            )
            rows = assign_subject_level_split(raw_rows, val_fraction=0.3, seed=4)

            aligned_rows, _ = align_manifest(
                rows, FakeAligner(), aligned_face_size=32, frame_count=16, out_dir=root / "aligned"
            )

            by_group = {row.group_id for row in rows}
            aligned_groups = {row.group_id for row in aligned_rows}
            self.assertEqual(by_group, aligned_groups)


if __name__ == "__main__":
    unittest.main()
