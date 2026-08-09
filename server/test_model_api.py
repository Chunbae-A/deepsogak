import unittest
from unittest.mock import Mock, patch

import requests

import model_api


class ModelApiAdapterTests(unittest.TestCase):
    @staticmethod
    def _response(payload: dict) -> Mock:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    @patch("model_api.requests.post")
    def test_analyze_protected_photo_returns_both_results(self, post: Mock) -> None:
        post.side_effect = [
            self._response(
                {
                    "is_same_person": True,
                    "similarity": 0.91,
                    "threshold": 0.28,
                    "threshold_status": "research_only_unapproved",
                    "processing_ms": 100,
                    "model_name": "buffalo_l",
                }
            ),
            self._response(
                {
                    "is_suspected_deepfake": False,
                    "deepfake_score": 0.12,
                    "threshold": 0.75,
                    "threshold_status": "research_only_unapproved",
                    "processing_ms": 80,
                    "inference_ms": 20,
                    "model_name": "efficientnet_b4_celebdf_v2",
                }
            ),
        ]

        result = model_api.analyze_protected_photo(
            b"original",
            b"protected",
            content_type="image/jpeg",
        )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["identity"]["isSamePerson"])
        self.assertEqual(result["identity"]["similarity"], 0.91)
        self.assertFalse(result["deepfake"]["isSuspectedDeepfake"])
        self.assertEqual(result["deepfake"]["deepfakeScore"], 0.12)
        self.assertEqual(post.call_count, 2)

    @patch("model_api.requests.post")
    def test_one_failed_step_returns_partial_failed(self, post: Mock) -> None:
        post.side_effect = [
            requests.ConnectionError(),
            self._response(
                {
                    "is_suspected_deepfake": False,
                    "deepfake_score": 0.1,
                    "threshold": 0.75,
                }
            ),
        ]

        result = model_api.analyze_protected_photo(
            b"original",
            b"protected",
            content_type="image/jpeg",
        )

        self.assertEqual(result["status"], "partial_failed")
        self.assertEqual(result["identity"]["status"], "unavailable")
        self.assertEqual(result["deepfake"]["status"], "completed")

    @patch("model_api.requests.get", side_effect=requests.ConnectionError())
    def test_health_does_not_expose_connection_error(self, _get: Mock) -> None:
        self.assertEqual(
            model_api.health(),
            {"status": "unavailable", "connected": False},
        )

    @patch("model_api.requests.post")
    def test_public_monitoring_calls_enrollment_then_scan(self, post: Mock) -> None:
        post.side_effect = [
            self._response(
                {
                    "enrollment_id": "enrollment-1",
                    "status": "active",
                    "reference_count": 1,
                }
            ),
            self._response(
                {
                    "scan_id": "scan-1",
                    "status": "queued",
                    "status_url": "/v1/exposure-scans/scan-1",
                    "client_candidates_url": (
                        "/v1/exposure-scans/scan-1/client-candidates"
                    ),
                }
            ),
        ]

        enrollment = model_api.create_face_enrollment(
            [(b"reference", "image/jpeg")]
        )
        scan = model_api.start_exposure_scan(
            enrollment["enrollment_id"],
            query_text="동의받은 공개 검색어",
            maximum_results=5,
            idempotency_key="monitoring-demo-key",
        )

        self.assertEqual(scan["scan_id"], "scan-1")
        enrollment_call = post.call_args_list[0]
        self.assertEqual(
            enrollment_call.kwargs["files"][0][0], "reference_images"
        )
        scan_call = post.call_args_list[1]
        self.assertEqual(scan_call.kwargs["json"]["privacy_mode"], "web_monitoring")
        self.assertTrue(scan_call.kwargs["json"]["web_monitoring_consent"])
        self.assertEqual(
            scan_call.kwargs["headers"]["Idempotency-Key"],
            "monitoring-demo-key",
        )

    @patch("model_api.requests.get")
    def test_public_monitoring_fetches_status_and_client_candidates(
        self, get: Mock
    ) -> None:
        get.side_effect = [
            self._response(
                {
                    "scan_id": "scan-1",
                    "status": "completed",
                    "progress_percent": 100,
                    "progress": {"identity_match_count": 1},
                }
            ),
            self._response(
                {
                    "scan_id": "scan-1",
                    "status": "completed",
                    "candidate_count": 1,
                    "candidates": [
                        {
                            "candidate_id": "candidate-1",
                            "recommended_action": "review_required",
                        }
                    ],
                }
            ),
        ]

        status = model_api.get_exposure_scan("scan-1")
        candidates = model_api.get_client_exposure_candidates("scan-1")

        self.assertEqual(status["progress_percent"], 100)
        self.assertEqual(
            candidates["candidates"][0]["recommended_action"],
            "review_required",
        )

    @patch("model_api.requests.post", side_effect=requests.ConnectionError())
    def test_public_monitoring_connection_error_is_stable(self, _post: Mock) -> None:
        with self.assertRaises(model_api.ModelApiError) as raised:
            model_api.create_face_enrollment([(b"reference", "image/jpeg")])

        self.assertEqual(
            raised.exception.code, "MODEL_API_ENROLLMENT_REQUEST_FAILED"
        )
        self.assertTrue(raised.exception.unavailable)

    @patch("model_api.requests.post")
    def test_public_monitoring_keeps_safe_model_validation_message(
        self, post: Mock
    ) -> None:
        response = Mock()
        response.status_code = 422
        response.json.return_value = {
            "error": {
                "code": "MULTIPLE_FACES",
                "message": "사진에는 한 사람의 얼굴만 있어야 합니다.",
            }
        }
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        post.return_value = response

        with self.assertRaises(model_api.ModelApiError) as raised:
            model_api.create_face_enrollment([(b"reference", "image/jpeg")])

        self.assertEqual(raised.exception.code, "MULTIPLE_FACES")
        self.assertEqual(
            raised.exception.message,
            "사진에는 한 사람의 얼굴만 있어야 합니다.",
        )


if __name__ == "__main__":
    unittest.main()
