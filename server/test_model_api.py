import unittest
from unittest.mock import Mock, patch

import requests

import model_api


class ModelApiAdapterTests(unittest.TestCase):
    @staticmethod
    def _response(payload: dict, *, status_code: int = 200) -> Mock:
        response = Mock(spec=requests.Response)
        response.ok = status_code < 400
        response.status_code = status_code
        response.json.return_value = payload
        return response

    @patch("model_api.requests.post")
    def test_google_candidates_are_submitted_without_query_image(self, post: Mock) -> None:
        post.return_value = self._response({"scan_id": "scan-1", "status": "queued"})

        result = model_api.start_candidate_scan(
            "enrollment-1",
            [
                {
                    "page_url": "https://example.com/post",
                    "media_url": "https://cdn.example.com/image.jpg",
                    "thumbnail_url": "https://cdn.example.com/image.jpg",
                }
            ],
            maximum_results=5,
            idempotency_key="google-vision-test-key",
        )

        self.assertEqual(result["scan_id"], "scan-1")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["privacy_mode"], "privacy_strict")
        self.assertNotIn("query_text", body)
        self.assertNotIn("image", body)
        self.assertEqual(body["candidates"][0]["page_url"], "https://example.com/post")

    @patch("model_api.requests.post")
    def test_model_validation_error_is_preserved(self, post: Mock) -> None:
        post.return_value = self._response(
            {
                "error": {
                    "code": "MULTIPLE_FACES",
                    "message": "사진에는 한 사람의 얼굴만 있어야 합니다.",
                }
            },
            status_code=422,
        )

        with self.assertRaises(model_api.ModelApiError) as raised:
            model_api.create_face_enrollment([(b"image", "image/jpeg")])

        self.assertEqual(raised.exception.code, "MULTIPLE_FACES")
        self.assertEqual(
            raised.exception.message, "사진에는 한 사람의 얼굴만 있어야 합니다."
        )

    @patch("model_api.requests.get", side_effect=requests.ConnectionError())
    def test_health_does_not_expose_connection_details(self, _get: Mock) -> None:
        result = model_api.health()

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["connected"])
        self.assertEqual(result["errorCode"], "MODEL_API_HEALTH_REQUEST_FAILED")

    @patch("model_api.requests.get")
    def test_capabilities_use_stable_model_api_endpoint(self, get: Mock) -> None:
        get.return_value = self._response(
            {
                "api_version": "0.9.0",
                "deployment_mode": "research_demo",
                "models": [],
            }
        )

        result = model_api.capabilities()

        self.assertTrue(result["connected"])
        self.assertEqual(result["api_version"], "0.9.0")
        self.assertTrue(
            get.call_args.args[0].endswith("/v1/capabilities")
        )

    @patch("model_api.requests.get")
    def test_candidate_adapter_uses_client_contract_endpoint(self, get: Mock) -> None:
        get.return_value = self._response(
            {"scan_id": "scan-1", "status": "completed", "candidates": []}
        )

        model_api.get_exposure_candidates("scan-1")

        self.assertTrue(
            get.call_args.args[0].endswith(
                "/v1/exposure-scans/scan-1/client-candidates"
            )
        )


if __name__ == "__main__":
    unittest.main()
