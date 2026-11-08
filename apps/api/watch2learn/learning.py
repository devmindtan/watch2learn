"""Learner library: saved/learned words and sentences, stored with their context.

Rows are filled from the lesson on the server (never from client-supplied text), so
every saved item keeps its original cue, translation, timestamp and lesson link.
"""

from .jobs import connect, initialize, now

STATUSES = ("saved", "learned")
SCORE_FIELDS = "best_score INTEGER, last_score INTEGER, practice_count INTEGER NOT NULL DEFAULT 0"


def initialize_learning() -> None:
    initialize()
    with connect() as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS learner_words (
                word_id TEXT PRIMARY KEY,
                word TEXT NOT NULL,
                traditional TEXT,
                pinyin TEXT,
                meaning TEXT,
                own_meaning TEXT,
                status TEXT NOT NULL,
                lesson_id TEXT,
                cue_id TEXT,
                sentence TEXT,
                sentence_translation TEXT,
                start_ms INTEGER,
                end_ms INTEGER,
                {SCORE_FIELDS},
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS learner_sentences (
                sentence_id TEXT PRIMARY KEY,
                lesson_id TEXT NOT NULL,
                cue_id TEXT NOT NULL,
                text TEXT NOT NULL,
                pinyin TEXT,
                translation TEXT,
                start_ms INTEGER,
                end_ms INTEGER,
                status TEXT NOT NULL,
                {SCORE_FIELDS},
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def sentence_id(lesson_id: str, cue_id: str) -> str:
    return f"{lesson_id}:{cue_id}"


def cue_pinyin(cue: dict) -> str:
    segments = cue.get("segments", [])
    return " ".join(segment["pinyin"] for segment in segments if segment.get("pinyin"))


def word_fields(lesson: dict, word_id: str, cue_id: str | None) -> dict | None:
    """Word data plus the occurrence context, taken from the saved lesson."""
    word = next((item for item in lesson.get("vocabulary", []) if item["id"] == word_id), None)
    if not word:
        return None
    occurrences = word.get("occurrences", [])
    occurrence = next((item for item in occurrences if item["cue_id"] == cue_id), None)
    occurrence = occurrence or (occurrences[0] if occurrences else {})
    cue = next(
        (item for item in lesson.get("cues", []) if item["id"] == occurrence.get("cue_id")), {}
    )
    meanings = word.get("definitions_vi") or []
    return {
        "word": word["word"],
        "traditional": word.get("traditional"),
        "pinyin": occurrence.get("pinyin") or word.get("pinyin"),
        "meaning": next((item for item in meanings if not item.startswith(("LT:", "CL:"))), None),
        "cue_id": occurrence.get("cue_id"),
        "sentence": occurrence.get("cue_text"),
        "sentence_translation": cue.get("translation_vi") or None,
        "start_ms": occurrence.get("start_ms"),
        "end_ms": occurrence.get("end_ms"),
    }


def save_word(
    word_id: str,
    status: str | None,
    own_meaning: str | None,
    lesson_id: str | None,
    fields: dict | None,
) -> dict | None:
    """Create or update a word. New words need lesson fields; updates keep context."""
    initialize_learning()
    timestamp = now()
    with connect() as connection:
        existing = connection.execute(
            "SELECT * FROM learner_words WHERE word_id = ?", (word_id,)
        ).fetchone()
        if not existing and not fields:
            return None
        if not existing:
            connection.execute(
                """
                INSERT INTO learner_words
                    (word_id, word, traditional, pinyin, meaning, own_meaning, status, lesson_id,
                     cue_id, sentence, sentence_translation, start_ms, end_ms, created_at,
                     updated_at)
                VALUES (:word_id, :word, :traditional, :pinyin, :meaning, :own_meaning,
                        :status, :lesson_id, :cue_id, :sentence, :sentence_translation,
                        :start_ms, :end_ms, :created_at, :updated_at)
                """,
                {
                    **fields,
                    "word_id": word_id,
                    "own_meaning": own_meaning or None,
                    "status": status or "saved",
                    "lesson_id": lesson_id,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            )
        else:
            updates = {"updated_at": timestamp}
            if status:
                updates["status"] = status
            if own_meaning is not None:
                updates["own_meaning"] = own_meaning or None
            assignments = ", ".join(f"{key} = :{key}" for key in updates)
            connection.execute(
                f"UPDATE learner_words SET {assignments} WHERE word_id = :word_id",
                {**updates, "word_id": word_id},
            )
    return get_word(word_id)


def get_word(word_id: str) -> dict | None:
    initialize_learning()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM learner_words WHERE word_id = ?", (word_id,)
        ).fetchone()
    return dict(row) if row else None


def list_words(status: str | None = None) -> list[dict]:
    initialize_learning()
    query = "SELECT * FROM learner_words"
    parameters: tuple = ()
    if status:
        query += " WHERE status = ?"
        parameters = (status,)
    with connect() as connection:
        rows = connection.execute(query + " ORDER BY updated_at DESC", parameters).fetchall()
    return [dict(row) for row in rows]


def delete_word(word_id: str) -> bool:
    initialize_learning()
    with connect() as connection:
        cursor = connection.execute("DELETE FROM learner_words WHERE word_id = ?", (word_id,))
    return cursor.rowcount > 0


def save_sentence(lesson_id: str, cue: dict, status: str | None) -> dict:
    initialize_learning()
    identifier = sentence_id(lesson_id, cue["id"])
    timestamp = now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learner_sentences
                (sentence_id, lesson_id, cue_id, text, pinyin, translation, start_ms, end_ms,
                 status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sentence_id) DO UPDATE SET
                status = COALESCE(?, learner_sentences.status),
                translation = excluded.translation,
                updated_at = excluded.updated_at
            """,
            (
                identifier,
                lesson_id,
                cue["id"],
                cue["text"],
                cue_pinyin(cue),
                cue.get("translation_vi") or None,
                cue["start_ms"],
                cue["end_ms"],
                status or "saved",
                timestamp,
                timestamp,
                status,
            ),
        )
    return get_sentence(identifier)


def get_sentence(identifier: str) -> dict | None:
    initialize_learning()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM learner_sentences WHERE sentence_id = ?", (identifier,)
        ).fetchone()
    return dict(row) if row else None


def list_sentences(status: str | None = None) -> list[dict]:
    initialize_learning()
    query = "SELECT * FROM learner_sentences"
    parameters: tuple = ()
    if status:
        query += " WHERE status = ?"
        parameters = (status,)
    with connect() as connection:
        rows = connection.execute(query + " ORDER BY updated_at DESC", parameters).fetchall()
    return [dict(row) for row in rows]


def delete_sentence(identifier: str) -> bool:
    initialize_learning()
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM learner_sentences WHERE sentence_id = ?", (identifier,)
        )
    return cursor.rowcount > 0


def record_score(kind: str, identifier: str, score: int) -> None:
    """Keep the latest and best pronunciation score of a saved word or sentence."""
    initialize_learning()
    table, key = (
        ("learner_words", "word_id") if kind == "word" else ("learner_sentences", "sentence_id")
    )
    with connect() as connection:
        connection.execute(
            f"""
            UPDATE {table}
            SET last_score = ?, best_score = MAX(COALESCE(best_score, 0), ?),
                practice_count = practice_count + 1, updated_at = ?
            WHERE {key} = ?
            """,
            (score, score, now(), identifier),
        )


def learner_state() -> dict:
    """Compact maps the lesson screen needs to mark words and sentences."""
    return {
        "words": {
            row["word_id"]: {"status": row["status"], "own_meaning": row["own_meaning"]}
            for row in list_words()
        },
        "sentences": {row["sentence_id"]: row["status"] for row in list_sentences()},
    }
