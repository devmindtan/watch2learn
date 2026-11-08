import wave
from pathlib import Path

import pytest
from watch2learn.media import extract_asr_audio, probe_media


def write_silent_wave(path: Path, channels: int = 2, rate: int = 48_000):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\0\0" * channels * rate)


def test_probe_and_extract_audio_for_asr(tmp_path):
    source = tmp_path / "source.wav"
    output = tmp_path / "derived" / "speech.wav"
    write_silent_wave(source)

    probe = probe_media(source)
    assert probe["streams"][0]["sample_rate"] == "48000"
    extract_asr_audio(source, output)
    derived = probe_media(output)
    assert derived["streams"][0]["sample_rate"] == "16000"
    assert derived["streams"][0]["channels"] == 1
    with pytest.raises(FileExistsError):
        extract_asr_audio(source, output)
