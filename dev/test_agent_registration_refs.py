"""
Pipeline -> Agent 寮曠敤瀹屾暣鎬ч潤鎬佹鏌?(Preflight Hard Gate)
纭繚 assets/resource/pipeline/*.json 涓紩鐢ㄧ殑鎵€鏈?custom_action 鍜?custom_recognition
鍧囧凡鍦?agent/*.py 涓敞鍐屽疄鐜般€?"""
import os
import sys
import glob
import json
import ast

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pipeline_dir = os.path.join(root_dir, "assets", "resource", "pipeline")
    agent_dir = os.path.join(root_dir, "agent")

    # 1. Collect pipeline references
    pipeline_actions = {}
    pipeline_recos = {}

    pipeline_files = glob.glob(os.path.join(pipeline_dir, "*.json"))
    for pfile in pipeline_files:
        rel_pfile = os.path.relpath(pfile, root_dir)
        try:
            with open(pfile, "r", encoding="utf-8-sig") as f:
                pdata = json.load(f)
        except Exception as e:
            print(f"[FAIL] 鏃犳硶瑙ｆ瀽 Pipeline JSON: {rel_pfile} ({e})")
            return 1

        for node_name, node_def in pdata.items():
            if isinstance(node_def, dict):
                ca = node_def.get("custom_action")
                if ca:
                    pipeline_actions.setdefault(ca, []).append((rel_pfile, node_name))
                cr = node_def.get("custom_recognition")
                if cr:
                    pipeline_recos.setdefault(cr, []).append((rel_pfile, node_name))

    # 2. 鏀堕泦 Agent 婧愮爜涓殑娉ㄥ唽瀹炵幇 (閫氳繃 Python AST 瑙ｆ瀽锛岀‘淇濅弗璋?
    registered_actions = set()
    registered_recos = set()

    agent_files = glob.glob(os.path.join(agent_dir, "*.py"))
    for afile in agent_files:
        with open(afile, "r", encoding="utf-8-sig") as f:
            tree = ast.parse(f.read(), filename=afile)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        attr = dec.func.attr
                        if attr in ("custom_action", "custom_recognition") and dec.args:
                            arg0 = dec.args[0]
                            if isinstance(arg0, ast.Constant):
                                if attr == "custom_action":
                                    registered_actions.add(arg0.value)
                                else:
                                    registered_recos.add(arg0.value)

    print(f"[Check] Pipeline references: CustomAction={len(pipeline_actions)}, CustomRecognition={len(pipeline_recos)}")
    print(f"[Check] Agent registered: CustomAction={len(registered_actions)}, CustomRecognition={len(registered_recos)}")

    # 3. 校验子集关系 (Pipeline 引用必须是 Agent 注册实现的子集)
    errors = []

    for ca, refs in pipeline_actions.items():
        if ca not in registered_actions:
            ref_str = ", ".join([f"{f}:{n}" for f, n in refs])
            errors.append(f"Missing CustomAction registration: '{ca}' referenced by: {ref_str}")

    for cr, refs in pipeline_recos.items():
        if cr not in registered_recos:
            ref_str = ", ".join([f"{f}:{n}" for f, n in refs])
            errors.append(f"Missing CustomRecognition registration: '{cr}' referenced by: {ref_str}")

    if errors:
        print("\n[FAIL] Pipeline references unregistered CustomAction / CustomRecognition:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\n[PASS] All Pipeline CustomAction and CustomRecognition references are registered in Agent!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
