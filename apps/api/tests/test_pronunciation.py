import asyncio

import httpx
import pytest
from test_learning import make_lesson
from watch2learn import app as app_module
from watch2learn import explain, learning, pronunciation
from watch2learn.app import app
from watch2learn.lesson import vocabulary_id


def test_scores_compare_pinyin_not_characters():
    perfect = pronunciation.score_pronunciation("我捡到了一部手机", "我撿到了一部手機。")
    assert perfect["score"] == 100
    homophone = pronunciation.score_pronunciation("学习", "学席")  # 习 and 席 are both xí
    assert homophone["score"] == 100
    wrong_tone = pronunciation.score_pronunciation("买", "卖")  # mǎi vs mài
    assert wrong_tone["score"] == 75
    assert wrong_tone["syllables"][0]["tone"] is False
    missing = pronunciation.score_pronunciation(
        "今天放学以后我一个人去学校", "今天放学以后我一个人回家"
    )
    assert 60 <= missing["score"] <= 85
    assert [item["heard"] for item in missing["syllables"][-3:]] == [None, None, None]
    assert pronunciation.score_pronunciation("你好", "")["score"] == 0
    with pytest.raises(ValueError):
        pronunciation.score_pronunciation("hello", "你好")


def test_recording_endpoint_scores_and_records_progress(monkeypatch, tmp_path):
    lesson_id = make_lesson(monkeypatch, tmp_path)
    monkeypatch.setattr(app_module, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(
        app_module, "extract_asr_audio", lambda source, output: output.write_bytes(b"") or output
    )
    monkeypatch.setattr(app_module, "probe_media", lambda path: {"format": {"duration": "1.4"}})
    monkeypatch.setattr(app_module, "transcribe_clip", lambda path: "学习")
    study = vocabulary_id("学习")
    learning.save_word(
        study,
        "saved",
        None,
        lesson_id,
        {
            "word": "学习",
            "traditional": None,
            "pinyin": "xué xí",
            "meaning": "học",
            "cue_id": "cue-2",
            "sentence": "今天学习中文。",
            "sentence_translation": None,
            "start_ms": 1000,
            "end_ms": 3000,
        },
    )

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"audio": ("take.webm", b"opus", "audio/webm")}
            data = {"target": "学习", "kind": "word", "item_id": study}
            result = (await client.post("/api/pronunciation", files=files, data=data)).json()
            assert result["score"] == 100
            bad = await client.post("/api/pronunciation", files=files, data={"target": "abc"})
            assert bad.status_code == 422

    asyncio.run(scenario())
    row = learning.get_word(study)
    assert (row["best_score"], row["last_score"], row["practice_count"]) == (100, 100, 1)
    assert not list((tmp_path / "jobs").iterdir())


def test_explanations_are_generated_once_per_context(monkeypatch, tmp_path):
    lesson_id = make_lesson(monkeypatch, tmp_path)
    calls = []

    def fake_ollama(prompt):
        calls.append(prompt)
        return "<think></think>**Trong câu này** 学习 nghĩa là học.\n- Dùng ở trường học."

    monkeypatch.setattr(explain, "ask_ollama", fake_ollama)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            body = {"lesson_id": lesson_id, "word_id": vocabulary_id("学习"), "cue_id": "cue-2"}
            first = (await client.post("/api/explain", json=body)).json()
            second = (await client.post("/api/explain", json=body)).json()
            return first, second

    first, second = asyncio.run(scenario())
    assert first["text"] == "Trong câu này 学习 nghĩa là học. Dùng ở trường học."
    assert first["cached"] is False and second["cached"] is True
    assert len(calls) == 1 and "今天学习中文。" in calls[0]
