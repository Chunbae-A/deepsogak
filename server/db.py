"""딥소각 서버의 영속 저장소.

이전에는 프로토타입 인메모리 dict/list(JOBS, _manual_reports, _confirmed_keep_ids,
_draft_overrides, REPORT_COUNT, _scan_cache)에만 상태를 두어 서버를 재시작하면
전부 사라졌다. 이 모듈은 같은 데이터를 SQLite 파일(storage/deepsogak.db)에
저장해 재시작·다른 프로세스 간에도 유지되도록 한다.

설계 원칙:
- 팀 규모·해커톤 프로토타입 단계에 맞춰 별도 DB 서버 없이 표준 라이브러리
  sqlite3만 사용한다(새 의존성 추가 없음). 나중에 MySQL 등으로 옮길 때도
  이 모듈의 함수 시그니처만 유지하면 호출부(main.py)는 바뀌지 않는다.
- 호출마다 짧게 connect/commit/close 한다. 동시 쓰기 경합이 SQLite 기본
  잠금으로 처리 가능한 트래픽 규모(해커톤 시연·소규모 팀 사용)를 전제로 한다.
- main.py가 기존에 쓰던 키 이름(originalPath, protectedPath, sha256, phash,
  createdAt 등)을 그대로 반환해, 호출부 로직을 최대한 건드리지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_DB_PATH: Path | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    protected_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    phash TEXT NOT NULL,
    created_at REAL NOT NULL,
    deepbaeksin_applied INTEGER NOT NULL DEFAULT 0,
    deepbaeksin_meta TEXT
);

CREATE TABLE IF NOT EXISTS manual_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_cache (
    job_id TEXT PRIMARY KEY,
    matches_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init_db(db_path: Path) -> None:
    """DB 파일 경로를 정하고 테이블이 없으면 만든다. 앱 시작 시 한 번 호출한다."""
    global _DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _DB_PATH = db_path
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _require_path() -> Path:
    if _DB_PATH is None:
        raise RuntimeError("init_db()를 먼저 호출해야 합니다.")
    return _DB_PATH


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_require_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# jobs (보호사진 처리 작업)
# ---------------------------------------------------------------------------


def create_job(
    job_id: str,
    *,
    original_path: Path,
    protected_path: Path,
    sha256: str,
    phash: str,
    created_at: float,
    deepbaeksin_applied: bool = False,
    deepbaeksin_meta: dict[str, Any] | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (id, original_path, protected_path, sha256, phash, created_at,
                 deepbaeksin_applied, deepbaeksin_meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                str(original_path),
                str(protected_path),
                sha256,
                phash,
                created_at,
                1 if deepbaeksin_applied else 0,
                json.dumps(deepbaeksin_meta, ensure_ascii=False) if deepbaeksin_meta else None,
            ),
        )


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "originalPath": Path(row["original_path"]),
        "protectedPath": Path(row["protected_path"]),
        "sha256": row["sha256"],
        "phash": row["phash"],
        "createdAt": row["created_at"],
        "deepbaeksinApplied": bool(row["deepbaeksin_applied"]),
        "deepbaeksinMeta": json.loads(row["deepbaeksin_meta"]) if row["deepbaeksin_meta"] else None,
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def get_latest_job() -> tuple[str, dict[str, Any]] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return row["id"], _row_to_job(row)


def count_jobs() -> int:
    with _connect() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    return count


# ---------------------------------------------------------------------------
# manual_reports (사용자 직접 제보 URL)
# ---------------------------------------------------------------------------


def add_manual_report(url: str, created_at: float) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO manual_reports (url, created_at) VALUES (?, ?)",
            (url, created_at),
        )


def list_manual_reports() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT url FROM manual_reports ORDER BY id ASC"
        ).fetchall()
    return [{"url": row["url"]} for row in rows]


# ---------------------------------------------------------------------------
# scan_cache (얼굴가드 순찰 결과 캐시 — job_id별 최신 결과 1건만 유지)
# ---------------------------------------------------------------------------


def get_scan_cache(job_id: str) -> list[dict[str, Any]] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT matches_json FROM scan_cache WHERE job_id = ?", (job_id,)
        ).fetchone()
    return json.loads(row["matches_json"]) if row else None


def set_scan_cache(job_id: str, matches: list[dict[str, Any]]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scan_cache (job_id, matches_json) VALUES (?, ?)
            ON CONFLICT(job_id) DO UPDATE SET matches_json = excluded.matches_json
            """,
            (job_id, json.dumps(matches, ensure_ascii=False)),
        )


# ---------------------------------------------------------------------------
# app_state (단일 값 상태: 확정 후보 id, 신고서 초안 덮어쓰기, 신고 건수)
# ---------------------------------------------------------------------------

_CONFIRMED_KEEP_IDS_KEY = "confirmed_keep_ids"
_DRAFT_OVERRIDES_KEY = "draft_overrides"
_REPORT_COUNT_KEY = "report_count"


def _get_state(key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set_state(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def _delete_state(key: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM app_state WHERE key = ?", (key,))


def get_confirmed_keep_ids() -> list[str]:
    raw = _get_state(_CONFIRMED_KEEP_IDS_KEY)
    return json.loads(raw) if raw else []


def set_confirmed_keep_ids(keep_ids: list[str]) -> None:
    _set_state(_CONFIRMED_KEEP_IDS_KEY, json.dumps(keep_ids, ensure_ascii=False))


def get_draft_overrides() -> list[dict[str, Any]] | None:
    raw = _get_state(_DRAFT_OVERRIDES_KEY)
    return json.loads(raw) if raw else None


def set_draft_overrides(fields: list[dict[str, Any]] | None) -> None:
    if fields is None:
        _delete_state(_DRAFT_OVERRIDES_KEY)
    else:
        _set_state(_DRAFT_OVERRIDES_KEY, json.dumps(fields, ensure_ascii=False))


def get_report_count() -> int:
    raw = _get_state(_REPORT_COUNT_KEY)
    return int(raw) if raw else 0


def increment_report_count() -> int:
    count = get_report_count() + 1
    _set_state(_REPORT_COUNT_KEY, str(count))
    return count


def reset_all() -> None:
    """테스트 전용: 모든 테이블을 비운다."""
    with _connect() as conn:
        conn.executescript(
            "DELETE FROM jobs; DELETE FROM manual_reports; "
            "DELETE FROM scan_cache; DELETE FROM app_state;"
        )
