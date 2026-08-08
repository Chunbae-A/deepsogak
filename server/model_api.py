"""모노레포 얼굴가드 모델 API를 호출하는 딥소각 서버용 어댑터."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
RESEARCH_WARNING = (
    "얼굴 유사도와 딥페이크 점수는 보정된 확률이 아닌 연구용 원점수입니다. "
    "운영 판정이나 자동 신고에 사용하지 마세요."
)


def _base_url() -> str:
    return os.getenv("FACEGUARD_MODEL_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _timeout_seconds() -> float:
    return float(os.getenv("FACEGUARD_MODEL_API_TIMEOUT_SECONDS", "30"))


def _failed_result(error_code: str, *, unavailable: bool = False) -> dict[str, Any]:
    return {
        "status": "unavailable" if unavailable else "failed",
        "errorCode": error_code,
    }


def health() -> dict[str, Any]:
    """기존 서버가 모델 API에 접근할 수 있는지 민감정보 없이 확인한다."""

    try:
        response = requests.get(
            f"{_base_url()}/health",
            timeout=min(_timeout_seconds(), 5.0),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return {"status": "unavailable", "connected": False}
    except (TypeError, ValueError):
        return {"status": "invalid_response", "connected": False}

    return {
        "status": payload.get("status", "unknown"),
        "connected": True,
        "apiVersion": payload.get("api_version"),
        "faceModelLoaded": bool(payload.get("model_loaded")),
        "deepfakeModelLoaded": bool(payload.get("deepfake_model_loaded")),
        "executionProvider": payload.get("execution_provider"),
        "deepfakeExecutionProvider": payload.get("deepfake_execution_provider"),
    }


def _verify_identity(
    original_bytes: bytes,
    protected_bytes: bytes,
    *,
    content_type: str,
) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{_base_url()}/v1/faceguard/verify",
            files=[
                (
                    "reference_images",
                    ("reference-image", original_bytes, content_type),
                ),
                (
                    "query_image",
                    ("protected-image", protected_bytes, content_type),
                ),
            ],
            timeout=_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else 500
        return _failed_result(f"MODEL_API_IDENTITY_HTTP_{status_code}")
    except requests.RequestException:
        return _failed_result("MODEL_API_IDENTITY_REQUEST_FAILED", unavailable=True)
    except (TypeError, ValueError):
        return _failed_result("MODEL_API_IDENTITY_INVALID_RESPONSE")

    return {
        "status": "completed",
        "isSamePerson": bool(payload.get("is_same_person")),
        "similarity": payload.get("similarity"),
        "threshold": payload.get("threshold"),
        "thresholdStatus": payload.get("threshold_status"),
        "processingMs": payload.get("processing_ms"),
        "modelName": payload.get("model_name"),
    }


def _analyze_deepfake(
    protected_bytes: bytes,
    *,
    content_type: str,
) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{_base_url()}/v1/deepfake/analyze",
            files={"image": ("protected-image", protected_bytes, content_type)},
            timeout=_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else 500
        return _failed_result(f"MODEL_API_DEEPFAKE_HTTP_{status_code}")
    except requests.RequestException:
        return _failed_result("MODEL_API_DEEPFAKE_REQUEST_FAILED", unavailable=True)
    except (TypeError, ValueError):
        return _failed_result("MODEL_API_DEEPFAKE_INVALID_RESPONSE")

    return {
        "status": "completed",
        "isSuspectedDeepfake": bool(payload.get("is_suspected_deepfake")),
        "deepfakeScore": payload.get("deepfake_score"),
        "threshold": payload.get("threshold"),
        "thresholdStatus": payload.get("threshold_status"),
        "processingMs": payload.get("processing_ms"),
        "inferenceMs": payload.get("inference_ms"),
        "modelName": payload.get("model_name"),
    }


def analyze_protected_photo(
    original_bytes: bytes,
    protected_bytes: bytes,
    *,
    content_type: str,
) -> dict[str, Any]:
    """보호 처리 전후 동일인 유지와 보호본 딥페이크 점수를 함께 확인한다."""

    identity = _verify_identity(
        original_bytes,
        protected_bytes,
        content_type=content_type,
    )
    deepfake = _analyze_deepfake(protected_bytes, content_type=content_type)
    completed_count = sum(
        result.get("status") == "completed" for result in (identity, deepfake)
    )
    if completed_count == 2:
        status = "completed"
    elif completed_count == 1:
        status = "partial_failed"
    else:
        status = "unavailable"

    return {
        "status": status,
        "identity": identity,
        "deepfake": deepfake,
        "warning": RESEARCH_WARNING,
    }
