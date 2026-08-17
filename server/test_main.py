"""서버 엔드포인트 통합 테스트.

딥백신 알고리즘 자체는 test_deepbaeksin.py에서 이미 검증하므로, 여기서는
main.deepbaeksin.apply_deepbaeksin을 빠른 가짜로 바꿔서 "엔드포인트가 DB와
제대로 연결됐는가"에만 집중한다. 실제 얼굴 사진으로 하는 수동 검증은 PR
설명에 기록돼 있다(딥백신 53회 반복, 유사도 1.0->0.929, 서버 재시작 후에도
결과 유지 확인).
"""

import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

import db
import main


def _fake_apply_deepbaeksin(image, **_kwargs):
    meta = {
        "applied": True,
        "reason": "ok",
        "iterationsRun": 5,
        "epsilon": 8,
        "similarityAfter": 0.9,
        "endToEndSimilarityAfter": 0.9,
        "ssim": 0.99,
        "elapsedSeconds": 0.01,
        "thresholdStatus": "research_only_unapproved",
    }
    return image.convert("RGB"), meta


def _sample_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class ServerEndpointsTestCase(unittest.TestCase):
    def setUp(self):
        # 다른 테스트 모듈(test_db.py)이 db._DB_PATH를 임시 파일로 바꿔놓고
        # 정리할 수 있으므로, main.py가 실제로 쓰는 DB 경로로 명시적으로
        # 되돌린 뒤 시작한다. unittest discover로 여러 파일이 한 프로세스에서
        # 돌 때도 이 테스트가 독립적으로 동작하게 하기 위함이다.
        db.init_db(main.DB_PATH)
        db.reset_all()
        patcher = patch.object(main, "deepbaeksin")
        self.mock_deepbaeksin = patcher.start()
        self.mock_deepbaeksin.apply_deepbaeksin.side_effect = _fake_apply_deepbaeksin
        self.mock_deepbaeksin.warm_up.return_value = True
        self.addCleanup(patcher.stop)

        # 실제 Google Vision API를 호출하면 네트워크에 의존해 테스트가 느려지고
        # 불안정해진다. 얼굴가드 순찰 로직 자체(pHash 대조 등)는 vision_scan
        # 모듈의 몫이라 여기서는 빈 결과로 고정해 서버 쪽 연결부만 검증한다.
        vision_patcher = patch.object(main.vision_scan, "scan_web", return_value=[])
        vision_patcher.start()
        self.addCleanup(vision_patcher.stop)

        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def tearDown(self):
        db.reset_all()

    def _upload(self):
        response = self.client.post(
            "/api/protection/process",
            files={"photo": ("sample.jpg", _sample_jpeg_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["jobId"]

    def test_process_then_result_reflects_deepbaeksin_meta(self):
        job_id = self._upload()

        result = self.client.get("/api/protection/result", params={"jobId": job_id})
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body["deepbaeksin"]["reason"], "ok")
        self.assertIn("90%", body["appliedChecks"][0])

    def test_result_for_unknown_job_is_404(self):
        response = self.client.get("/api/protection/result", params={"jobId": "missing"})
        self.assertEqual(response.status_code, 404)

    def test_home_summary_counts_persist_across_requests(self):
        self._upload()
        self._upload()

        summary = self.client.get("/api/home/summary").json()
        self.assertEqual(summary["protectedCount"], 2)

    def test_manual_report_and_confirm_and_draft_override_flow(self):
        self.client.post("/api/monitoring/report", json={"url": "https://example.com/leak"})
        summary = self.client.get("/api/monitoring/summary").json()
        self.assertGreaterEqual(summary["totalCandidates"], 1)

        confirm = self.client.post("/api/monitoring/candidates/confirm", json={"keepIds": ["c1"]})
        self.assertEqual(confirm.status_code, 200)

        override = self.client.post(
            "/api/report/draft",
            json={"fields": [{"key": "postUrl", "label": "게시물 URL", "value": "manual.example.com"}]},
        )
        self.assertEqual(override.status_code, 200)

        draft = self.client.get("/api/report/draft").json()
        self.assertEqual(draft[0]["value"], "manual.example.com")

    def test_report_consent_increments_count(self):
        before = self.client.get("/api/home/summary").json()["reportCount"]
        self.client.post("/api/report/consent")
        after = self.client.get("/api/home/summary").json()["reportCount"]
        self.assertEqual(after, before + 1)

    def test_empty_upload_is_rejected(self):
        response = self.client.post(
            "/api/protection/process",
            files={"photo": ("empty.jpg", b"", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
