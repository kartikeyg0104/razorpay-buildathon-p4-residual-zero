"""stdio MCP entry: python -m residual_zero.mcp"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    cand = here.parents[3]
    if cand.joinpath("fixtures").joinpath("recon").is_dir():
        return cand
    return Path.cwd()


def main() -> None:
    root = repo_root()
    os.chdir(root)
    from residual_zero.runtime.envfile import load_env_file

    load_env_file()
    from residual_zero.mcp.protocol import serve

    serve()


if __name__ == "__main__":
    main()
