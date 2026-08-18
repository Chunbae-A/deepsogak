"""딥소각 서버의 영속 저장소.

이전에는 프로토타입 인메모리 dict/list(JOBS, _manual_reports, _confirmed_keep_ids,
_draft_overrides, REPORT_COUNT, _scan_cache)에만 상태를 두어 서버를 재시작하면
전부 사라졌다. 이 모듈은 같은 데이터를 SQLite 파일(data/deepsogak.db)에
저장해 재시작·다른 프로세스 간에도 유지되도록 한다. DB 파일은 반드시
/static으로 서빙되는 storage/ 트리 밖에 둔다 — 안에 두면 인증 없이
그대로 다운로드된다(#75).

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
    protected_path TEXT,
    sha256 TEXT,
    phash TEXT,
    created_at REAL NOT NULL,
    deepbaeksin_applied INTEGER NOT NULL DEFAULT 0,
    deepbaeksin_meta TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    error_reason TEXT,
    owner_id TEXT
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
        _migrate_add_columns(conn)


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """비동기 처리(status/error_reason 컬럼)를 추가하기 전에 만들어진 DB 파일도
    계속 쓸 수 있도록, 없는 컬럼만 추가한다. protected_path/sha256/phash의
    NOT NULL 제약까지는 옮기지 않는다 — 이 저장소는 아직 실사용 데이터가 없는
    프로토타입이라, 그 정도로 오래된 DB 파일은 data/deepsogak.db를 지우고
    새로 시작하는 편이 이 마이그레이션 코드를 유지하는 것보다 간단하다.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "status" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
    if "error_reason" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN error_reason TEXT")
    if "owner_id" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN owner_id TEXT")


def _require_path() -> Path:
    if _DB_PATH is None:
        raise RuntimeError("init_db()를 먼저 호출해야 합니다.")
    return _DB_PATH


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_require_path())
    conn.row_factory = sqlite3.Row
    # WAL(Write-Ahead Logging)은 쓰기 하나가 읽기 전체를 막는 SQLite 기본 동작을
    # 완화해, 팀원 여러 명이 동시에 서버를 두드려도 잠금 경합이 덜 생기게 한다.
    # busy_timeout은 그래도 잠깐 잠기는 순간에 바로 실패하지 않고 잠시 재시도하게 한다.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
    owner_id: str | None = None,
) -> None:
    """이미 처리가 끝난 작업을 한 번에 기록한다(주로 테스트·단발성 스크립트용).

    실제 서버는 대신 create_pending_job()으로 즉시 jobId를 내주고,
    complete_job()/fail_job()으로 백그라운드 처리 결과를 나중에 채운다
    (POST /api/protection/process가 딥백신 처리를 기다리지 않도록 하기 위함).
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (id, original_path, protected_path, sha256, phash, created_at,
                 deepbaeksin_applied, deepbaeksin_meta, status, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
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
                owner_id,
            ),
        )


def create_pending_job(
    job_id: str, *, original_path: Path, created_at: float, owner_id: str | None = None
) -> None:
    """원본만 저장된 상태로 작업을 만든다. 딥백신 처리는 아직 안 끝났다.

    owner_id: #77 스캐폴딩용 컬럼. 지금은 아무도 값을 채워 보내지 않아
    항상 NULL이고, get_latest_completed_job()도 아직 이 값으로 필터링하지
    않는다(기존 "서버 인스턴스 하나 = 사용자 한 명" 동작 그대로 유지).
    클라이언트가 실제 식별자를 보내도록 정하고 나면 이 컬럼과
    get_latest_completed_job(owner_id=...)를 실제로 연결한다.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, original_path, created_at, status, owner_id)
            VALUES (?, ?, ?, 'processing', ?)
            """,
            (job_id, str(original_path), created_at, owner_id),
        )


def complete_job(
    job_id: str,
    *,
    protected_path: Path,
    sha256: str,
    phash: str,
    deepbaeksin_applied: bool,
    deepbaeksin_meta: dict[str, Any] | None,
) -> None:
    """백그라운드 딥백신 처리가 끝난 pending job을 completed로 채운다."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET protected_path = ?, sha256 = ?, phash = ?, deepbaeksin_applied = ?,
                deepbaeksin_meta = ?, status = 'completed', error_reason = NULL
            WHERE id = ?
            """,
            (
                str(protected_path),
                sha256,
                phash,
                1 if deepbaeksin_applied else 0,
                json.dumps(deepbaeksin_meta, ensure_ascii=False) if deepbaeksin_meta else None,
                job_id,
            ),
        )


def fail_job(job_id: str, *, reason: str) -> None:
    """백그라운드 처리 중 예외가 나면 실패 사유를 남긴다(원본은 그대로 둔다)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', error_reason = ? WHERE id = ?",
            (reason, job_id),
        )


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "originalPath": Path(row["original_path"]),
        "protectedPath": Path(row["protected_path"]) if row["protected_path"] else None,
        "sha256": row["sha256"],
        "phash": row["phash"],
        "createdAt": row["created_at"],
        "deepbaeksinApplied": bool(row["deepbaeksin_applied"]),
        "deepbaeksinMeta": json.loads(row["deepbaeksin_meta"]) if row["deepbaeksin_meta"] else None,
        "status": row["status"],
        "errorReason": row["error_reason"],
        "ownerId": row["owner_id"],
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def get_latest_completed_job(
    *, owner_id: str | None = None
) -> tuple[str, dict[str, Any]] | None:
    """얼굴가드 순찰 등에 쓸, 가장 최근에 '완료된' 보호사진을 찾는다.

    아직 처리 중이거나 실패한 job은 protected_path가 없어 순찰 대상이 될 수
    없으므로 completed만 본다.

    owner_id: #77 스캐폴딩용. None(기본값)이면 지금까지와 동일하게 DB
    전체에서 가장 최근 job을 돌려준다(서버 인스턴스 하나 = 사용자 한 명
    전제). 값을 넘기면 그 owner_id로만 좁혀서 찾는다 — 다만 지금은
    create_pending_job()을 부르는 쪽(main.py) 어디도 owner_id를 채워
    보내지 않으므로, 값을 넘겨도 매칭되는 job이 없을 수 있다. 실제로
    쓰려면 클라이언트 식별자를 받는 부분이 먼저 필요하다(#77 본문 참고).
    """
    with _connect() as conn:
        if owner_id is None:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'completed' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM jobs WHERE status = 'completed' AND owner_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (owner_id,),
            ).fetchone()
    if row is None:
        return None
    return row["id"], _row_to_job(row)


def count_completed_jobs() -> int:
    with _connect() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'completed'"
        ).fetchone()
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
    # 읽고 나서 1 더해 다시 쓰는 방식(get_report_count() + 1)은 동시에 두 요청이
    # 들어오면 하나의 증가분을 잃어버릴 수 있다(lost update). INSERT ... ON
    # CONFLICT ... DO UPDATE 한 문장으로 증가를 SQLite 트랜잭션 안에서 원자적으로
    # 처리해 이 경합을 없앤다.
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_state (key, value) VALUES (?, '1')
            ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1
            """,
            (_REPORT_COUNT_KEY,),
        )
        row = conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (_REPORT_COUNT_KEY,)
        ).fetchone()
    return int(row["value"])


def reset_all() -> None:
    """테스트 전용: 모든 테이블을 비운다."""
    with _connect() as conn:
        conn.executescript(
            "DELETE FROM jobs; DELETE FROM manual_reports; "
            "DELETE FROM scan_cache; DELETE FROM app_state;"
        )
