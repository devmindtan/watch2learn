from types import SimpleNamespace

from watch2learn import asr


def test_transcription_preserves_timing_and_provenance(monkeypatch):
    class FakeModel:
        def transcribe(self, path, **options):
            assert path.endswith("speech.wav")
            assert options["language"] == "zh"
            segments = [SimpleNamespace(start=1.2, end=3.4, text=" 你好，欢迎学习中文。 ")]
            info = SimpleNamespace(language="zh", language_probability=0.98765)
            return iter(segments), info

    monkeypatch.setattr(asr, "load_model", lambda: FakeModel())
    cues, provenance = asr.transcribe_mandarin("speech.wav")

    assert cues[0].start_ms == 1200
    assert cues[0].end_ms == 3400
    assert cues[0].text == "你好，欢迎学习中文。"
    assert provenance["method"] == "faster-whisper"
    assert provenance["language_probability"] == 0.9877
