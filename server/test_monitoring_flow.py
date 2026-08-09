import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import model_api


class MonitoringFlowHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        main.JOBS.clear()
        main.MONITORING_SCANS.clear()
        main.MODEL_CANDIDATES.clear()
        main._manual_reports.clear()
        main._confirmed_keep_ids.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reference_path = Path(self.temp_dir.name) / "reference.jpg"
        self.reference_path.write_bytes(b"reference-image")
        main.JOBS["job-1"] = {
            "originalPath": self.reference_path,
            "contentType": "image/jpeg",
            "createdAt": time.time(),
        }
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def test_missing_score_message_is_natural_korean(self) -> None:
        self.assertEqual(
            main._score_signal("딥페이크 모델 원점수", None),
            "딥페이크 모델 원점수를 계산하지 못함",
        )

    @patch("main.model_api.start_exposure_scan")
    @patch("main.model_api.create_face_enrollment")
    def test_start_scan_uses_uploaded_photo_and_explicit_consent(
        self, create_enrollment, start_scan
    ) -> None:
        create_enrollment.return_value = {"enrollment_id": "enrollment-1"}
        start_scan.return_value = {
            "scan_id": "scan-1",
            "status": "queued",
            "warning": "연구용",
        }

        response = self.client.post(
            "/api/monitoring/scans",
            json={
                "queryText": "동의받은 공개 검색어",
                "webMonitoringConsent": True,
                "referenceJobIds": ["job-1"],
                "maximumResults": 5,
            },
        )

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["scanId"], "scan-1")
        self.assertEqual(response.json()["referenceCount"], 1)
        references = create_enrollment.call_args.args[0]
        self.assertEqual(references, [(b"reference-image", "image/jpeg")])
        self.assertEqual(
            start_scan.call_args.kwargs["query_text"], "동의받은 공개 검색어"
        )
        self.assertIn("scan-1", main.MONITORING_SCANS)

    @patch("main.model_api.create_face_enrollment")
    def test_start_scan_rejects_missing_consent_before_model_call(
        self, create_enrollment
    ) -> None:
        response = self.client.post(
            "/api/monitoring/scans",
            json={
                "queryText": "공개 검색어",
                "webMonitoringConsent": False,
                "referenceJobIds": ["job-1"],
            },
        )

        self.assertEqual(response.status_code, 400, response.text)
        create_enrollment.assert_not_called()

    @patch("main.model_api.get_exposure_scan")
    def test_scan_status_maps_progress_without_inventing_confidence(
        self, get_scan
    ) -> None:
        main.MONITORING_SCANS["scan-1"] = {"createdAt": time.time()}
        get_scan.return_value = {
            "scan_id": "scan-1",
            "status": "deepfake_analyzing",
            "progress_percent": 80,
            "progress": {
                "searched_candidate_count": 5,
                "analyzed_candidate_count": 3,
                "identity_match_count": 2,
                "deepfake_completed_count": 1,
            },
        }

        response = self.client.get("/api/monitoring/scans/scan-1")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["progressPercent"], 80)
        self.assertEqual(body["identityMatchCount"], 2)
        self.assertNotIn("confidence", str(body).lower())

    @patch("main.model_api.get_client_exposure_candidates")
    def test_candidates_and_report_use_arcface_and_onnx_raw_scores(
        self, get_candidates
    ) -> None:
        main.MONITORING_SCANS["scan-1"] = {"createdAt": time.time()}
        get_candidates.return_value = {
            "scan_id": "scan-1",
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": "candidate-uuid-1",
                    "source_url": "https://example.com/post",
                    "media_url": "https://cdn.example.com/image.jpg",
                    "thumbnail_url": None,
                    "source_type": "searxng",
                    "source_engine": "duckduckgo images",
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

        response = self.client.get(
            "/api/monitoring/scans/scan-1/candidates"
        )
        self.assertEqual(response.status_code, 200, response.text)
        candidate = response.json()[0]
        self.assertEqual(candidate["faceSimilarity"], 0.652316)
        self.assertEqual(candidate["deepfakeScore"], 0.8123)
        self.assertEqual(candidate["riskLevel"], "high")
        self.assertNotIn("similarityPercent", candidate)

        detail = self.client.get(
            "/api/monitoring/candidates/candidate-uuid-1"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertIn("확률 아님", " ".join(detail.json()["signals"]))

        confirmed = self.client.post(
            "/api/monitoring/candidates/confirm",
            json={"keepIds": ["candidate-uuid-1"]},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        report = self.client.get("/api/report/draft").json()
        ai_result = next(item for item in report if item["key"] == "aiResult")
        self.assertIn("0.652316", ai_result["value"])
        self.assertIn("0.8123", ai_result["value"])

    @patch(
        "main.model_api.create_face_enrollment",
        side_effect=model_api.ModelApiError(
            "MODEL_API_ENROLLMENT_REQUEST_FAILED", unavailable=True
        ),
    )
    def test_model_connection_failure_returns_503_without_fake_results(
        self, _create_enrollment
    ) -> None:
        response = self.client.post(
            "/api/monitoring/scans",
            json={
                "queryText": "공개 검색어",
                "webMonitoringConsent": True,
                "referenceJobIds": ["job-1"],
            },
        )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "MODEL_API_ENROLLMENT_REQUEST_FAILED",
        )


if __name__ == "__main__":
    unittest.main()
