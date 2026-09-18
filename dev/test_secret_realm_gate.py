# -*- coding: utf-8 -*-
"""秘境之门（SecretRealmGateTask）专项测试。

业务契约：
- 两态启动恢复（秘境之门主页 > 主鱼缸入口）；
- 送出列大 ROI OCR「送出」点击文字本身，循环直到无送出；
- 分支一：选择送出鱼弹窗（分词兼容）→ 确定送出条件模板 → 弹窗送出 → 领取 → 等 5 秒 → 确定；
- 分支二：「您没有这种鱼」（分词兼容）→ 按相对偏移 (+241,-117) 定位垃圾桶（模板确认，拒绝盲点）→ 确认删除对号；
- 分支结束统一回到 SendRouter 继续识别下一个送出；
- 无送出后 OCR 返回退出 + 主鱼缸确认 + 日常双出口；
- 日常收尾：SECRET_REALM_GATE 步骤接入调度（队列顺序在绿野之后）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "assets/resource/pipeline/features/secret_realm_gate.json"
ROUTINE_PATH = ROOT / "assets/resource/pipeline/routine/daily_routine.json"
INTERFACE_PATH = ROOT / "assets/interface.json"

GLOBAL_HANDLERS = [
    "[JumpBack]GlobalActivityPagePopup",
    "[JumpBack]GlobalDailySignPopup",
    "[JumpBack]GlobalSpecialOfferPopup",
    "[JumpBack]GlobalNewsPopup",
    "[JumpBack]GlobalLevelUpPopup",
]

MAIN_TANK = "main"
GATE_PAGE = "gate"           # 秘境之门主页（图二）
SEND_POPUP = "send_popup"    # 分支一弹窗（图一）
RESULT_POPUP = "result"      # 送出成功后的领取/确定结算页
NO_FISH_PAGE = "no_fish"     # 分支二提示页


def business_next(node):
    return [name for name in node.get("next", []) if name not in GLOBAL_HANDLERS]


class MockArg:
    def __init__(self, param=None):
        self.custom_action_param = json.dumps(param or {})
        self.custom_recognition_param = self.custom_action_param
        self.box = None


class MockRunArg(MockArg):
    def __init__(self, box=None, param=None):
        super().__init__(param)
        self.box = box


class MockCtrl:
    def __init__(self):
        self.clicks = []

    def post_click(self, x, y):
        self.clicks.append((x, y))

        class _Job:
            def wait(self):
                pass

        return _Job()


class MockRecoResult:
    def __init__(self, hit, box=None):
        self.hit = hit
        self.box = box


class MockTasker:
    def __init__(self, ctrl):
        self.controller = ctrl


class MockContext:
    def __init__(self, delete_hit_box=None):
        self.ctrl = MockCtrl()
        self.delete_hit_box = delete_hit_box

    @property
    def tasker(self):
        return MockTasker(self.ctrl)

    def run_recognition(self, name, image=None, pipeline_override=None):
        if self.delete_hit_box is not None:
            return MockRecoResult(True, self.delete_hit_box)
        return MockRecoResult(False)


class SecretRealmGateSimulator:
    """按 Maa next 列表语义驱动真实 secret_realm_gate.json。

    page 字段：
      send_visible: 主页任务列表是否还有「送出」
      branch: 点击送出后进入的分支 "send" | "no_fish"
      send_condition: 分支一中确定送出条件是否成立
    """

    def __init__(self, pipeline, page):
        self.pipeline = pipeline
        self.page = page
        self.visited = []
        self.clicks = []
        self.outcome = None

    def reco_hit(self, name):
        p = self.page
        if name in ("SecretRealmGateTask", "SecretRealmGateStartRouter",
                    "SecretRealmGateSendRouter", "SecretRealmGateNoMoreSend",
                    "SecretRealmGateClickDelete"):
            return True  # DirectHit 型节点
        if name == "SecretRealmGateOpenTreasure":
            return p["stage"] == "main_tank"  # 右下角宝箱只在主鱼缸
        if name == "SecretRealmGateMainTankEntry":
            return p["stage"] == "main_tank"  # 入口模板在宝箱菜单弹出后可见
        if name in ("SecretRealmGateMainPage",):
            return p["stage"] == "gate"  # 秘境之门_识别
        if name == "SecretRealmGateClickSend":
            return p["stage"] == "gate" and p["send_visible"]  # OCR 送出
        if name == "SecretRealmGateSendPopup":
            return p["stage"] == "send_popup"  # 分支一标题 OCR
        if name == "SecretRealmGateCheckSendCondition":
            return p.get("send_condition", False)  # 确定送出条件模板
        if name in ("SecretRealmGateClickPopupSend", "SecretRealmGateClickClaim",
                    "SecretRealmGateClickConfirm"):
            return p["stage"] in ("send_popup", "result")  # 弹窗内 OCR 按钮
        if name == "SecretRealmGateNoFishCheck":
            return p.get("branch") == "no_fish" and p["stage"] == "no_fish"  # 分支二 OCR
        if name == "SecretRealmGateClickConfirmDelete":
            return p.get("branch") == "no_fish" and p["stage"] == "no_fish"  # 删除确认对号
        if name == "SecretRealmGateExitGate":
            return p["stage"] == "gate" and not p["send_visible"]  # OCR 返回
        if name == "SecretRealmGateVerifyTank":
            return p["stage"] == "main_tank"  # 主界面特征
        if name in ("DailyRoutineReturnIfActive", "DailyRoutineStandaloneDone"):
            return True  # 双出口（语义层面恒可达其一）
        if name == "SecretRealmGateAbort":
            return True
        raise AssertionError(f"意外到达节点: {name}")

    def _follow(self, name):
        self.visited.append(name)
        if name in ("DailyRoutineReturnIfActive", "DailyRoutineStandaloneDone"):
            # 双出口定义在 daily_routine.json（Custom reco 分流），到达即视为出口终点
            self.outcome = "daily_exit"
            return
        node = self.pipeline[name]
        if node.get("action") == "StopTask":
            self.outcome = "stop_task"
            return
        if node.get("action") == "Click" or name == "SecretRealmGateClickSend":
            self.clicks.append(name)
        # 页面转移（模拟真实点击后的页面变化）
        if name == "SecretRealmGateOpenTreasure":
            self.page = {"stage": "main_tank", "send_visible": self.page["send_visible"]}
        if name == "SecretRealmGateMainTankEntry":
            self.page = {"stage": "gate", "send_visible": self.page["send_visible"]}
        elif name == "SecretRealmGateClickSend":
            if self.page.get("branch") == "no_fish":
                self.page = {"stage": "no_fish", "branch": "no_fish"}
            else:
                self.page = {"stage": "send_popup", "send_condition": self.page.get("send_condition", True)}
        elif name == "SecretRealmGateClickPopupSend":
            self.page = {"stage": "result"}
        elif name == "SecretRealmGateClickClaim":
            self.page = {"stage": "result"}  # 等 5 秒后同位置出现确定
        elif name == "SecretRealmGateClickConfirm":
            self.page = {"stage": "gate", "send_visible": False}  # 最后一单送完
        elif name == "SecretRealmGateClickConfirmDelete":
            self.page = {"stage": "gate", "send_visible": False}  # 卡片已删
        elif name == "SecretRealmGateExitGate":
            self.page = {"stage": "main_tank"}
        for cand in business_next(node):
            if self.reco_hit(cand):
                self._follow(cand)
                return
        self.outcome = "chain_end"

    def run(self, page):
        self.page = page
        self._follow("SecretRealmGateTask")
        return self


def run_tests():
    pipeline = json.loads(GATE_PATH.read_text(encoding="utf-8"))
    routine = json.loads(ROUTINE_PATH.read_text(encoding="utf-8"))
    interface = json.loads(INTERFACE_PATH.read_text(encoding="utf-8"))

    # ---- 模板与 ROI 契约 ----
    tpl_specs = {
        "SecretRealmGateOpenTreasure": ("右下角_宝箱.png", [1120, 562, 141, 141], "Click"),
        "SecretRealmGateMainTankEntry": ("秘境之门_入口.png", [573, 621, 58, 40], "Click"),
        "SecretRealmGateMainPage": ("秘境之门_识别.png", [464, 0, 354, 127], "DoNothing"),
        "SecretRealmGateCheckSendCondition": ("秘境之门_确定送出条件.png", [179, 229, 107, 37], "DoNothing"),
        "SecretRealmGateClickConfirmDelete": ("秘境之门_确认删除.png", [804, 462, 44, 44], "Click"),
    }
    for node_name, (tpl, roi, action) in tpl_specs.items():
        node = pipeline[node_name]
        assert node["recognition"] == "TemplateMatch"
        assert node["template"] == tpl, node_name
        assert node["roi"] == roi, node_name
        assert node["threshold"] == 0.8, node_name
        assert node["action"] == action, node_name
    for name in ("右下角_宝箱.png", "秘境之门_入口.png", "秘境之门_识别.png",
                 "秘境之门_确定送出条件.png", "秘境之门_删除.png", "秘境之门_确认删除.png"):
        assert (ROOT / "assets/resource/image" / name).is_file()
    # OCR 节点契约
    assert pipeline["SecretRealmGateClickSend"]["expected"] == "^送出$"
    assert pipeline["SecretRealmGateClickSend"]["roi"] == [930, 149, 149, 522]
    assert pipeline["SecretRealmGateClickSend"]["custom_action"] == "SecretRealmGateClickSendAction"
    assert pipeline["SecretRealmGateSendPopup"]["expected"] == "选择|送出的鱼", "分支一分词兼容"
    assert pipeline["SecretRealmGateNoFishCheck"]["expected"] == "没有这种鱼|您没有", "分支二分词兼容"
    assert pipeline["SecretRealmGateClickPopupSend"]["roi"] == [886, 646, 68, 28]
    assert pipeline["SecretRealmGateClickClaim"]["roi"] == [605, 583, 68, 34]
    assert pipeline["SecretRealmGateClickClaim"]["post_delay"] == 5000, "领取后等 5 秒"
    assert pipeline["SecretRealmGateClickConfirm"]["roi"] == [605, 583, 68, 34]
    assert pipeline["SecretRealmGateClickDelete"]["custom_action"] == "SecretRealmGateClickDeleteAction"
    assert pipeline["SecretRealmGateVerifyTank"]["template"] == "主界面特征.png"
    print("[PASS] 模板/ROI/OCR 契约：用户坐标原样接入，两个弹窗标题均做分词兼容")

    # ---- 静态拓扑：分支统一回流 SendRouter；双出口 ----
    assert business_next(pipeline["SecretRealmGateClickConfirm"]) == ["SecretRealmGateSendRouter"]
    assert business_next(pipeline["SecretRealmGateClickConfirmDelete"]) == ["SecretRealmGateSendRouter"]
    assert business_next(pipeline["SecretRealmGateVerifyTank"]) == [
        "DailyRoutineReturnIfActive", "DailyRoutineStandaloneDone"
    ]
    assert business_next(pipeline["SecretRealmGateStartRouter"]) == [
        "SecretRealmGateMainPage", "SecretRealmGateOpenTreasure",
        "SecretRealmGateMainTankEntry", "SecretRealmGateAbort",
    ], "主鱼缸启动必须先开宝箱再点入口"
    assert business_next(pipeline["SecretRealmGateOpenTreasure"]) == ["SecretRealmGateMainTankEntry"]
    assert pipeline["SecretRealmGateVerifyTank"]["custom_action"] == "SecretRealmGateDoneAction"
    print("[PASS] 静态拓扑：两分支结束统一回流 SendRouter，VerifyTank 走日常双出口")

    # ---- 场景 1：主鱼缸启动，两单分支一送出后无送出，退出回鱼缸 ----
    sim = SecretRealmGateSimulator(pipeline, {
        "stage": "main_tank", "send_visible": True, "branch": "send", "send_condition": True,
    }).run({
        "stage": "main_tank", "send_visible": True, "branch": "send", "send_condition": True,
    })
    # 模拟器单链只送出一单（Confirm 后 send_visible=False），验证链路完整
    assert sim.clicks.count("SecretRealmGateClickSend") == 1
    assert "SecretRealmGateOpenTreasure" in sim.visited, "主鱼缸启动必须先开宝箱"
    assert "SecretRealmGateMainTankEntry" in sim.visited
    assert "SecretRealmGateSendPopup" in sim.visited
    assert "SecretRealmGateCheckSendCondition" in sim.visited
    assert "SecretRealmGateClickPopupSend" in sim.visited
    assert "SecretRealmGateClickClaim" in sim.visited
    assert "SecretRealmGateClickConfirm" in sim.visited
    assert "SecretRealmGateExitGate" in sim.visited
    assert "SecretRealmGateVerifyTank" in sim.visited
    assert "SecretRealmGateAbort" not in sim.visited
    assert sim.outcome == "daily_exit"
    print("[PASS] 场景 1：主鱼缸启动 → 分支一完整链 → 无送出 → 返回确认主鱼缸 → 双出口")

    # ---- 场景 2：分支二（没有这种鱼）→ 相对偏移删除 → 确认删除 ----
    import agent.runtime_state as rs
    import agent.my_action as ma
    rs.secret_realm_gate_state["last_send_box"] = [980, 441, 51, 29]
    ctx = MockContext(delete_hit_box=[1239, 330, 15, 17])
    act = ma.SecretRealmGateClickDeleteAction()
    assert act.run(ctx, MockRunArg()) is True
    assert ctx.ctrl.clicks == [(1246, 338)], ctx.ctrl.clicks  # 垃圾桶模板命中框中心
    assert rs.secret_realm_gate_state["last_send_box"] is None
    # 未命中删除图标时必须失败（拒绝盲点）
    rs.secret_realm_gate_state["last_send_box"] = [980, 441, 51, 29]
    assert act.run(MockContext(delete_hit_box=None), MockRunArg()) is False
    rs.secret_realm_gate_state["last_send_box"] = None
    print("[PASS] 场景 2：分支二相对偏移 (+241,-117) 命中垃圾桶模板后点击；未命中拒绝盲点")

    sim = SecretRealmGateSimulator(pipeline, {
        "stage": "gate", "send_visible": True, "branch": "no_fish",
    }).run({
        "stage": "gate", "send_visible": True, "branch": "no_fish",
    })
    assert "SecretRealmGateNoFishCheck" in sim.visited
    assert "SecretRealmGateClickDelete" in sim.visited
    assert "SecretRealmGateClickConfirmDelete" in sim.visited
    assert "SecretRealmGateSendPopup" not in sim.visited
    assert "SecretRealmGateExitGate" in sim.visited
    assert sim.outcome == "daily_exit"
    print("[PASS] 场景 2b：分支二完整链后回流退出，不进入分支一")

    # ---- 场景 3：主页直接启动（无需点入口）----
    sim = SecretRealmGateSimulator(pipeline, {
        "stage": "gate", "send_visible": False,
    }).run({"stage": "gate", "send_visible": False})
    assert "SecretRealmGateMainTankEntry" not in sim.visited
    assert "SecretRealmGateExitGate" in sim.visited
    assert sim.outcome == "daily_exit"
    print("[PASS] 场景 3：已在秘境之门主页启动（最深恢复），无送出直接退出")

    # ---- 场景 4：ClickSendAction 记录 OCR 框 ----
    ctx2 = MockContext()
    ctx2.ctrl = MockCtrl()
    act_send = ma.SecretRealmGateClickSendAction()

    class _Arg(MockRunArg):
        pass

    arg = _Arg(box=[961, 259, 83, 29])
    arg.box = [961, 259, 83, 29]
    assert act_send.run(ctx2, arg) is True
    assert rs.secret_realm_gate_state["last_send_box"] == [961, 259, 83, 29]
    assert ctx2.ctrl.clicks == [(1002, 273)]  # OCR 框中心（点击文字本身）
    rs.secret_realm_gate_state["last_send_box"] = None
    print("[PASS] 场景 4：ClickSend 点击 OCR 框中心（文字本身）并记录位置供分支二使用")

    # ---- 日常收尾接入契约 ----
    assert "DailyRoutineEnableSecretRealmGate" in routine
    assert routine["DailyRoutineEnableSecretRealmGate"]["enabled"] is False
    dispatcher_next = business_next(routine["DailyRoutineDispatcher"])
    assert "DailyRoutineStepSecretRealmGate" in dispatcher_next
    assert dispatcher_next.index("DailyRoutineStepGreenWildDaily") < dispatcher_next.index("DailyRoutineStepSecretRealmGate")
    step_node = routine["DailyRoutineStepSecretRealmGate"]
    assert step_node["custom_recognition_param"]["expected_step"] == "SECRET_REALM_GATE"
    assert business_next(step_node) == ["SecretRealmGateTask"]
    from agent.runtime_state import daily_routine_state
    assert "SecretRealmGate" in daily_routine_state["tasks"]
    # interface：独立任务 + 日常多选 case
    task = next(t for t in interface["task"] if t["entry"] == "SecretRealmGateTask")
    assert task["name"] == "秘境之门" and task["default_check"] is False
    cases = interface["option"]["日常收尾任务"]["cases"]
    srg_case = next(c for c in cases if c["name"] == "秘境之门")
    assert srg_case["pipeline_override"]["DailyRoutineEnableSecretRealmGate"]["enabled"] is True
    labels = [c["name"] for c in cases]
    assert labels.index("绿野寻仙踪日常") < labels.index("秘境之门")
    assert "秘境之门" not in interface["option"]["日常收尾任务"]["default_case"]
    print("[PASS] 日常收尾契约：Enable/Step/Dispatcher/队列顺序/多选 case 全部接入")

    print("[PASS] 秘境之门专项测试全部通过")


if __name__ == "__main__":
    run_tests()
