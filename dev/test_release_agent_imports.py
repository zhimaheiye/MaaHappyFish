#!/usr/bin/env python3
"""
Preflight smoke test for release agent imports.
Validates that embedded / release environment has all required runtime packages
and that agent actions/recognitions can be loaded cleanly without error.
"""

import os
import sys

def main():
    print("=== [Smoke Test] Release Agent Imports Preflight ===")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.splitlines()[0]}")

    # 1. Core third-party dependencies check
    print("\n[Step 1] Checking core dependencies...")
    try:
        import maa
        print(f"  [PASS] maa: {getattr(maa, '__version__', 'ok')}")
    except Exception as e:
        print(f"  [FAIL] Failed to import maa: {e}")
        sys.exit(1)

    try:
        import numpy
        print(f"  [PASS] numpy: {numpy.__version__}")
    except Exception as e:
        print(f"  [FAIL] Failed to import numpy: {e}")
        sys.exit(1)

    try:
        import cv2
        print(f"  [PASS] cv2: {cv2.__version__}")
    except Exception as e:
        print(f"  [FAIL] Failed to import cv2: {e}")
        sys.exit(1)

    # 2. Agent local modules check
    print("\n[Step 2] Checking Agent modules...")
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-dir", default=None, help="Path to agent directory")
    args = parser.parse_args()

    if args.agent_dir:
        agent_dir = os.path.abspath(args.agent_dir)
    else:
        agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent"))
        if not os.path.isdir(agent_dir):
            agent_dir = os.path.abspath("agent")
    
    print(f"  Adding agent directory to sys.path: {agent_dir}")
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)

    try:
        import runtime_state
        print("  [PASS] runtime_state imported successfully")
        import param_utils
        print("  [PASS] param_utils imported successfully")
        import my_action
        print("  [PASS] my_action imported successfully")
        import my_reco
        print("  [PASS] my_reco imported successfully")
    except Exception as e:
        print(f"  [FAIL] Failed to import agent modules: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)

    print("\n=== [PASS] All release agent imports verified successfully! ===")
    sys.exit(0)

if __name__ == "__main__":
    main()
