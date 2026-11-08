import wave

from faster_whisper.audio import decode_audio


def test_installed_asr_stack_decodes_real_wave_file(tmp_path):
    source = tmp_path / "speech.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * 16_000)

    audio = decode_audio(source)

    assert audio.shape == (16_000,)
