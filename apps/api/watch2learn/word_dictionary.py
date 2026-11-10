"""Global word dictionary shared by every video.

One entry per word and reading: the offline Vietnamese meanings, the videos where
the word occurs, and the AI lesson (how it is used, native examples, notes). The
lesson is written once; a later video containing the word reuses it. Entries stay
when a video is deleted, so nothing already written is lost; only the video link
goes. A learner can ask for a lesson to be rewritten (clear_lesson).
"""

import json

from .jobs import connect, initialize, now


def initialize_dictionary() -> None:
    initialize()
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dictionary_words (
                word_id TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                word TEXT NOT NULL,
                traditional TEXT,
                meanings_json TEXT NOT NULL,
                lesson_json TEXT,
                lesson_version TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (word_id, pinyin)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dictionary_sources (
                word_id TEXT NOT NULL,
                pinyin TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL,
                PRIMARY KEY (word_id, pinyin, lesson_id)
            )
            """
        )


def meanings(word: dict) -> list[str]:
    return [item for item in word.get("definitions_vi", []) if ":" not in item[:3]]


def register_lesson(lesson_id: str, vocabulary: list[dict]) -> None:
    """Add every word of a video (idempotent: re-registering replaces its links)."""
    initialize_dictionary()
    timestamp = now()
    with connect() as connection:
        connection.execute("DELETE FROM dictionary_sources WHERE lesson_id = ?", (lesson_id,))
        for word in vocabulary:
            key = (word["id"], word.get("pinyin") or "")
            connection.execute(
                """
                INSERT INTO dictionary_words
                    (word_id, pinyin, word, traditional, meanings_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (word_id, pinyin) DO UPDATE SET
                    meanings_json = excluded.meanings_json, traditional = excluded.traditional
                """,
                (
                    *key,
                    word["word"],
                    word.get("traditional"),
                    json.dumps(meanings(word), ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO dictionary_sources VALUES (?, ?, ?, ?)",
                (*key, lesson_id, word.get("occurrence_count", 0)),
            )


def forget_lesson(lesson_id: str) -> None:
    initialize_dictionary()
    with connect() as connection:
        connection.execute("DELETE FROM dictionary_sources WHERE lesson_id = ?", (lesson_id,))


def stored_lesson(word: dict, version: str) -> list[dict] | None:
    initialize_dictionary()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT lesson_json FROM dictionary_words
            WHERE word_id = ? AND pinyin = ? AND lesson_version = ?
            """,
            (word["id"], word.get("pinyin") or "", version),
        ).fetchone()
    return json.loads(row["lesson_json"]) if row and row["lesson_json"] else None


def save_lesson(word: dict, events: list[dict], version: str) -> None:
    initialize_dictionary()
    timestamp = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO dictionary_words
                (word_id, pinyin, word, traditional, meanings_json, lesson_json, lesson_version,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (word_id, pinyin) DO UPDATE SET
                lesson_json = excluded.lesson_json, lesson_version = excluded.lesson_version,
                updated_at = excluded.updated_at
            """,
            (
                word["id"],
                word.get("pinyin") or "",
                word["word"],
                word.get("traditional"),
                json.dumps(meanings(word), ensure_ascii=False),
                json.dumps(events, ensure_ascii=False),
                version,
                timestamp,
                timestamp,
            ),
        )


def clear_lesson(word: dict) -> None:
    """The learner asked for a new lesson: the next request writes it again."""
    initialize_dictionary()
    with connect() as connection:
        connection.execute(
            """
            UPDATE dictionary_words SET lesson_json = NULL, lesson_version = NULL
            WHERE word_id = ? AND pinyin = ?
            """,
            (word["id"], word.get("pinyin") or ""),
        )


def entries(version: str, query: str = "", limit: int = 5000) -> dict:
    """Dictionary rows, most widespread first, with the newest video that has each word."""
    initialize_dictionary()
    like = f"%{query}%"
    with connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM dictionary_words").fetchone()[0]
        rows = connection.execute(
            """
            SELECT d.word_id, d.pinyin, d.word, d.traditional, d.meanings_json,
                   d.lesson_version = ? AS has_lesson,
                   COUNT(s.lesson_id) AS video_count,
                   COALESCE(SUM(s.occurrence_count), 0) AS occurrence_count,
                   (SELECT s2.lesson_id FROM dictionary_sources s2
                    JOIN jobs j ON j.id = s2.lesson_id
                    WHERE s2.word_id = d.word_id AND s2.pinyin = d.pinyin
                    ORDER BY j.updated_at DESC LIMIT 1) AS lesson_id
            FROM dictionary_words d
            LEFT JOIN dictionary_sources s ON s.word_id = d.word_id AND s.pinyin = d.pinyin
            WHERE d.word LIKE ? OR d.pinyin LIKE ? OR d.meanings_json LIKE ?
            GROUP BY d.word_id, d.pinyin
            ORDER BY video_count DESC, occurrence_count DESC, d.word
            LIMIT ?
            """,
            (version, like, like, like, limit),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        senses = json.loads(item.pop("meanings_json"))
        item["meaning"] = senses[0] if senses else None
        item["meanings"] = senses
        item["has_lesson"] = bool(item["has_lesson"])
        items.append(item)
    return {"total": total, "entries": items}
