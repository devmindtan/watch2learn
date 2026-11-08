import pytest
from watch2learn.subtitles import parse_subtitles, timestamp_ms


def test_parses_srt_and_strips_markup():
    cues = parse_subtitles(
        """1
00:00:01,250 --> 00:00:03,000
<i>今天</i>我们学习中文。

2
00:00:03,100 --> 00:00:05,000
这个方法很有意思。
"""
    )
    assert [(cue.start_ms, cue.end_ms, cue.text) for cue in cues] == [
        (1250, 3000, "今天我们学习中文。"),
        (3100, 5000, "这个方法很有意思。"),
    ]


def test_parses_webvtt_timestamps_and_rejects_empty_input():
    cues = parse_subtitles("WEBVTT\n\n00:01.000 --> 00:02.500 align:start\n你好！\n")
    assert cues[0].text == "你好！"
    assert timestamp_ms("01:02:03.004") == 3_723_004
    with pytest.raises(ValueError, match="empty"):
        parse_subtitles("  ")
