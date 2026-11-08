import asyncio

import httpx
from watch2learn import app as app_module
from watch2learn.app import app
from watch2learn.dictionary import Cedict
from watch2learn.lesson import build_lesson, vocabulary_id
from watch2learn.subtitles import Cue


def make_lesson(monkeypatch, tmp_path) -> str:
    monkeypatch.setattr(app_module.jobs, "DB_PATH", tmp_path / "db.sqlite3")
    english = Cedict.from_text("學習 学习 [xue2 xi2] /to study/\n中文 中文 [Zhong1 wen2] /Chinese/")
    vietnamese = Cedict.from_text(
        "學習 学习 [xue2 xi2] /học/\n中文 中文 [Zhong1 wen2] /tiếng Trung/"
    )
    lesson = build_lesson(
        [Cue("cue-1", 0, 1000, "你好。"), Cue("cue-2", 1000, 3000, "今天学习中文。")],
        english,
        vietnamese,
        [{"translation_vi": "Xin chào."}, {"translation_vi": "Hôm nay học tiếng Trung."}],
    )
    job = app_module.jobs.create("fp", "a.mp4", tmp_path, tmp_path / "a.mp4", None)
    app_module.jobs.complete(job["id"], {"filename": "a.mp4", **lesson})
    return job["id"]


async def run(steps):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await steps(client)


def test_words_are_saved_with_lesson_context_and_progress(monkeypatch, tmp_path):
    lesson_id = make_lesson(monkeypatch, tmp_path)
    study = vocabulary_id("学习")

    async def steps(client):
        missing = await client.put(f"/api/library/words/{study}", json={"status": "saved"})
        assert missing.status_code == 422  # a new word needs its lesson context
        saved = await client.put(
            f"/api/library/words/{study}",
            json={"status": "saved", "lesson_id": lesson_id, "cue_id": "cue-2"},
        )
        row = saved.json()
        assert row["word"] == "学习" and row["meaning"] == "học"
        assert row["sentence"] == "今天学习中文。"
        assert row["sentence_translation"] == "Hôm nay học tiếng Trung."
        assert row["start_ms"] == 1000

        learned = await client.put(
            f"/api/library/words/{study}", json={"status": "learned", "own_meaning": "học tập"}
        )
        assert learned.json()["status"] == "learned"
        assert learned.json()["sentence"] == "今天学习中文。"  # context kept on update

        state = (await client.get("/api/library/state")).json()
        assert state["words"][study] == {"status": "learned", "own_meaning": "học tập"}
        assert (await client.get("/api/library/words?status=saved")).json() == []
        words = (await client.get("/api/library/words?status=learned")).json()
        assert words[0]["lesson_exists"] is True

        lessons = (await client.get("/api/lessons")).json()
        assert lessons[0]["learned_count"] == 1
        assert "vocabulary_ids" not in lessons[0]

        bad = await client.put("/api/library/words/../../etc", json={"status": "saved"})
        assert bad.status_code in (404, 422)
        assert (await client.delete(f"/api/library/words/{study}")).status_code == 204

    asyncio.run(run(steps))


def test_sentences_are_saved_from_the_lesson_not_from_the_client(monkeypatch, tmp_path):
    lesson_id = make_lesson(monkeypatch, tmp_path)

    async def steps(client):
        response = await client.put(
            f"/api/library/sentences/{lesson_id}/cue-2", json={"status": "saved", "text": "x"}
        )
        row = response.json()
        assert row["text"] == "今天学习中文。"
        assert row["pinyin"] == "jīn tiān xué xí zhōng wén"
        assert row["translation"] == "Hôm nay học tiếng Trung."
        again = await client.put(
            f"/api/library/sentences/{lesson_id}/cue-2", json={"status": "learned"}
        )
        assert again.json()["status"] == "learned"
        unknown = await client.put(f"/api/library/sentences/{lesson_id}/nope", json={})
        assert unknown.status_code == 404
        listed = (await client.get("/api/library/sentences?status=learned")).json()
        assert listed[0]["sentence_id"] == f"{lesson_id}:cue-2"
        assert (await client.delete(f"/api/library/sentences/{lesson_id}/cue-2")).status_code == 204

    asyncio.run(run(steps))


def test_browser_known_words_are_imported_once(monkeypatch, tmp_path):
    make_lesson(monkeypatch, tmp_path)
    study, chinese = vocabulary_id("学习"), vocabulary_id("中文")

    async def steps(client):
        result = await client.post(
            "/api/library/import",
            json={"learned": [study, "word-000000000000"], "meanings": {chinese: "tiếng Hoa"}},
        )
        assert result.json() == {"imported": 2, "not_found": 1}
        state = (await client.get("/api/library/state")).json()["words"]
        assert state[study]["status"] == "learned"
        assert state[chinese] == {"status": "saved", "own_meaning": "tiếng Hoa"}

    asyncio.run(run(steps))
