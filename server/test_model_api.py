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


if __name__ == "__main__":
    unittest.main()
