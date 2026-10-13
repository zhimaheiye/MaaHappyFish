# -*- coding: utf-8 -*-
"""零点击实机：不可能命中的 OCR 超时 → TakeoverError → StopTask。

不点击，不消耗活动资源。设备串走环境变量或 mumu_dev，不写死端口。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

MAA_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT_RAW = os.environ.get("HAPPYFISH_AGENT_ROOT")
if not AGENT_ROOT_RAW:
    raise SystemExit("先设置 HAPPYFISH_AGENT_ROOT，指向本机 happyfishagent 仓库；此脚本仅供人工实机验收")
AGENT_ROOT = Path(AGENT_ROOT_RAW).resolve()
if not (AGENT_ROOT / "happyfish-activity-automation" / "scripts" / "recorder").is_dir():
    raise SystemExit("HAPPYFISH_AGENT_ROOT 缺少活动自动化脚本目录")
SCRIPTS = AGENT_ROOT / "happyfish-activity-automation" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(MAA_ROOT / "agent"))
sys.path.insert(0, str(MAA_ROOT))

import maa
import maa.agent.agent_server as agent_server_mod
from maa.library import Library


def _passthrough(name):
    def wrap(obj):
        return obj

    return wrap


# maa.agent 会把进程切到 AgentServer DLL，那个 DLL 不能创建 AdbController。
# 先挡住装饰器，导入 _capture_720p 后再切回 MaaFramework。
agent_server_mod.AgentServer.custom_action = _passthrough
agent_server_mod.AgentServer.custom_recognition = _passthrough

from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from activity_takeover import DumpActivityTakeover
from my_action import _capture_720p
from recorder.device import open_client
from recorder.flow_to_maa import compile_session


def _node_names(detail):
    names = []
    nodes = getattr(detail, "nodes", None) or []
    for node in nodes:
        name = getattr(node, "name", None)
        if name:
            names.append(name)
    return names


def main():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session = (
        AGENT_ROOT
        / "happyfish-activity-automation"
        / "activities"
        / "v1-takeover-smoke"
        / "sessions"
        / stamp
    )
    session.mkdir(parents=True)
    (session / "screenshots").mkdir()
    (session / "diffs").mkdir()
    (session / "takeover").mkdir()
    trace_lines = [{"n": index, "marker": "head" if index < 2 else "tail"} for index in range(12)]
    (session / "trace.jsonl").write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in trace_lines) + "\n",
        encoding="utf-8",
    )
    flow = {
        "exploration_task": "v1-takeover-smoke",
        "session_id": stamp,
        "states": [
            {
                "state": "S0001",
                "name": None,
                "status": "maa_ready",
                "recognition": {
                    "type": "OCR",
                    "expected": "__MHF_V1_IMPOSSIBLE_TEST_TOKEN__",
                    "expected_mode": "literal",
                    "recommended_roi": [0, 0, 1280, 720],
                },
                "action": {"type": "DoNothing"},
                "result_candidates": [],
                "timing": {"recognition_timeout_ms": 2500},
                "safety": {"level": "readonly", "reason": "只识别一个不可能出现的字符串"},
            }
        ],
    }
    (session / "flow.json").write_text(json.dumps(flow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pipeline_path = compile_session(session)
    pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
    runnable = {key: value for key, value in pipeline.items() if not key.startswith("$")}
    for node in runnable.values():
        if node.get("action") == "Click":
            raise SystemExit("测试 Pipeline 含 Click，拒绝实机运行")
    # 直接进入识别节点。放在 StartRouter.next 里时，识别失败只算父节点的
    # next 未命中，不会触发该状态自己的 on_error。
    entry = "Activity_v1_takeover_smoke_S0001"

    client = open_client()
    print("device", client.serial, client.source, flush=True)
    Library.open(Path(maa.__file__).parent / "bin", agent_server=False)
    Toolkit.init_option(str(MAA_ROOT))
    controller = AdbController(client.adb_path, client.serial)
    controller.set_screenshot_target_short_side(720)
    connected = controller.post_connection().wait()
    if not connected.succeeded:
        raise SystemExit("adb 控制器连接失败")

    resource = Resource()
    model = resource.post_ocr_model(MAA_ROOT / "assets" / "resource" / "model" / "ocr").wait()
    if not model.succeeded:
        raise SystemExit("OCR 模型加载失败")
    action = DumpActivityTakeover()
    action.capture = _capture_720p
    if not resource.register_custom_action("DumpActivityTakeover", action):
        raise SystemExit("注册 DumpActivityTakeover 失败")

    tasker = Tasker()
    if not tasker.bind(resource, controller):
        raise SystemExit("Tasker 绑定失败")
    job = tasker.post_task(entry, runnable).wait()
    detail = job.get()
    names = _node_names(detail)
    print("task_succeeded", job.succeeded, "nodes", names, flush=True)

    packages = sorted((session / "takeover").iterdir())
    packages = [item for item in packages if item.is_dir() and (item / "meta.json").is_file()]
    if not packages:
        raise SystemExit("没有生成 takeover package")
    latest = packages[-1]
    meta = json.loads((latest / "meta.json").read_text(encoding="utf-8"))
    image = Image.open(latest / "current.png")
    tail = [
        json.loads(line)
        for line in (latest / "trace_tail.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print("package", latest, flush=True)
    print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)
    problems = []
    if meta.get("source_state") != "S0001":
        problems.append("source_state=%s" % meta.get("source_state"))
    if meta.get("reason") != "recognition_failed":
        problems.append("reason=%s" % meta.get("reason"))
    if not str(meta.get("pipeline_node") or "").endswith("__TakeoverError"):
        problems.append("pipeline_node=%s" % meta.get("pipeline_node"))
    if meta.get("expected") != "__MHF_V1_IMPOSSIBLE_TEST_TOKEN__":
        problems.append("expected=%s" % meta.get("expected"))
    if image.size != (1280, 720):
        problems.append("screenshot=%s" % (image.size,))
    if [item["n"] for item in tail] != list(range(2, 12)):
        problems.append("trace_tail=%s" % tail)
    if meta.get("trace_status") != "ok":
        problems.append("trace_status")
    if names:
        if not any(name.endswith("__TakeoverError") for name in names):
            problems.append("task detail 没有 TakeoverError: %s" % names)
        if not names[-1].endswith("__Stop"):
            problems.append("最后节点不是 StopTask: %s" % names)
        # 识别失败的业务节点不会进入成功节点列表。Stop 之后不能再出现它。
        if any(name.endswith("_S0001") for name in names):
            problems.append("失败节点仍被当成成功节点执行: %s" % names)
    if problems:
        raise SystemExit("实机验收失败: " + "; ".join(problems))
    print("LIVE_OK", latest, flush=True)


if __name__ == "__main__":
    main()
