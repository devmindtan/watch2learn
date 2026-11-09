"""Print which machine each heavy service would use right now (one SSH round trip)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from watch2learn.gpu_host import GPU, SERVICES  # noqa: E402

for service_id, service in SERVICES.items():
    machine, reason = GPU.pick(service_id)
    print(f"{service.label:32} → {'máy GPU' if machine == 'gpu' else 'laptop'} ({reason})")
