from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _resolve_cmd(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if sys.platform.startswith("win"):
        for candidate in (f"{name}.cmd", f"{name}.exe", f"{name}.bat"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    raise FileNotFoundError(
        f"Required command not found: {name}. Install Node.js to embed the Windows exe icon."
    )


def embed_exe_icon(
    exe_path: Path,
    icon_path: Path,
    repo_root: Path | None = None,
    product_name: str | None = None,
) -> None:
    """Rewrite the PE icon resource of a Windows exe so Explorer/shortcuts pick it up."""
    exe_path = Path(exe_path).resolve()
    icon_path = Path(icon_path).resolve()
    repo_root = (repo_root or Path(__file__).parent.parent).resolve()
    script_path = Path(__file__).with_name("set_exe_icon.mjs")

    if not exe_path.is_file():
        raise FileNotFoundError(f"EXE not found: {exe_path}")
    if not icon_path.is_file():
        raise FileNotFoundError(f"ICO not found: {icon_path}")
    if not script_path.is_file():
        raise FileNotFoundError(f"Icon embed script not found: {script_path}")

    npm = _resolve_cmd("npm")
    node = _resolve_cmd("node")
    patch_dir = Path(__file__).with_name(".icon-patch")
    patch_dir.mkdir(parents=True, exist_ok=True)

    print(f"Installing resedit (npm) to embed {icon_path.name} into {exe_path.name} ...")
    install = subprocess.run(
        [npm, "install", "--prefix", str(patch_dir), "--no-package-lock", "resedit"],
        cwd=repo_root,
        check=False,
    )
    if install.returncode != 0:
        raise RuntimeError(f"npm install resedit failed with exit {install.returncode}")

    env = os.environ.copy()
    env["RESEDIT_NODE_MODULES"] = str(patch_dir / "node_modules")
    cmd = [node, str(script_path), str(exe_path), str(icon_path)]
    if product_name:
        cmd.append(product_name)
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Failed to embed icon into {exe_path} (exit {completed.returncode})"
        )


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: python embed_exe_icon.py <exe> <ico> [product-name]", file=sys.stderr)
        sys.exit(1)
    embed_exe_icon(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        product_name=sys.argv[3] if len(sys.argv) == 4 else None,
    )
