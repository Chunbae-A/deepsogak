import unittest

import access_control


class AccessControlScaffoldTests(unittest.TestCase):
    """#76 접근 제어 방식이 정해지기 전까지, 이 모듈이 아직 미구현임을
    명시적으로 남겨두는 테스트. 실제 방식이 정해져 구현되면 이 테스트를
    실제 동작 검증 테스트로 교체한다.
    """

    def test_issue_photo_access_token_is_not_implemented_yet(self):
        with self.assertRaises(NotImplementedError):
            access_control.issue_photo_access_token("job-1")

    def test_verify_photo_access_token_is_not_implemented_yet(self):
        with self.assertRaises(NotImplementedError):
            access_control.verify_photo_access_token("some-token")


if __name__ == "__main__":
    unittest.main()
