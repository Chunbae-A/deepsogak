"""딥소각 서버에서 모노레포 얼굴가드 모델 API를 호출하는 내부 어댑터."""

from __future__ import annotations

import os
from typing import Any, Sequence

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_TIMEOUT_SECONDS = 30.0
RESEARCH_WARNING = (
    "얼굴 유사도와 딥페이크 점수는 연구용 원점수입니다. "
    "자동 신고·삭제 근거로 사용하지 말고 사람이 원문을 확인해야 합니다."
)


class ModelApiError(RuntimeError):
    """모델 API 실패를 안정적인 오류 코드로 변환한다."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.unavailable = unavailable


def _base_url() -> str:
    return os.environ.get("FACEGUARD_MODEL_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _timeout_seconds() -> float:
    raw = os.environ.get(
        "FACEGUARD_MODEL_API_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)
    )
    try:
        timeout = float(raw)
    except ValueError as error:
        raise ModelApiError(
            "MODEL_API_TIMEOUT_INVALID",
            "모델 API 제한 시간이 올바른 숫자가 아닙니다.",
        ) from error
    if timeout <= 0:
        raise ModelApiError(
            "MODEL_API_TIMEOUT_INVALID",
            "모델 API 제한 시간은 0보다 커야 합니다.",
        )
    return timeout


def _safe_error(response: requests.Response) -> tuple[str | None, str | None]:
    try:
        body = response.json()
    except (TypeError, ValueError):
        return None, None
    if not isinstance(body, dict):
        return None, None
    error = body.get("error")
    if not isinstance(error, dict):
        detail = body.get("detail")
        error = detail if isinstance(detail, dict) else None
    if not isinstance(error, dict):
        return None, None
    code = error.get("code")
    message = error.get("message")
    return (
        str(code) if isinstance(code, str) else None,
        str(message) if isinstance(message, str) else None,
    )


def _response_json(response: requests.Response, *, operation: str) -> dict[str, Any]:
    if not response.ok:
        code, message = _safe_error(response)
        raise ModelApiError(
            code or f"{operation}_HTTP_{response.status_code}",
            message,
            unavailable=response.status_code >= 500,
        )
    try:
        body = response.json()
    except (TypeError, ValueError) as error:
        raise ModelApiError(f"{operation}_INVALID_RESPONSE") from error
    if not isinstance(body, dict):
        raise ModelApiError(f"{operation}_INVALID_RESPONSE")
    return body


def health() -> dict[str, Any]:
    try:
        response = requests.get(
            f"{_base_url()}/health",
            timeout=min(_timeout_seconds(), 5.0),
        )
        body = _response_json(response, operation="MODEL_API_HEALTH")
    except ModelApiError as error:
        return {"status": "unavailable", "connected": False, "errorCode": error.code}
    except requests.RequestException:
        return {
            "status": "unavailable",
            "connected": False,
            "errorCode": "MODEL_API_HEALTH_REQUEST_FAILED",
        }
    return {
        "status": body.get("status", "unknown"),
        "connected": True,
        "modelLoaded": bool(body.get("model_loaded")),
        "deepfakeModelLoaded": bool(body.get("deepfake_model_loaded")),
        "executionProvider": body.get("execution_provider"),
        "thresholdStatus": body.get("threshold_status"),
        "deepfakeThresholdStatus": body.get("deepfake_threshold_status"),
    }


def capabilities() -> dict[str, Any]:
    """모델 API가 제공하는 기능과 안전 상태를 그대로 확인한다."""

    try:
        response = requests.get(
            f"{_base_url()}/v1/capabilities",
            timeout=min(_timeout_seconds(), 5.0),
        )
        body = _response_json(response, operation="MODEL_API_CAPABILITIES")
    except requests.RequestException as error:
        raise ModelApiError(
            "MODEL_API_CAPABILITIES_REQUEST_FAILED", unavailable=True
        ) from error
    body["connected"] = True
    return body


def create_face_enrollment(
    reference_images: Sequence[tuple[bytes, str]],
) -> dict[str, Any]:
    files = [
        ("reference_images", (f"reference-{index}.jpg", payload, content_type))
        for index, (payload, content_type) in enumerate(reference_images, start=1)
    ]
    try:
        response = requests.post(
            f"{_base_url()}/v1/faceguard/enrollments",
            files=files,
            timeout=_timeout_seconds(),
        )
    except requests.RequestException as error:
        raise ModelApiError(
            "MODEL_API_ENROLLMENT_REQUEST_FAILED", unavailable=True
        ) from error
    return _response_json(response, operation="MODEL_API_ENROLLMENT")


def start_candidate_scan(
    enrollment_id: str,
    candidates: Sequence[dict[str, Any]],
    *,
    maximum_results: int,
    idempotency_key: str,
) -> dict[str, Any]:
    """Google Vision 후보를 모델 API의 ArcFace→ONNX 파이프라인에 넣는다."""

    submitted = [
        {
            "page_url": candidate["page_url"],
            "media_url": candidate.get("media_url"),
            "thumbnail_url": candidate.get("thumbnail_url"),
        }
        for candidate in candidates
    ]
    try:
        response = requests.post(
            f"{_base_url()}/v1/exposure-scans",
            json={
                "enrollment_id": enrollment_id,
                "privacy_mode": "privacy_strict",
                "web_monitoring_consent": False,
                "maximum_results": maximum_results,
                "candidates": submitted,
            },
            headers={"Idempotency-Key": idempotency_key},
            timeout=_timeout_seconds(),
        )
    except requests.RequestException as error:
        raise ModelApiError(
            "MODEL_API_SCAN_START_REQUEST_FAILED", unavailable=True
        ) from error
    return _response_json(response, operation="MODEL_API_SCAN_START")


def get_exposure_scan(scan_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            f"{_base_url()}/v1/exposure-scans/{scan_id}",
            timeout=_timeout_seconds(),
        )
    except requests.RequestException as error:
        raise ModelApiError(
            "MODEL_API_SCAN_STATUS_REQUEST_FAILED", unavailable=True
        ) from error
    return _response_json(response, operation="MODEL_API_SCAN_STATUS")


def get_exposure_candidates(scan_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            f"{_base_url()}/v1/exposure-scans/{scan_id}/client-candidates",
            timeout=_timeout_seconds(),
        )
    except requests.RequestException as error:
        raise ModelApiError(
            "MODEL_API_SCAN_CANDIDATES_REQUEST_FAILED", unavailable=True
        ) from error
    return _response_json(response, operation="MODEL_API_CLIENT_CANDIDATES")
