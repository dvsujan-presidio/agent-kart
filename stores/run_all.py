"""Run all four mock stores locally: python -m stores.run_all"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"


def main() -> None:
    procs = []
    for f in sorted(DATA.glob("*.json")):
        cfg = json.loads(f.read_text())
        env = {**os.environ, "STORE_ID": cfg["id"], "PUBLIC_URL": f"http://localhost:{cfg['port']}"}
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "stores.server:app_from_env",
                    "--factory",
                    "--port",
                    str(cfg["port"]),
                    "--log-level",
                    "warning",
                ],
                env=env,
            )
        )
        print(f"{cfg['name']:24s} http://localhost:{cfg['port']}")
    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        for pr in procs:
            pr.terminate()


if __name__ == "__main__":
    main()
