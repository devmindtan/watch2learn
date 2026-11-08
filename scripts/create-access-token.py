"""Create (or show) the access token required when the backend is exposed remotely."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from watch2learn import security  # noqa: E402


def main() -> None:
    existing = security.access_token()
    if existing and "--rotate" not in sys.argv:
        print(f"Access token already exists ({security.TOKEN_FILE}):\n{existing}")
        return
    token = security.create_token_file()
    print(f"New access token written to {security.TOKEN_FILE} (keep it secret):\n{token}")


if __name__ == "__main__":
    main()
