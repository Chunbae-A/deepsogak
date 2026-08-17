import os
import unittest
from unittest.mock import Mock, patch

import vision_scan


class VisionDiscoveryTests(unittest.TestCase):
    @staticmethod
    def _response(payload: dict) -> Mock:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    @patch.dict(os.environ, {"GOOGLE_VISION_API_KEY": "test-secret"}, clear=False)
    @patch("vision_scan.requests.post")
    def test_discovers_page_matches_before_visual_candidates(self, post: Mock) -> None:
        post.return_value = self._response(
            {
                "responses": [
                    {
                        "webDetection": {
                            "pagesWithMatchingImages": [
                                {
                                    "url": "https://example.com/post/1",
                                    "pageTitle": "공개 게시물",
                                    "fullMatchingImages": [
                                        {"url": "https://cdn.example.com/full.jpg"}
                                    ],
                                    "partialMatchingImages": [
                                        {"url": "https://cdn.example.com/crop.jpg"}
                                    ],
                                }
                            ],
                            "visuallySimilarImages": [
                                {"url": "https://images.example.net/similar.jpg"}
                            ],
                            "bestGuessLabels": [{"label": "portrait"}],
                        }
                    }
                ]
            }
        )

        result = vision_scan.discover_web_candidates(b"image", maximum_results=3)

        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["candidates"][0]["match_type"], "full_match")
        self.assertEqual(result["candidates"][1]["match_type"], "partial_match")
        self.assertEqual(result["candidates"][2]["match_type"], "visually_similar")
        self.assertEqual(result["best_guess_labels"], ["portrait"])
        request = post.call_args
        self.assertEqual(request.args[0], vision_scan.VISION_ANNOTATE_URL)
        self.assertEqual(request.kwargs["headers"], {"x-goog-api-key": "test-secret"})
        self.assertNotIn("test-secret", request.args[0])

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_returns_stable_error(self) -> None:
        with self.assertRaises(vision_scan.VisionScanError) as raised:
            vision_scan.discover_web_candidates(b"image")

        self.assertEqual(raised.exception.code, "GOOGLE_VISION_API_KEY_MISSING")
        self.assertTrue(raised.exception.unavailable)

    @patch.dict(os.environ, {"GOOGLE_VISION_API_KEY": "test-secret"}, clear=False)
    @patch("vision_scan.requests.post")
    def test_response_level_error_is_not_silently_ignored(self, post: Mock) -> None:
        post.return_value = self._response(
            {"responses": [{"error": {"code": 7, "message": "denied"}}]}
        )

        with self.assertRaises(vision_scan.VisionScanError) as raised:
            vision_scan.discover_web_candidates(b"image")

        self.assertEqual(raised.exception.code, "GOOGLE_VISION_ANALYSIS_FAILED")


if __name__ == "__main__":
    unittest.main()
