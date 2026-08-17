import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FaceGuardComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = (ROOT / "docker-compose.faceguard.yml").read_text(
            encoding="utf-8"
        )
        cls.example_env = (ROOT / ".env.faceguard.example").read_text(
            encoding="utf-8"
        )

    def test_server_calls_model_api_over_internal_service_name(self):
        self.assertIn("FACEGUARD_MODEL_API_URL: http://faceguard-model-api:8000", self.compose)
        self.assertIn("faceguard-model-api:", self.compose)
        self.assertIn("condition: service_healthy", self.compose)

    def test_host_ports_are_loopback_only(self):
        self.assertIn('"127.0.0.1:8000:8000"', self.compose)
        self.assertIn('"127.0.0.1:8001:8000"', self.compose)

    def test_secret_is_injected_instead_of_committed(self):
        self.assertIn('GOOGLE_VISION_API_KEY: "${GOOGLE_VISION_API_KEY:-}"', self.compose)
        self.assertIn("GOOGLE_VISION_API_KEY=", self.example_env)
        self.assertNotIn("AIza", self.compose)
        self.assertNotIn("AIza", self.example_env)


if __name__ == "__main__":
    unittest.main()
