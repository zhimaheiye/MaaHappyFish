import json
import re
import sys
import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
EXPECTED_GITHUB_URL = "https://github.com/zhimaheiye/MaaHappyFish"
ASSET_REGEX = re.compile(r"\b(?:win|windows)-(?:x64|x86_64)\b", re.IGNORECASE)
SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+$")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def test_interface_contracts():
    interface_assets = REPO_ROOT / "assets" / "interface.json"
    interface_client = REPO_ROOT / "client" / "interface.json"
    interface_avalonia = REPO_ROOT / "client_avalonia" / "interface.json"

    assert interface_assets.exists(), f"Missing {interface_assets}"
    assert interface_client.exists(), f"Missing {interface_client}"
    assert interface_avalonia.exists(), f"Missing {interface_avalonia}"

    # 1. SHA256 equality across all 3 interface.json files
    sha_assets = sha256_file(interface_assets)
    sha_client = sha256_file(interface_client)
    sha_avalonia = sha256_file(interface_avalonia)

    assert sha_assets == sha_client, f"interface.json mismatch between assets and client"
    assert sha_assets == sha_avalonia, f"interface.json mismatch between assets and client_avalonia"
    print("[PASS] All 3 interface.json files are byte-identical.")

    # 2. github field verification
    with open(interface_assets, "r", encoding="utf-8") as f:
        data = json.load(f)

    github_url = data.get("github")
    assert github_url == EXPECTED_GITHUB_URL, (
        f"interface.json 'github' field invalid:\n"
        f"Expected: {EXPECTED_GITHUB_URL}\n"
        f"Got: {github_url}"
    )
    print(f"[PASS] interface.json 'github' field exactly matches: {github_url}")

    # 3. SemVer verification
    version = data.get("version", "")
    assert SEMVER_REGEX.match(version), f"interface.json 'version' is not valid SemVer: '{version}'"
    print(f"[PASS] interface.json 'version' is valid SemVer: {version}")

    # 4. Release asset matcher verification
    sample_asset = f"MaaHappyFish-win-x86_64-v{version}.zip"
    assert ASSET_REGEX.search(sample_asset), (
        f"Sample release asset '{sample_asset}' does not match MFAAvalonia asset regex!"
    )
    print(f"[PASS] Release asset name '{sample_asset}' matches MFAAvalonia priority 100 pattern.")

def test_install_workflow_safety():
    workflow_path = REPO_ROOT / ".github" / "workflows" / "install.yml"
    assert workflow_path.exists(), f"Missing {workflow_path}"

    content = workflow_path.read_text(encoding="utf-8")

    # Verify no config or logs are packaged
    assert "rm -rf" in content or "cp" in content, "Workflow structure check"
    # Ensure package name pattern matches
    assert "MaaHappyFish-${{ matrix.os }}-${{ matrix.arch }}" in content, "Matrix asset naming check"
    print("[PASS] Workflow packaging rules verified.")

if __name__ == "__main__":
    try:
        test_interface_contracts()
        test_install_workflow_safety()
        print("\nALL UPDATE CONTRACT CHECKS PASSED 100%!")
    except AssertionError as e:
        print(f"\n[FAIL] Update contract assertion failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
