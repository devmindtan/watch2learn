import asyncio
import json

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


def read_events(body: dict) -> list[dict]:
    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/explain", json=body)
            assert response.headers["content-type"].startswith("application/x-ndjson")
            return [json.loads(line) for line in response.text.splitlines() if line]

    return asyncio.run(scenario())


WORD_REPLY = (
    "<giao_tiep>Hay gặp ở trường, 动词 dùng trang trọng vừa phải.</giao_tiep>\n"
    "<su_dung>Thường đi với 中文 (tiếng Trung).</su_dung>\n"
    "<vi_du>我们一起学习。 | Chúng ta cùng học.</vi_du>\n<vi_du>không có chữ Hán | x</vi_du>"
)


def test_word_lesson_streams_vietnamese_sections_and_is_cached(monkeypatch, tmp_path):
    lesson_id = make_lesson(monkeypatch, tmp_path)
    prompts = []

    def fake_stream(prompt):
        prompts.append(prompt)
        for start in range(0, len(WORD_REPLY), 7):  # tags arrive split across chunks
            yield WORD_REPLY[start : start + 7]

    monkeypatch.setattr(explain, "stream_ollama", fake_stream)
    body = {"lesson_id": lesson_id, "word_id": vocabulary_id("学习"), "cue_id": "cue-2"}
    events = read_events(body)

    assert events[0]["type"] == "facts"
    assert events[0]["facts"]["syllables"] == [
        {"character": "学", "pinyin": "xué", "tone": 2},
        {"character": "习", "pinyin": "xí", "tone": 2},
    ]
    sections = {event["key"]: event["text"] for event in events if event["type"] == "section"}
    assert list(sections) == ["giao_tiep", "su_dung"]
    assert sections["giao_tiep"] == "Hay gặp ở trường, động từ dùng trang trọng vừa phải."
    examples = [event for event in events if event["type"] == "example"]
    assert examples == [
        {
            "type": "example",
            "zh": "我们一起学习。",
            "vi": "Chúng ta cùng học.",
            "pinyin": "wǒ men yì qǐ xué xí",
        }
    ]
    assert events[-1] == {"type": "done", "cached": False}
    assert "gần “x” tiếng Việt" in prompts[0] and "今天学习中文。" in prompts[0]
    assert events[0]["facts"]["tips"][0].startswith("Chữ 学:")

    again = read_events(body)
    assert len(prompts) == 1 and again[-1] == {"type": "done", "cached": True}
    assert [event.get("text") for event in again[1:-1]] == [
        event.get("text") for event in events[1:-1]
    ]


def test_sentence_lesson_and_offline_fallback(monkeypatch, tmp_path):
    lesson_id = make_lesson(monkeypatch, tmp_path)
    prompts = []

    def fake_stream(prompt):
        prompts.append(prompt)
        yield "<giao_tiep>Nói khi kể lịch học.</giao_tiep><cau_truc>Thời gian đứng trước động từ."
        yield "</cau_truc><vi_du>明天学习。 | Ngày mai học.</vi_du>"

    monkeypatch.setattr(explain, "stream_ollama", fake_stream)
    events = read_events({"lesson_id": lesson_id, "cue_id": "cue-2"})
    assert {"type": "section", "key": "cau_truc", "text": "Thời gian đứng trước động từ."} in events
    assert "学习 = học" in prompts[0]
    assert [item["character"] for item in events[0]["facts"]["syllables"]][:2] == ["今", "天"]

    def offline(prompt):
        raise OSError("connection refused")
        yield ""

    monkeypatch.setattr(explain, "stream_ollama", offline)
    fallback = read_events({"lesson_id": lesson_id, "cue_id": "cue-1"})
    assert fallback[0]["facts"]["syllables"][0]["character"] == "你"
    assert fallback[1]["type"] == "error" and "Ollama" in fallback[1]["message"]


def test_pronunciation_tips_cover_tone_changes_and_hard_sounds():
    tips = pronunciation.learner_tips(pronunciation.han_syllables("你好"))
    assert tips[0].startswith("你好 có hai thanh 3 liền nhau")
    shi = pronunciation.learner_tips(pronunciation.han_syllables("老师"))
    assert shi == [
        "Chữ 师: phụ âm đầu uốn đầu lưỡi lên, gần “s” tiếng Việt đọc nặng; "
        "vần đọc gần “ư” có uốn lưỡi, không đọc “i”."
    ]
    bushi = pronunciation.learner_tips([("不", "bu2"), ("是", "shi4")])
    assert any("不 đứng trước thanh 4" in tip for tip in bushi)
