#!/usr/bin/env python3
"""
Pipeline 正则与资源加载 Smoke Preflight 校验工具
用于检测 assets/resource/pipeline/ 下所有节点的 expected 正则表达式合法性，
并执行底层 MaaFramework Resource bundle 加载自检。
"""
import glob
import json
import os
import re
import sys

def check_pipeline_regex():
    pipeline_files = glob.glob("assets/resource/pipeline/*.json")
    if not pipeline_files:
        print("[ERROR] No pipeline files found in assets/resource/pipeline/")
        return False

    errors = []
    regex_checked_count = 0

    for pf in pipeline_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"{pf}: JSON parse error -> {e}")
            continue

        for node_name, node in data.items():
            if not isinstance(node, dict):
                continue

            # Check expected in OCR nodes (and other recognition types)
            expected = node.get("expected")
            if expected is None:
                continue

            expected_list = expected if isinstance(expected, list) else [expected]
            for pat in expected_list:
                if not isinstance(pat, str):
                    continue
                regex_checked_count += 1
                try:
                    re.compile(pat)
                except re.error as e:
                    errors.append(
                        f"[{pf}] Node '{node_name}': invalid regex '{pat}' -> {e}"
                    )

    print(f"[Preflight] Checked {regex_checked_count} regex patterns across {len(pipeline_files)} pipeline files.")
    if errors:
        print(f"[FAIL] Found {len(errors)} regex/syntax errors:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("[PASS] All regex patterns compiled successfully in Python re.")

    # Second layer: MaaFramework Resource post_bundle smoke test
    try:
        import maa
        from maa.resource import Resource

        r = Resource()
        job = r.post_bundle("client_avalonia/resource")
        res = job.wait()
        if res.succeeded:
            print(f"[PASS] MaaFramework Resource.post_bundle succeeded! (Loaded {len(r.node_list)} nodes)")
            return True
        else:
            print("[FAIL] MaaFramework Resource.post_bundle reported failure!")
            return False
    except ImportError:
        print("[WARN] maa python package not installed, skipping C++ core smoke test.")
        return True
    except Exception as e:
        print(f"[FAIL] MaaFramework smoke test raised exception: {e}")
        return False


if __name__ == "__main__":
    success = check_pipeline_regex()
    sys.exit(0 if success else 1)
