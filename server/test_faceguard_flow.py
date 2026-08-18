import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
import main


class FaceGuardFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        # test_db.py 등 다른 테스트 모듈이 db._DB_PATH를 임시 파일로 바꿔놓을 수
        # 있으므로, main.py가 실제로 쓰는 DB 경로로 명시적으로 되돌린 뒤 시작한다
        # (test_main.py와 동일한 패턴).
        db.init_db(main.DB_PATH)
        db.reset_all()
        main.FACEGUARD_SCANS.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        original = root / "original.jpg"
        protected = root / "protected.jpg"
        original.write_bytes(b"original-image")
        protected.write_bytes(b"metadata-free-image")
        db.create_job(
            "job-1",
            original_path=original,
            protected_path=protected,
            sha256="fake-sha256",
            phash="fake-phash",
            created_at=time.time(),
        )
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    @patch("main.model_api.start_candidate_scan")
    @patch("main.model_api.create_face_enrollment")
    @patch("main.vision_scan.discover_web_candidates")
    def test_scan_runs_vision_then_arcface_onnx_pipeline(
        self, discover, enroll, start_scan
    ) -> None:
        discover.return_value = {
            "provider": "google_vision_web_detection",
            "status": "completed",
            "raw_candidate_count": 1,
            "candidate_count": 1,
            "truncated_count": 0,
            "best_guess_labels": [],
            "candidates": [
                {
                    "page_url": "https://example.com/post",
                    "media_url": "https://cdn.example.com/image.jpg",
                    "thumbnail_url": "https://cdn.example.com/image.jpg",
                    "provider": "google_vision_web_detection",
                    "match_type": "partial_match",
                    "page_title": "게시물",
                }
            ],
        }
        enroll.return_value = {"enrollment_id": "enrollment-1"}
        start_scan.return_value = {"scan_id": "scan-1", "status": "queued"}

        response = self.client.post(
            "/api/faceguard/scans",
            json={
                "referenceJobIds": ["job-1"],
                "webMonitoringConsent": True,
                "maximumResults": 5,
            },
        )

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["scanId"], "scan-1")
        self.assertEqual(discover.call_args.args[0], b"metadata-free-image")
        self.assertEqual(enroll.call_args.args[0], [(b"original-image", "image/jpeg")])
        self.assertEqual(start_scan.call_args.args[0], "enrollment-1")
        self.assertIn("scan-1", main.FACEGUARD_SCANS)

    @patch("main.vision_scan.discover_web_candidates")
    def test_scan_requires_explicit_consent_before_external_call(self, discover) -> None:
        response = self.client.post(
            "/api/faceguard/scans",
            json={
                "referenceJobIds": ["job-1"],
                "webMonitoringConsent": False,
            },
        )

        self.assertEqual(response.status_code, 400, response.text)
        discover.assert_not_called()

    @patch("main.model_api.get_exposure_candidates")
    def test_candidate_response_keeps_raw_scores_not_fake_confidence(self, get_candidates) -> None:
        main.FACEGUARD_SCANS["scan-1"] = {
            "modelScanId": "scan-1",
            "discovery": {"candidate_count": 1},
            "discoveryByUrl": {
                "https://cdn.example.com/image.jpg": {"match_type": "partial_match"}
            },
        }
        get_candidates.return_value = {
            "scan_id": "scan-1",
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "source_url": "https://example.com/post",
                    "media_url": "https://cdn.example.com/image.jpg",
                    "thumbnail_url": None,
                    "source_type": "user_url",
                    "source_engine": None,
                    "face_similarity": 0.652316,
                    "face_match_level": "matched",
                    "deepfake_score": 0.8123,
                    "deepfake_signal": "suspected",
                    "recommended_action": "review_required",
                    "analysis_status": "completed",
                    "warning": "연구용 원점수",
                }
            ],
        }

        response = self.client.get("/api/faceguard/scans/scan-1/candidates")

        self.assertEqual(response.status_code, 200, response.text)
        candidate = response.json()["candidates"][0]
        self.assertEqual(candidate["faceSimilarity"], 0.652316)
        self.assertEqual(candidate["deepfakeScore"], 0.8123)
        self.assertEqual(candidate["recommendedAction"], "review_required")
        self.assertEqual(candidate["visionMatchType"], "partial_match")
        self.assertNotIn("confidence", str(candidate).lower())

    @patch("main.model_api.capabilities")
    def test_capabilities_keep_research_safety_contract(self, capabilities) -> None:
        capabilities.return_value = {
            "connected": True,
            "api_version": "0.9.0",
            "deployment_mode": "research_demo",
            "workflows": ["face_verification", "public_exposure_scan"],
            "models": [
                {
                    "component_id": "face_verification",
                    "role": "동일인 후보 선별",
                    "model_name": "buffalo_l",
                    "load_state": "lazy",
                    "decision_status": "research_only_unapproved",
                    "score_semantics": "cosine_similarity",
                    "default_enabled": True,
                }
            ],
            "state_storage": "process_memory_ttl",
            "warning": "연구용",
        }

        response = self.client.get("/api/faceguard/capabilities")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["apiVersion"], "0.9.0")
        self.assertEqual(body["models"][0]["componentId"], "face_verification")
        self.assertEqual(body["models"][0]["scoreSemantics"], "cosine_similarity")
        self.assertFalse(body["scoresAreProbabilities"])
        self.assertFalse(body["automaticEnforcementAllowed"])
        self.assertFalse(body["originalMediaPersisted"])

    @patch.dict(os.environ, {"GOOGLE_VISION_API_KEY": "server-only-key"}, clear=False)
    @patch("main.model_api.health")
    def test_health_never_returns_google_api_key(self, health) -> None:
        health.return_value = {"status": "ok", "connected": True}

        response = self.client.get("/api/faceguard/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertNotIn("server-only-key", response.text)


class MonitoringBridgeTests(unittest.TestCase):
    """#80: /api/monitoring/*가 예전 pHash 시뮬레이션이 아니라 진짜
    /api/faceguard/scans/* 파이프라인 결과를 그대로 반영하는지 검증한다."""

    def setUp(self) -> None:
        db.init_db(main.DB_PATH)
        db.reset_all()
        main.FACEGUARD_SCANS.clear()
        main.MONITORING_SCAN_BY_JOB.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        original = root / "original.jpg"
        protected = root / "protected.jpg"
        original.write_bytes(b"original-image")
        protected.write_bytes(b"metadata-free-image")
        db.create_job(
            "job-1",
            original_path=original,
            protected_path=protected,
            sha256="fake-sha256",
            phash="fake-phash",
            created_at=time.time(),
        )
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def _mock_discovery(self) -> dict:
        return {
            "provider": "google_vision_web_detection",
            "status": "completed",
            "raw_candidate_count": 1,
            "candidate_count": 1,
            "truncated_count": 0,
            "best_guess_labels": [],
            "candidates": [
                {
                    "page_url": "https://example.com/post",
                    "media_url": "https://cdn.example.com/image.jpg",
                    "thumbnail_url": "https://cdn.example.com/image.jpg",
                    "provider": "google_vision_web_detection",
                    "match_type": "partial_match",
                    "page_title": "게시물",
                }
            ],
        }

    @patch("main.model_api.get_exposure_candidates")
    @patch("main.model_api.get_exposure_scan")
    @patch("main.model_api.start_candidate_scan")
    @patch("main.model_api.create_face_enrollment")
    @patch("main.vision_scan.discover_web_candidates")
    def test_candidates_reflect_real_pipeline_result_not_hardcoded_fallback(
        self, discover, enroll, start_scan, get_scan, get_candidates
    ) -> None:
        discover.return_value = self._mock_discovery()
        enroll.return_value = {"enrollment_id": "enrollment-1"}
        start_scan.return_value = {"scan_id": "scan-1", "status": "queued"}
        get_scan.return_value = {"status": "completed", "progress_percent": 100, "progress": {}}
        get_candidates.return_value = {
            "scan_id": "scan-1",
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "source_url": "https://example.com/post",
                    "media_url": "https://cdn.example.com/image.jpg",
                    "thumbnail_url": None,
                    "face_similarity": 0.9123,
                    "face_match_level": "matched",
                    "deepfake_score": 0.8123,
                    "deepfake_signal": "suspected",
                    "recommended_action": "review_required",
                    "warning": "연구용 원점수",
                }
            ],
        }

        response = self.client.get("/api/monitoring/candidates")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 1)
        # 예전 하드코딩 값(예: 92%, "공개 SNS")이 아니라 모델 API가 돌려준
        # 실제 face_similarity·recommendedAction을 그대로 반영해야 한다.
        self.assertEqual(body[0]["similarityPercent"], 91)
        self.assertEqual(body[0]["riskLabel"], "딥페이크 위험도 · 높음")
        self.assertEqual(body[0]["riskLevel"], "high")
        self.assertEqual(body[0]["sourceLabel"], "Google 이미지 검색")

        detail = self.client.get("/api/monitoring/candidates/c1").json()
        self.assertIn("0.912", detail["signals"][0])
        self.assertIn("0.8123", detail["signals"][1])

    @patch("main.vision_scan.discover_web_candidates")
    def test_no_vision_candidates_returns_empty_list_not_hardcoded_fallback(self, discover) -> None:
        discover.return_value = {
            "provider": "google_vision_web_detection",
            "status": "completed",
            "raw_candidate_count": 0,
            "candidate_count": 0,
            "truncated_count": 0,
            "best_guess_labels": [],
            "candidates": [],
        }

        response = self.client.get("/api/monitoring/candidates")

        self.assertEqual(response.status_code, 200)
        # 예전에는 여기서 CANDIDATE_DETAILS 하드코딩 후보 3개(c1/c2/c3)가 나왔다.
        self.assertEqual(response.json(), [])

    def test_no_protected_photo_yet_returns_honest_empty_summary(self) -> None:
        db.reset_all()  # job-1도 지운다 — 보호사진이 아예 없는 상태

        response = self.client.get("/api/monitoring/summary")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        # 예전에는 여기서 totalCandidates=6짜리 가짜 요약이 나왔다.
        self.assertEqual(body["totalCandidates"], 0)
        self.assertEqual(body["lastCheckedAt"], "아직 보호사진 없음")

    @patch("main.model_api.get_exposure_scan")
    @patch("main.model_api.start_candidate_scan")
    @patch("main.model_api.create_face_enrollment")
    @patch("main.vision_scan.discover_web_candidates")
    def test_model_api_failed_status_reports_error_not_stuck_scanning(
        self, discover, enroll, start_scan, get_scan
    ) -> None:
        """모델 API가 스캔을 status="failed"로 종결해도 "scanning"에 영원히
        머무르면 안 된다(FINAL_SCAN_STATUSES에 completed·partial_failed 외에
        failed도 있음 — services/faceguard-model-api/faceguard_api/exposure.py)."""
        discover.return_value = self._mock_discovery()
        enroll.return_value = {"enrollment_id": "enrollment-1"}
        start_scan.return_value = {"scan_id": "scan-1", "status": "queued"}
        get_scan.return_value = {"status": "failed", "progress_percent": 0, "progress": {}}

        response = self.client.get("/api/monitoring/summary")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["lastCheckedAt"], "확인 실패 — 잠시 후 다시 시도해 주세요")
        # 실패한 스캔 매핑은 지워져서 다음 요청은 새 스캔을 다시 시도할 수 있어야 한다.
        self.assertNotIn("job-1", main.MONITORING_SCAN_BY_JOB)


if __name__ == "__main__":
    unittest.main()
