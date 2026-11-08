from watch2learn.dictionary import Cedict
from watch2learn.lesson import add_vietnamese_definitions, build_lesson
from watch2learn.subtitles import Cue


def test_lesson_preserves_neighbor_context_and_dictionary_provenance(tmp_path):
    source = tmp_path / "cedict_ts.u8"
    dictionary = Cedict.from_text(
        "學習 学习 [xue2 xi2] /to learn/to study/\n中文 中文 [Zhong1 wen2] /Chinese language/",
        source,
    )
    lesson = build_lesson(
        [
            Cue("cue-1", 0, 1000, "欢迎来到这里。"),
            Cue("cue-2", 1000, 3000, "今天学习中文。"),
            Cue("cue-3", 3000, 4500, "我们一起开始吧。"),
            Cue("cue-4", 4500, 6000, "每天学习一点。"),
        ],
        dictionary,
    )

    learning = next(word for word in lesson["vocabulary"] if word["word"] == "学习")
    assert learning["definitions"] == ["to learn", "to study"]
    assert learning["pinyin"] == "xué xí"
    assert learning["pinyin_numbered"] == "xue2 xi2"
    assert learning["occurrence_count"] == 2
    assert learning["occurrences"][0]["before_text"] == "欢迎来到这里。"
    assert learning["occurrences"][0]["cue_text"] == "今天学习中文。"
    assert learning["occurrences"][0]["after_text"] == "我们一起开始吧。"
    assert learning["occurrences"][1]["cue_text"] == "每天学习一点。"
    assert lesson["dictionary"]["loaded"] is True


def test_traditional_surface_maps_to_simplified_lexeme():
    dictionary = Cedict.from_text("學習 学习 [xue2 xi2] /to learn/")
    lesson = build_lesson([Cue("cue-1", 0, 1000, "我在學習。")], dictionary)
    learning = next(word for word in lesson["vocabulary"] if word["word"] == "学习")
    assert learning["traditional"] == "學習"
    assert learning["surface_forms"] == ["學習"]


def test_vietnamese_meanings_follow_english_reading_and_cue_translations_align():
    english = Cedict.from_text("行 行 [xing2] /to walk/\n行 行 [hang2] /row/")
    vietnamese = Cedict.from_text("行 行 [hang2] /hàng/\n行 行 [xing2] /đi; được/")
    lesson = build_lesson(
        [Cue("cue-1", 0, 1000, "行。"), Cue("cue-2", 1000, 2000, "好。")],
        english,
        vietnamese,
        [{"translation_vi": "Được."}, {"translation_vi": "Tốt."}],
        {"target_language": "vi", "available": True, "method": "machine-translation"},
    )
    word = next(item for item in lesson["vocabulary"] if item["word"] == "行")
    assert word["definitions_vi"] == ["đi; được"]
    assert [cue["translation_vi"] for cue in lesson["cues"]] == ["Được.", "Tốt."]
    assert lesson["translation"]["available"] is True


def test_saved_lesson_backfills_missing_vietnamese_meanings(tmp_path):
    english = Cedict.from_text("學習 学习 [xue2 xi2] /to learn/")
    vietnamese = Cedict.from_text("學習 学习 [xue2 xi2] /học/", tmp_path / "cvdict.u8")
    lesson = build_lesson([Cue("cue-1", 0, 1000, "学习")], english)
    assert lesson["vocabulary"][0]["definitions_vi"] == []
    del lesson["vocabulary"][0]["definitions_vi"]
    add_vietnamese_definitions(lesson, english, vietnamese)
    assert lesson["vocabulary"][0]["definitions_vi"] == ["học"]
    assert lesson["vietnamese_dictionary"]["loaded"] is True


def test_polyphonic_word_uses_sentence_reading_and_keeps_alternatives():
    english = Cedict.from_text(
        "更 更 [geng1] /to change/\n更 更 [geng4] /more/\n銀行 银行 [yin2 hang2] /bank/"
    )
    vietnamese = Cedict.from_text("更 更 [geng1] /thay đổi/\n更 更 [geng4] /càng; hơn/")
    lesson = build_lesson([Cue("cue-1", 0, 1000, "这样更容易。")], english, vietnamese)
    word = next(item for item in lesson["vocabulary"] if item["word"] == "更")
    assert word["pinyin"] == "gèng"
    assert word["definitions"] == ["more"]
    assert word["definitions_vi"] == ["càng; hơn"]
    assert word["occurrences"][0]["pinyin"] == "gèng"
    assert word["alternatives"][0]["pinyin"] == "gēng"
    assert word["alternatives"][0]["definitions_vi"] == ["thay đổi"]
    segment = next(seg for seg in lesson["cues"][0]["segments"] if seg["text"] == "更")
    assert segment["pinyin"] == "gèng"
