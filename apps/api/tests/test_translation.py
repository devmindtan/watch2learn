import asyncio

import httpx
import pytest
from watch2learn import app as app_module
from watch2learn import translation
from watch2learn.app import app
from watch2learn.subtitles import Cue


def test_only_comma_continued_cues_are_translated_together():
    cues = [
        Cue("cue-1", 0, 1000, "如果明天不下雨，"),
        Cue("cue-2", 1200, 2500, "我们就去爬山。"),
        Cue("cue-3", 2600, 3500, "今天放学以后我一个人回家"),
        Cue("cue-4", 3600, 4500, "天气很好"),
        Cue("cue-5", 4600, 5000, "我走的很慢，"),
        Cue("cue-6", 9000, 10000, "停下来。"),
    ]
    # Unpunctuated cues are whole sentences in real subtitles; a long pause ends a group.
    assert translation.sentence_groups(cues) == [[0, 1], [2], [3], [4], [5]]
    assert translation.join_cue_text(["我昨天去了一家", "很有名的餐厅。"]) == (
        "我昨天去了一家，很有名的餐厅。"
    )


def test_context_rows_share_one_sentence_translation(monkeypatch):
    seen = []

    def fake_translate(texts):
        seen.extend(texts)
        return [f"vi:{text}" for text in texts]

    monkeypatch.setattr(translation, "translate_to_vietnamese", fake_translate)
    rows = translation.translate_cues_in_context(
        [Cue("a", 0, 1000, "如果明天不下雨，"), Cue("b", 1100, 2000, "我们就去爬山。")]
    )
    assert seen == ["如果明天不下雨，我们就去爬山。"]  # no doubled comma
    assert rows[0] == rows[1]
    assert rows[0]["translation_group"] == "a"
    assert rows[0]["translation_group_end"] == "b"


def test_saved_lesson_translation_backfill_is_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.jobs, "DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr(translation, "model_ready", lambda: True)
    monkeypatch.setattr(
        translation, "translate_to_vietnamese", lambda texts: [f"vi:{text}" for text in texts]
    )
    job = app_module.jobs.create("fp", "old.mp4", tmp_path, tmp_path / "x.mp4", None)
    app_module.jobs.complete(
        job["id"],
        {
            "cues": [
                {"id": "cue-1", "start_ms": 0, "end_ms": 900, "text": "你好。"},
                {"id": "cue-2", "start_ms": 1000, "end_ms": 2000, "text": "再见。"},
            ],
            "vocabulary": [],
        },
    )

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(f"/api/lessons/{job['id']}/translations")

    response = asyncio.run(scenario())
    assert response.status_code == 200
    assert [cue["translation_vi"] for cue in response.json()["cues"]] == ["vi:你好。", "vi:再见。"]
    saved = app_module.jobs.get(job["id"])["result"]
    assert saved["translation"]["unit"] == translation.TRANSLATION_UNIT
    assert saved["cues"][1]["translation_vi"] == "vi:再见。"


@pytest.mark.skipif(not translation.model_ready(), reason="run pnpm setup:translation")
def test_local_model_translates_mandarin_to_vietnamese():
    result = translation.translate_to_vietnamese(["我们今天去看电影吧。", "", "你好"])
    assert "phim" in result[0].lower()
    assert result[1] == ""
    assert result[2]


def test_model_markup_is_removed_from_translations():
    assert translation.clean_output("{\\cHFAEBB8} Xin chào <i>bạn</i>") == "Xin chào bạn"


@pytest.mark.skipif(not translation.model_ready(), reason="run pnpm setup:translation")
def test_bracketed_stage_direction_translates_inner_text():
    result = translation.translate_to_vietnamese(["（轻轻地哼着歌）"])[0]
    assert result.startswith("(") and result.endswith(")")
    assert "{" not in result and "\\" not in result


def test_only_chinese_is_sent_for_translation(monkeypatch):
    assert translation.chinese_source("I love Beijing ♪") == ""
    assert translation.chinese_source("こんにちは、元気ですか") == ""
    assert translation.chinese_source("안녕하세요") == ""
    assert translation.chinese_source("Xin chào các bạn") == ""
    assert translation.chinese_source("我喜欢iPhone。") == "我喜欢iPhone。"
    assert translation.chinese_source("Daily routine in Chinese 日常生活") == "日常生活"
    # Vietnamese teaching mixed into one line (screenshot of a real lesson).
    assert translation.chinese_source("Tôi đến đây,我来了,我先走。") == "我来了,我先走。"
    assert translation.chinese_source("Tôi đi trước nhé, 我先走, tận 一下.") == "我先走,"
    assert translation.chinese_source("Đợi mục chúc, tận 一下, quay đi.") == ""
    assert translation.chinese_source("快 一点 , nhén lén mục chúc, quay đi.") == "快 一点 ,"
    assert translation.chinese_source("nǐ hǎo 你好") == ""  # pinyin is not translated

    seen = []

    def fake_translate(texts):
        seen.extend(texts)
        return [f"vi:{text}" for text in texts]

    monkeypatch.setattr(translation, "translate_to_vietnamese", fake_translate)
    rows = translation.translate_cues_in_context(
        [
            Cue("a", 0, 1000, "如果明天不下雨，"),
            Cue("b", 1100, 2000, "OK, let's go"),
            Cue("c", 2100, 3000, "我们就去爬山。"),
        ]
    )
    assert "OK, let's go" not in seen and all("let" not in text for text in seen)
    assert rows[1]["translation_vi"] == ""
    assert rows[1]["translation_skipped"] == "not-chinese"
    assert rows[0]["translation_group_end"] == "a"  # foreign line breaks the sentence group
    assert rows[2]["translation_vi"] == "vi:我们就去爬山。"


def test_startup_upgrade_translates_saved_lessons_once(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.jobs, "DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr(translation, "model_ready", lambda: True)
    calls = []

    def fake_translate(texts):
        calls.append(texts)
        return [f"vi:{text}" for text in texts]

    monkeypatch.setattr(translation, "translate_to_vietnamese", fake_translate)
    job = app_module.jobs.create("fp", "old.mp4", tmp_path, tmp_path / "x.mp4", None)
    cue = {"id": "cue-1", "start_ms": 0, "end_ms": 900, "text": "你好。", "translation_vi": "cũ"}
    app_module.jobs.complete(job["id"], {"cues": [cue], "vocabulary": []})

    app_module.upgrade_saved_lessons()
    app_module.upgrade_saved_lessons()

    assert len(calls) == 1
    saved = app_module.jobs.get(job["id"])["result"]
    assert saved["cues"][0]["translation_vi"] == "vi:你好。"
    assert app_module.translation_is_current(saved)


def test_old_lessons_get_context_readings_without_losing_text_or_translation(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.jobs, "DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr(translation, "model_ready", lambda: False)
    job = app_module.jobs.create("fp", "old.mp4", tmp_path, tmp_path / "x.mp4", None)
    old_cue = {
        "id": "cue-1",
        "start_ms": 6220,
        "end_ms": 9000,
        "text": "上一集,我撿到了一個手機",
        "translation_vi": "Tập trước, tôi nhặt được một cái điện thoại.",
        "segments": [{"text": "上", "vocabulary_id": "x", "pinyin": "shǎng"}],
    }
    app_module.jobs.complete(job["id"], {"cues": [old_cue], "vocabulary": [], "filename": "a"})

    app_module.upgrade_saved_lessons()

    saved = app_module.jobs.get(job["id"])["result"]
    cue = saved["cues"][0]
    assert cue["text"] == "上一集,我捡到了一个手机" and cue["start_ms"] == 6220
    assert cue["text_original"] == old_cue["text"]
    assert cue["translation_vi"] == old_cue["translation_vi"]
    segment = next(item for item in cue["segments"] if item["text"] == "上")
    assert segment["pinyin"] == "shàng"
    assert saved["analysis"]["version"] == app_module.ANALYSIS_VERSION
    assert saved["filename"] == "a"


def test_mixed_line_only_learns_the_chinese_clauses():
    from watch2learn.lesson import cue_tokens
    from watch2learn.subtitles import Cue

    tokens = cue_tokens(Cue("c", 0, 1000, "Tôi đi trước nhé, 我先走, tận 一下."))
    words = [token["text"] for token in tokens if token.get("vocabulary_id")]
    assert "".join(words) == "我先走"
    assert "".join(token["text"] for token in tokens) == "Tôi đi trước nhé, 我先走, tận 一下."
    foreign = [token["text"] for token in tokens if token.get("foreign")]
    assert foreign == ["Tôi đi trước nhé,", " tận 一下."]
    first = next(token for token in tokens if token.get("vocabulary_id"))
    assert "Tôi đi trước nhé, 我先走"[first["start_offset"]] == "我"
