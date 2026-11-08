from watch2learn.dictionary import Cedict
from watch2learn.lesson import build_lesson
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
