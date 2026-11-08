"""Durable local processing jobs and completed lessons."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "watch2learn.sqlite3"


def now() -> str:
    return datetime.now(UTC).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    with connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                filename TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL,
                error TEXT,
                result_json TEXT,
                work_dir TEXT,
                source_path TEXT,
                subtitle_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS jobs_fingerprint ON jobs(fingerprint, status)"
        )


def create(
    fingerprint: str,
    filename: str,
    work_dir: Path,
    source_path: Path,
    subtitle_path: Path | None,
) -> dict:
    initialize()
    job_id = uuid4().hex
    timestamp = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs
                (id, fingerprint, filename, status, stage, progress, work_dir,
                 source_path, subtitle_path, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', 'uploaded', 5, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                fingerprint,
                filename,
                str(work_dir),
                str(source_path),
                str(subtitle_path) if subtitle_path else None,
                timestamp,
                timestamp,
            ),
        )
    return get(job_id)


def find_completed(fingerprint: str) -> dict | None:
    initialize()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM jobs
            WHERE fingerprint = ? AND status = 'complete'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()
    return serialize(row) if row else None


def update(job_id: str, stage: str, progress: int) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs SET status = 'processing', stage = ?, progress = ?, updated_at = ?
            WHERE id = ?
            """,
            (stage, max(0, min(99, progress)), now(), job_id),
        )


def complete(job_id: str, result: dict) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'complete', stage = 'complete', progress = 100,
                filename = COALESCE(?, filename), result_json = ?, error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (result.get("filename"), json.dumps(result, ensure_ascii=False), now(), job_id),
        )


def save_result(job_id: str, result: dict) -> None:
    """Persist an enriched lesson (e.g. backfilled translations) without reordering."""
    with connect() as connection:
        connection.execute(
            "UPDATE jobs SET result_json = ? WHERE id = ? AND status = 'complete'",
            (json.dumps(result, ensure_ascii=False), job_id),
        )


def delete(job_id: str) -> bool:
    initialize()
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM jobs WHERE id = ? AND status IN ('complete', 'failed')", (job_id,)
        )
    return cursor.rowcount > 0


def fail(job_id: str, error: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'failed', stage = 'failed', error = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, now(), job_id),
        )


def serialize(row: sqlite3.Row) -> dict:
    item = dict(row)
    result_json = item.pop("result_json")
    item.pop("fingerprint")
    item.pop("work_dir")
    item.pop("source_path")
    item.pop("subtitle_path")
    item["result"] = json.loads(result_json) if result_json else None
    return item


def get(job_id: str) -> dict | None:
    initialize()
    with connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return serialize(row) if row else None


def completed_ids() -> list[str]:
    initialize()
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM jobs WHERE status = 'complete' ORDER BY updated_at DESC"
        ).fetchall()
    return [row["id"] for row in rows]


def recent_lessons(limit: int = 30) -> list[dict]:
    initialize()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM jobs WHERE status = 'complete'
            ORDER BY updated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    lessons = []
    for row in rows:
        job = serialize(row)
        result = job.pop("result")
        lessons.append(
            {
                **job,
                "vocabulary_count": len(result.get("vocabulary", [])),
                "transcript_method": result.get("transcript", {}).get("method"),
                "source_kind": result.get("source", {}).get("kind", "file"),
            }
        )
    return lessons


def pending() -> list[dict]:
    initialize()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, filename, work_dir, source_path, subtitle_path
            FROM jobs WHERE status IN ('queued', 'processing')
            ORDER BY created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]
