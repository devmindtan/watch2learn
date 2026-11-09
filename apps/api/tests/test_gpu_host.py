import asyncio

import httpx
from watch2learn import gpu_host, remote_speech, tts
from watch2learn.app import app

ON = {
    "reachable": True,
    "installed": {"ollama": True, "speech": True},
    "running": {"ollama": False, "speech": False},
    "busy": [],
}


def host(monkeypatch, state):
    monkeypatch.setenv("WATCH2LEARN_GPU", "on")
    monkeypatch.setenv("WATCH2LEARN_GPU_HOST", "desktop-kndgm60")
    gpu = gpu_host.GpuHost()
    monkeypatch.setattr(gpu, "remote_state", lambda name: state)
    return gpu


def test_gpu_is_used_when_on_and_falls_back_with_a_reason(monkeypatch):
    assert host(monkeypatch, ON).pick("speech") == ("gpu", "máy GPU đang bật")
    off = {"reachable": False, "reason": "không kết nối được desktop-kndgm60"}
    assert host(monkeypatch, off).pick("speech") == ("local", off["reason"])
    missing = ON | {"installed": {"ollama": True, "speech": False}}
    assert host(monkeypatch, missing).pick("speech")[0] == "local"
    busy = ON | {"busy": ["VoiceStudio"]}
    assert "VoiceStudio" in host(monkeypatch, busy).pick("ollama")[1]
    monkeypatch.setenv("WATCH2LEARN_GPU", "off")
    assert gpu_host.GpuHost().pick("ollama")[0] == "local"


def test_endpoint_opens_a_tunnel_only_when_the_gpu_is_picked(monkeypatch):
    gpu = host(monkeypatch, ON)
    opened = []
    monkeypatch.setattr(gpu_host, "healthy", lambda service, timeout=1.5: False)
    monkeypatch.setattr(gpu, "open_tunnel", lambda service: opened.append(service.id) or True)
    assert gpu.endpoint("speech") == "http://127.0.0.1:8912"
    assert opened == ["speech"]
    assert gpu.endpoint("ollama", start=False) is None  # health checks never start tunnels

    off = host(monkeypatch, {"reachable": False, "reason": "tắt"})
    assert off.endpoint("speech") is None
    assert off.status()["services"]["speech"]["reason"] == "tắt"


def test_tts_uses_the_gpu_worker_and_falls_back_to_the_laptop(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "available_voices", lambda: {"vi": [], "zh": []})
    monkeypatch.setattr(remote_speech, "synthesize", lambda parts, voices: b"gpu-audio")

    async def speak():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/tts", json={"parts": [{"text": "你好", "lang": "zh"}]})

    assert asyncio.run(speak()).content == b"gpu-audio"
    monkeypatch.setattr(remote_speech, "synthesize", lambda parts, voices: None)
    monkeypatch.setattr(tts, "voices_ready", lambda: True)
    local = tmp_path / "local.m4a"
    local.write_bytes(b"laptop-audio")
    monkeypatch.setattr(tts, "synthesize", lambda parts, voices: local)
    assert asyncio.run(speak()).content == b"laptop-audio"
