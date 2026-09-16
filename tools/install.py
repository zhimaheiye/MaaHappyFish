from pathlib import Path

import shutil
import sys

try:
    import jsonc
except ModuleNotFoundError as e:
    raise ImportError(
        "Missing dependency 'json-with-comments' (imported as 'jsonc').\n"
        f"Install it with:\n  {sys.executable} -m pip install json-with-comments\n"
        "Or add it to your project's requirements."
    ) from e

from configure import configure_ocr_model
from embed_exe_icon import embed_exe_icon


working_dir = Path(__file__).parent.parent.resolve()
install_path = working_dir / Path("install")
version = len(sys.argv) > 1 and sys.argv[1] or "v0.0.1"

# the first parameter is self name
if sys.argv.__len__() < 4:
    print("Usage: python install.py <version> <os> <arch>")
    print("Example: python install.py v1.0.0 win x86_64")
    sys.exit(1)

os_name = sys.argv[2]
arch = sys.argv[3]


def get_dotnet_platform_tag():
    """自动检测当前平台并返回对应的dotnet平台标签"""
    if os_name == "win" and arch == "x86_64":
        platform_tag = "win-x64"
    elif os_name == "win" and arch == "aarch64":
        platform_tag = "win-arm64"
    elif os_name == "macos" and arch == "x86_64":
        platform_tag = "osx-x64"
    elif os_name == "macos" and arch == "aarch64":
        platform_tag = "osx-arm64"
    elif os_name == "linux" and arch == "x86_64":
        platform_tag = "linux-x64"
    elif os_name == "linux" and arch == "aarch64":
        platform_tag = "linux-arm64"
    else:
        print("Unsupported OS or architecture.")
        print("available parameters:")
        print("version: e.g., v1.0.0")
        print("os: [win, macos, linux, android]")
        print("arch: [aarch64, x86_64]")
        sys.exit(1)

    return platform_tag


def install_deps():
    if not (working_dir / "deps" / "bin").exists():
        print('Please download the MaaFramework to "deps" first.')
        print('请先下载 MaaFramework 到 "deps"。')
        sys.exit(1)

    if os_name == "android":
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
    else:
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path / "runtimes" / get_dotnet_platform_tag() / "native",
            ignore=shutil.ignore_patterns(
                "*MaaDbgControlUnit*",
                "*MaaThriftControlUnit*",
                "*MaaRpc*",
                "*MaaHttp*",
                "plugins",
                "*.node",
                "*MaaPiCli*",
            ),
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "libs" / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "bin" / "plugins",
            install_path / "plugins" / get_dotnet_platform_tag(),
            dirs_exist_ok=True,
        )



def install_resource():

    configure_ocr_model()

    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        working_dir / "assets" / "interface.json",
        install_path,
    )

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = jsonc.load(f)

    interface["version"] = version

    # Windows x64 is the supported release and carries its own Python runtime.
    if os_name == "win" and arch == "x86_64":
        interface["agent"]["child_exec"] = r"{PROJECT_DIR}/python/python.exe"

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)


def install_chores():
    shutil.copy2(
        working_dir / "README.md",
        install_path,
    )
    shutil.copy2(
        working_dir / "LICENSE",
        install_path,
    )
    shutil.copy2(
        working_dir / "THIRD_PARTY_NOTICES.md",
        install_path,
    )
    if os_name == "win":
        shutil.copy2(
            working_dir / "tools" / "collect_test_report.ps1",
            install_path,
        )
        shutil.copy2(
            working_dir / "tools" / "collect-test-report.cmd",
            install_path,
        )


def install_agent():
    shutil.copytree(
        working_dir / "agent",
        install_path / "agent",
        dirs_exist_ok=True,
    )


def install_icon():
    if os_name == "android":
        return

    source_icon = working_dir / "happyfish.ico"
    target_dir = install_path / "Assets"
    target_icon = target_dir / "logo.ico"

    if not source_icon.exists():
        raise FileNotFoundError(f"Project icon not found: {source_icon}")

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_icon, target_icon)

    # logo.ico only changes the running window/tray. Explorer and shortcuts
    # read the PE icon baked into the launcher exe, so rewrite that too.
    if os_name == "win":
        src_exe = install_path / "MFAAvalonia.exe"
        dst_exe = install_path / "MaaHappyFish.exe"
        if src_exe.exists():
            embed_exe_icon(
                src_exe,
                source_icon,
                working_dir,
                product_name="MaaHappyFish",
            )
            if dst_exe.exists() and dst_exe.resolve() != src_exe.resolve():
                dst_exe.unlink()
            src_exe.replace(dst_exe)
        elif dst_exe.exists():
            embed_exe_icon(
                dst_exe,
                source_icon,
                working_dir,
                product_name="MaaHappyFish",
            )
        else:
            print(f"Skip embedding exe icon: {src_exe} not found")
    else:
        src_bin = install_path / "MFAAvalonia"
        dst_bin = install_path / "MaaHappyFish"
        if src_bin.exists():
            if dst_bin.exists() and dst_bin.resolve() != src_bin.resolve():
                dst_bin.unlink()
            src_bin.replace(dst_bin)


def install_default_instance():
    """为新安装包写入默认任务列表预设；更新时 MFA 会保留用户现有 config。"""
    target = install_path / "config" / "instances" / "default.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(working_dir / "assets" / "default_instance.json", target)


if __name__ == "__main__":
    install_deps()
    install_resource()
    install_chores()
    install_agent()
    install_icon()
    install_default_instance()

    print(f"Install to {install_path} successfully.")
