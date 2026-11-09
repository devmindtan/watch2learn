"""Optional GPU machine reached over Tailscale + SSH (docs/gpu-host.md).

The user's rule: use the GPU machine when it is on; fall back to this laptop when it
is off, the service is not installed there, or the card is busy with another
project's heavy model. Each service stays bound to 127.0.0.1 on the GPU machine;
one SSH process runs it in the foreground and forwards it to a loopback port here,
so nothing is exposed to the tailnet. Tunnels close after a period without use so
the 6 GB card is freed for other work.
"""

import atexit
import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = PROJECT_ROOT / ".gpu" / "host.json"
LOG_DIR = PROJECT_ROOT / ".gpu"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
STATE_SECONDS = 60
IDLE_SECONDS = int(os.environ.get("WATCH2LEARN_GPU_IDLE_SECONDS", "600"))
START_SECONDS = 90
HOST_RE = re.compile(r"^[A-Za-z0-9._@-]+$")
# Other projects' heavy services on the same card: while one runs, ours wait locally.
OTHER_HEAVY_PORTS = {3900: "VoiceStudio", 8188: "ComfyUI"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Service:
    id: str
    label: str
    dir: str
    remote_port: int
    local_port: int
    health: str

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"


SERVICES = {
    "ollama": Service("ollama", "Ollama", "~/ollama-gpu", 11434, 11435, "/api/version"),
    "speech": Service(
        "speech", "Watch2Learn speech (TTS + ASR)", "~/watch2learn-gpu", 8911, 8912, "/health"
    ),
}


def configured_host() -> str | None:
    if os.environ.get("WATCH2LEARN_GPU", "").lower() in {"0", "off", "false", "local"}:
        return None
    host = os.environ.get("WATCH2LEARN_GPU_HOST", "").strip()
    if not host:
        try:
            host = str(json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("host", ""))
        except (OSError, ValueError):
            return None
    return host if HOST_RE.fullmatch(host) else None


def remote_bash(host: str, command: str) -> list[str]:
    # The GPU machine is Windows + WSL: run the command in the WSL Ubuntu shell.
    return [host, "wsl", "-e", "bash", "-lc", f'"{command}"']


def healthy(service: Service, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(service.url + service.health, timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


class GpuHost:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict | None = None
        self.state_time = 0.0
        self.tunnels: dict[str, subprocess.Popen] = {}
        self.started_remote: set[str] = set()
        self.last_used: dict[str, float] = {}
        self.reasons: dict[str, str] = {}
        self.reaper: threading.Thread | None = None

    # One SSH round trip: is the machine on, what is installed, which ports listen.
    def remote_state(self, host: str) -> dict:
        checks = [f"test -x {s.dir}/run.sh && echo INSTALLED:{s.id}" for s in SERVICES.values()]
        command = "; ".join(["ss -ltnH", *checks, "true"])
        try:
            result = subprocess.run(
                SSH + remote_bash(host, command), capture_output=True, text=True, timeout=20
            )
        except (OSError, subprocess.SubprocessError):
            return {"reachable": False, "reason": f"không kết nối được {host}"}
        if result.returncode != 0:
            return {"reachable": False, "reason": f"không kết nối được {host}"}
        lines = result.stdout.splitlines()

        def listening(port: int) -> bool:
            return any(re.search(rf"127\.0\.0\.1:{port}\s", line) for line in lines)

        return {
            "reachable": True,
            "installed": {s.id: f"INSTALLED:{s.id}" in lines for s in SERVICES.values()},
            "running": {s.id: listening(s.remote_port) for s in SERVICES.values()},
            "busy": [label for port, label in OTHER_HEAVY_PORTS.items() if listening(port)],
        }

    def cached_state(self, host: str) -> dict:
        if self.state is None or time.monotonic() - self.state_time > STATE_SECONDS:
            self.state = self.remote_state(host)
            self.state_time = time.monotonic()
        return self.state

    def pick(self, service_id: str) -> tuple[str, str]:
        """("gpu" | "local", reason) for a job that needs `service_id`."""
        host = configured_host()
        if not host:
            return "local", "chưa cấu hình máy GPU (.gpu/host.json)"
        state = self.cached_state(host)
        if not state["reachable"]:
            return "local", state.get("reason", "máy GPU không bật")
        if not state["installed"].get(service_id):
            return "local", f"máy GPU chưa cài {SERVICES[service_id].label}"
        if state["busy"]:
            return "local", f"card GPU đang bận với {', '.join(state['busy'])}"
        return "gpu", "máy GPU đang bật"

    def endpoint(self, service_id: str, start: bool = True) -> str | None:
        """Base URL of the GPU service on a local port, or None to use the laptop."""
        service = SERVICES[service_id]
        if not start:  # health checks: never wait behind a tunnel being opened
            tunnel = self.tunnels.get(service_id)
            alive = tunnel and tunnel.poll() is None and healthy(service)
            return service.url if alive else None
        with self.lock:
            tunnel = self.tunnels.get(service_id)
            if tunnel and tunnel.poll() is None and healthy(service):
                self.last_used[service_id] = time.monotonic()
                return service.url
            if not start:
                return None
            machine, reason = self.pick(service_id)
            self.reasons[service_id] = reason
            if machine != "gpu":
                return None
            if healthy(service):  # a tunnel opened by another process/project already
                self.last_used[service_id] = time.monotonic()
                return service.url
            if self.open_tunnel(service):
                return service.url
            self.reasons[service_id] = f"không bật được {service.label} trên máy GPU"
            self.state = None
            return None

    def open_tunnel(self, service: Service) -> bool:
        host = configured_host()
        was_running = bool(self.state and self.state["running"].get(service.id))
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = (LOG_DIR / f"{service.id}.log").open("ab")
        forward = f"127.0.0.1:{service.local_port}:127.0.0.1:{service.remote_port}"
        command = SSH + [
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-L",
            forward,
            *remote_bash(host, f"{service.dir}/run.sh"),
        ]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        deadline = time.monotonic() + START_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            if healthy(service):
                self.tunnels[service.id] = process
                if not was_running:
                    self.started_remote.add(service.id)
                self.last_used[service.id] = time.monotonic()
                self.ensure_reaper()
                logger.info("%s is running on the GPU machine", service.label)
                return True
            time.sleep(0.5)
        process.terminate()
        return False

    def close(self, service_id: str) -> None:
        tunnel = self.tunnels.pop(service_id, None)
        if service_id in self.started_remote and (host := configured_host()):
            self.started_remote.discard(service_id)
            stop = (
                f"test -x {SERVICES[service_id].dir}/stop.sh && {SERVICES[service_id].dir}/stop.sh"
            )
            subprocess.run(SSH + remote_bash(host, stop), capture_output=True, timeout=60)
        if tunnel and tunnel.poll() is None:
            tunnel.terminate()
        self.state = None

    def ensure_reaper(self) -> None:
        if self.reaper and self.reaper.is_alive():
            return

        def reap() -> None:
            while self.tunnels:
                time.sleep(30)
                with self.lock:
                    for service_id in list(self.tunnels):
                        idle = time.monotonic() - self.last_used.get(service_id, 0)
                        if idle > IDLE_SECONDS:
                            logger.info("Closing idle GPU service %s", service_id)
                            self.close(service_id)

        self.reaper = threading.Thread(target=reap, name="gpu-reaper", daemon=True)
        self.reaper.start()

    def shutdown(self) -> None:
        with self.lock:
            for service_id in list(self.tunnels):
                self.close(service_id)

    def status(self) -> dict:
        host = configured_host()
        return {
            "configured": bool(host),
            "host": host,
            "services": {
                service_id: {
                    "active": bool(
                        (tunnel := self.tunnels.get(service_id)) and tunnel.poll() is None
                    ),
                    "reason": self.reasons.get(service_id),
                }
                for service_id in SERVICES
            },
        }


GPU = GpuHost()
# Close tunnels (and stop services we started) even when the process exits on an error,
# so the GPU machine's VRAM is never left held by an orphaned worker.
atexit.register(GPU.shutdown)
