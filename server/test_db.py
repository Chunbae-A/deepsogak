import tempfile
import threading
import unittest
from pathlib import Path

import db


class DbTestCase(unittest.TestCase):
    def setUp(self):
        # db._DB_PATH는 모듈 전역 상태라, 여기서 임시 파일로 바꾸면 같은
        # 프로세스에서 나중에 실행되는 다른 테스트 모듈(test_main.py 등)에
        # 그대로 새어나갈 수 있다. 원래 값을 저장해뒀다가 tearDown에서
        # 되돌린다(unittest discover로 여러 파일을 한 번에 돌릴 때를 대비).
        self._original_db_path = db._DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        db.init_db(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()
        db._DB_PATH = self._original_db_path

    def test_create_and_get_job_round_trips_all_fields(self):
        db.create_job(
            "job1",
            original_path=Path("/tmp/original.jpg"),
            protected_path=Path("/tmp/protected.jpg"),
            sha256="abc123",
            phash="deadbeef",
            created_at=1000.0,
            deepbaeksin_applied=True,
            deepbaeksin_meta={"reason": "ok", "similarityAfter": 0.9},
        )
        job = db.get_job("job1")
        self.assertIsNotNone(job)
        self.assertEqual(job["originalPath"], Path("/tmp/original.jpg"))
        self.assertEqual(job["protectedPath"], Path("/tmp/protected.jpg"))
        self.assertEqual(job["sha256"], "abc123")
        self.assertEqual(job["phash"], "deadbeef")
        self.assertEqual(job["createdAt"], 1000.0)
        self.assertTrue(job["deepbaeksinApplied"])
        self.assertEqual(job["deepbaeksinMeta"]["reason"], "ok")

    def test_get_job_missing_returns_none(self):
        self.assertIsNone(db.get_job("does-not-exist"))

    def test_get_latest_completed_job_returns_most_recent_by_created_at(self):
        db.create_job(
            "older", original_path=Path("a"), protected_path=Path("a"),
            sha256="a", phash="a", created_at=100.0,
        )
        db.create_job(
            "newer", original_path=Path("b"), protected_path=Path("b"),
            sha256="b", phash="b", created_at=200.0,
        )
        latest = db.get_latest_completed_job()
        self.assertIsNotNone(latest)
        job_id, job = latest
        self.assertEqual(job_id, "newer")
        self.assertEqual(job["sha256"], "b")

    def test_get_latest_completed_job_empty_returns_none(self):
        self.assertIsNone(db.get_latest_completed_job())

    def test_owner_id_defaults_to_none_and_round_trips(self):
        # #77 스캐폴딩: owner_id를 안 넘기면 기존과 동일하게 NULL로 저장된다.
        db.create_job(
            "no-owner", original_path=Path("a"), protected_path=Path("a"),
            sha256="a", phash="a", created_at=1.0,
        )
        self.assertIsNone(db.get_job("no-owner")["ownerId"])

        db.create_job(
            "with-owner", original_path=Path("b"), protected_path=Path("b"),
            sha256="b", phash="b", created_at=2.0, owner_id="user-1",
        )
        self.assertEqual(db.get_job("with-owner")["ownerId"], "user-1")

    def test_get_latest_completed_job_without_owner_filter_ignores_owner_id(self):
        # owner_id를 안 넘기면(기본값 None) 지금까지처럼 owner_id와 무관하게
        # DB 전체에서 가장 최근 job을 돌려준다 — 기존 단일 사용자 동작을
        # 그대로 유지한다는 게 이 테스트의 핵심.
        db.create_job(
            "user-a-job", original_path=Path("a"), protected_path=Path("a"),
            sha256="a", phash="a", created_at=100.0, owner_id="user-a",
        )
        db.create_job(
            "user-b-job", original_path=Path("b"), protected_path=Path("b"),
            sha256="b", phash="b", created_at=200.0, owner_id="user-b",
        )
        latest = db.get_latest_completed_job()
        self.assertEqual(latest[0], "user-b-job")

    def test_get_latest_completed_job_with_owner_filter_scopes_to_that_owner(self):
        db.create_job(
            "user-a-job", original_path=Path("a"), protected_path=Path("a"),
            sha256="a", phash="a", created_at=100.0, owner_id="user-a",
        )
        db.create_job(
            "user-b-job", original_path=Path("b"), protected_path=Path("b"),
            sha256="b", phash="b", created_at=200.0, owner_id="user-b",
        )
        latest = db.get_latest_completed_job(owner_id="user-a")
        self.assertEqual(latest[0], "user-a-job")

    def test_count_completed_jobs(self):
        self.assertEqual(db.count_completed_jobs(), 0)
        db.create_job("a", original_path=Path("a"), protected_path=Path("a"), sha256="a", phash="a", created_at=1.0)
        db.create_job("b", original_path=Path("b"), protected_path=Path("b"), sha256="b", phash="b", created_at=2.0)
        self.assertEqual(db.count_completed_jobs(), 2)

    def test_manual_reports_preserve_insertion_order(self):
        db.add_manual_report("https://example.com/1", created_at=1.0)
        db.add_manual_report("https://example.com/2", created_at=2.0)
        reports = db.list_manual_reports()
        self.assertEqual([r["url"] for r in reports], [
            "https://example.com/1",
            "https://example.com/2",
        ])

    def test_scan_cache_missing_returns_none_then_set_and_get(self):
        self.assertIsNone(db.get_scan_cache("job1"))
        matches = [{"similarity": 90, "source_type": "검색엔진"}]
        db.set_scan_cache("job1", matches)
        self.assertEqual(db.get_scan_cache("job1"), matches)

    def test_scan_cache_upsert_overwrites(self):
        db.set_scan_cache("job1", [{"a": 1}])
        db.set_scan_cache("job1", [{"a": 2}])
        self.assertEqual(db.get_scan_cache("job1"), [{"a": 2}])

    def test_confirmed_keep_ids_defaults_empty_and_round_trips(self):
        self.assertEqual(db.get_confirmed_keep_ids(), [])
        db.set_confirmed_keep_ids(["c1", "c3"])
        self.assertEqual(db.get_confirmed_keep_ids(), ["c1", "c3"])

    def test_draft_overrides_defaults_none_and_round_trips(self):
        self.assertIsNone(db.get_draft_overrides())
        fields = [{"key": "postUrl", "label": "게시물 URL", "value": "x"}]
        db.set_draft_overrides(fields)
        self.assertEqual(db.get_draft_overrides(), fields)
        db.set_draft_overrides(None)
        self.assertIsNone(db.get_draft_overrides())

    def test_report_count_increments_and_persists(self):
        self.assertEqual(db.get_report_count(), 0)
        self.assertEqual(db.increment_report_count(), 1)
        self.assertEqual(db.increment_report_count(), 2)
        self.assertEqual(db.get_report_count(), 2)

    def test_state_survives_reinit_on_same_file_path(self):
        """서버 재시작을 흉내낸다: 같은 경로로 init_db를 다시 불러도 값이 남아있어야 한다."""
        db.create_job("job1", original_path=Path("a"), protected_path=Path("a"), sha256="a", phash="a", created_at=1.0)
        db.increment_report_count()

        db.init_db(self.db_path)  # "재시작" — 같은 파일을 다시 연다

        self.assertIsNotNone(db.get_job("job1"))
        self.assertEqual(db.get_report_count(), 1)

    def test_reset_all_clears_every_table(self):
        db.create_job("job1", original_path=Path("a"), protected_path=Path("a"), sha256="a", phash="a", created_at=1.0)
        db.add_manual_report("https://example.com", created_at=1.0)
        db.set_confirmed_keep_ids(["c1"])
        db.increment_report_count()

        db.reset_all()

        self.assertEqual(db.count_completed_jobs(), 0)
        self.assertEqual(db.list_manual_reports(), [])
        self.assertEqual(db.get_confirmed_keep_ids(), [])
        self.assertEqual(db.get_report_count(), 0)

    def test_concurrent_increment_report_count_has_no_lost_updates(self):
        """여러 스레드가 동시에 신고 동의를 눌러도 카운트가 씹히면 안 된다.

        WAL 모드가 'database is locked' 실패를 막고, increment_report_count의
        원자적 UPSERT가 읽고-쓰는 사이의 경합(lost update)을 막는지 함께 검증한다.
        """
        thread_count = 8
        increments_per_thread = 15
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                for _ in range(increments_per_thread):
                    db.increment_report_count()
            except BaseException as exc:  # noqa: BLE001 - 스레드 예외를 메인에서 확인하려고 수집
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(db.get_report_count(), thread_count * increments_per_thread)

    def test_concurrent_job_creation_has_no_locking_errors(self):
        """여러 스레드가 동시에 보호사진을 처리해도 쓰기 잠금 오류가 나면 안 된다."""
        thread_count = 8
        errors: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                db.create_job(
                    f"job-{index}",
                    original_path=Path(f"a{index}"),
                    protected_path=Path(f"b{index}"),
                    sha256=f"sha{index}",
                    phash=f"phash{index}",
                    created_at=float(index),
                )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(db.count_completed_jobs(), thread_count)


if __name__ == "__main__":
    unittest.main()
