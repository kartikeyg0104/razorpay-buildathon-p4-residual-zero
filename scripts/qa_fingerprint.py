"""Environment fingerprint for a QA run. Never prints secrets."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def main() -> dict:
    commit = ""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        commit = ""
    files = [
        Path("data/dev/rendered/bank.csv"),
        Path("data/dev/rendered/ledger.csv"),
        Path("data/dev/rendered/settlement.csv"),
        Path("config/solver.yaml"),
        Path("config/tax_rates.yaml"),
        Path("config/fees.yaml"),
        Path("config/features.yaml"),
        Path("config/llm.yaml"),
    ]
    hashed = {str(p): _sha(p) for p in files}
    payload = {
        "git_commit": commit,
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "hashes": hashed,
        "NVIDIA_API_KEY": "present" if (os.environ.get("NVIDIA_API_KEY") or "").strip() else "missing",
        "AI_API_KEY": "present" if (os.environ.get("AI_API_KEY") or "").strip() else "missing",
        "AI_PROVIDER": os.environ.get("AI_PROVIDER") or "unset",
        "AI_MODEL": os.environ.get("AI_MODEL") or "unset",
        "writes_cleared": False,
        "note": "Fingerprint only. LIVE_PROVIDER is not YES unless provider_live.json says so.",
    }
    out = Path("artifacts").joinpath("qa", "fingerprint.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("git_commit", "python", "os", "NVIDIA_API_KEY", "AI_MODEL")}, indent=2))
    return payload


if __name__ == "__main__":
    from residual_zero.runtime.envfile import load_env_file

    load_env_file()
    main()
