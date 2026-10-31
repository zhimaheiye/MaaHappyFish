"""Select checkout dependencies before importing Maa; releases stay isolated.

Keep the same Agent process so MFA retains ownership and cancellation control.
"""
from pathlib import Path
import os
import re
import sys


def configure_development_imports(agent_file):
    root = Path(agent_file).resolve().parent.parent
    config = root / ".venv/pyvenv.cfg"
    if not ((root / ".git").exists() and (root / "assets/interface.json").is_file() and config.is_file()):
        return None
    version = re.search(r"(?m)^version\s*=\s*(\d+)\.(\d+)", config.read_text(encoding="utf-8"))
    if version is None or tuple(map(int, version.groups())) != sys.version_info[:2]:
        raise RuntimeError("Development Python version differs from .venv; use tools/start-dev-client.cmd")
    relative = "Lib/site-packages" if os.name == "nt" else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    site = root / ".venv" / relative
    if not (site / "maa").is_dir():
        raise RuntimeError("Development MaaFramework is missing; install tools/requirements-dev.txt")
    path = str(site)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
    return site
