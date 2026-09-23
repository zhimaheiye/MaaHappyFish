"""秘境之门离线回归：使用既有截图作场景素材，模拟 Maa 识别结果与点击后页面。"""

import json
import re
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "dev/fixtures/secret_realm_gate"
PIPELINE = ROOT / "assets/resource/pipeline/features/secret_realm_gate.json"
SOURCE = ROOT / "agent/my_action.py"

import agent.my_action as action
from agent.runtime_state import secret_realm_gate_state


def result(text="", box=None, items=None):
    return SimpleNamespace(hit=box is not None, box=box, text=text, all_results=items or [])


def item(text, box):
    return SimpleNamespace(text=text, box=box)


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Controller:
    def __init__(self, context):
        self.context = context
        self.clicks = []

    def frame(self):
        ctx = self.context
        ctx.frames += 1
        if ctx.stage == "pending" and ctx.frames >= ctx.delay_frames:
            ctx.stage = "select"
        if ctx.stage == "animation" and ctx.frames >= ctx.confirm_at:
            ctx.stage = "confirm"
        return ctx.stage

    def post_click(self, x, y):
        self.clicks.append((x, y))
        ctx = self.context
        if ctx.stage == "select" and (x, y) == (1158, 82):
            ctx.stage = "main"
        elif ctx.stage == "select" and 885 <= x <= 960 and 640 <= y <= 680:
            ctx.stage = "claim"
        elif ctx.stage == "no_fish" and (x, y) == (300, 300):
            ctx.stage = "main"
        elif ctx.stage == "main" and x >= 1200:
            ctx.stage = "delete_confirm"
        elif ctx.stage == "delete_confirm":
            ctx.stage = "main"
        elif ctx.stage == "claim":
            ctx.stage = "animation"
            ctx.confirm_at = ctx.frames + ctx.reward_delay_frames
        elif ctx.stage == "confirm":
            ctx.stage = "main"
        return SimpleNamespace(wait=lambda: None)


class Context:
    def __init__(self, stage, count=(1, 1), delay_frames=8, reward_delay_frames=10,
                 send_items=None, delete_box=None):
        self.stage = stage
        self.count = count
        self.frames = 0
        self.delay_frames = delay_frames
        self.reward_delay_frames = reward_delay_frames
        self.confirm_at = 0
        self.send_items = send_items if send_items is not None else [item("送出", [980, 441, 51, 29])]
        self.delete_box = delete_box if delete_box is not None else [1239, 330, 15, 17]
        self.delete_roi = None
        self.controller = Controller(self)
        self.tasker = SimpleNamespace(controller=self.controller, running=True, stopping=False)

    def run_recognition(self, name, frame=None, pipeline_override=None):
        stage = frame if frame is not None else self.stage
        if name == "SecretRealmGateSendOcrAll":
            return result(items=self.send_items if stage == "main" else [])
        if name == "SecretRealmGateSelectedCount":
            n, m = self.count
            return result(items=[item(f"已经选中{n}/{m}条鱼", [550, 642, 180, 30])]) if stage == "select" else result()
        if name == "SecretRealmGateDeleteIcon":
            self.delete_roi = pipeline_override["roi"]
            return result(box=self.delete_box) if stage == "main" else result()
        matches = {
            "SecretRealmGateMainPage": ("main", [550, 20, 160, 50]),
            "SecretRealmGateSendPopup": ("select", [545, 48, 200, 35]),
            "SecretRealmGateNoFishCheck": ("no_fish", [720, 560, 160, 40]),
            "SecretRealmGateClickPopupSend": ("select", [886, 646, 68, 28]),
            "SecretRealmGateClickClaim": ("claim", [605, 583, 68, 34]),
            "SecretRealmGateClickConfirm": ("confirm", [605, 583, 68, 34]),
            "SecretRealmGateClickConfirmDelete": ("delete_confirm", [804, 462, 44, 44]),
        }
        expected_stage, box = matches.get(name, (None, None))
        return result(box=box) if stage == expected_stage else result()


def run_order(ctx):
    secret_realm_gate_state["last_send_box"] = [980, 441, 51, 29]
    clock = Clock()
    with ExitStack() as stack:
        stack.enter_context(patch.object(action, "_capture_720p", lambda ctrl: ctrl.frame()))
        stack.enter_context(patch.object(action.time, "monotonic", clock.monotonic))
        stack.enter_context(patch.object(action.time, "sleep", clock.sleep))
        ok = action.SecretRealmGateProcessOrderAction().run(ctx, SimpleNamespace())
    return ok, clock.now


def run_tests():
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    # 真实截图作为离线样本：此测试不请求模拟器或实时截图。
    images = {}
    for name in (
        "01_送鱼任务列表_初始3单.png", "02_选择您要送出的鱼_面板_树须泡泡4of7.png",
        "03_选择面板_仅1条鱼苗_1of1_可送.png", "04_您没有这种鱼_弹窗.png",
        "05_删除订单_二次确认.png", "06_送出成功_恭喜获得_领取.png",
        "07_随机奖励抽取_确定.png", "08_送单后槽位补新单_锁定态.png",
        "09_三槽全部锁定态.png",
        "11_按钮_钞票x5_付费禁止点.png",
    ):
        image = cv2.imdecode(np.fromfile(str(FIXTURES / name), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert image is not None and image.shape[0] > 0 and image.shape[1] > 0, name
        if not name.startswith("11_"):
            assert image.shape[:2] == (720, 1280), name
        images[name] = image

    ocr = RapidOCR()

    def fixture_text(name, roi):
        x, y, w, h = roi
        rows, _ = ocr(images[name][y:y + h, x:x + w])
        return "".join(str(row[1]).replace(" ", "") for row in (rows or []))

    assert "已经选中4/7条鱼" in fixture_text(
        "02_选择您要送出的鱼_面板_树须泡泡4of7.png", (510, 624, 270, 70))
    assert "已经选中1/1条鱼" in fixture_text(
        "03_选择面板_仅1条鱼苗_1of1_可送.png", (510, 624, 270, 70))
    assert "您没有这种鱼" in fixture_text(
        "04_您没有这种鱼_弹窗.png", (680, 530, 260, 90))
    assert "送出" not in fixture_text(
        "09_三槽全部锁定态.png", (930, 149, 149, 522))

    pipeline = json.loads(PIPELINE.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    assert "SecretRealmGatePopupWait" not in pipeline
    assert "SecretRealmGateMarkNoResponseAction" not in source
    assert "no_response_rows" not in source
    assert "enable_srg = False" in source
    assert pipeline["SecretRealmGateClickSend"]["on_error"] == ["SecretRealmGateAbort"]
    assert pipeline["SecretRealmGateProcessOrder"]["on_error"] == ["SecretRealmGateAbort"]
    assert pipeline["SecretRealmGateSendOcrAll"]["expected"] == "^送出$"
    assert pipeline["SecretRealmGateClickPopupSend"]["expected"] == "^送出$"
    assert pipeline["SecretRealmGateNoFishCheck"]["roi"] == [680, 530, 260, 90]
    assert pipeline["SecretRealmGateNoMoreSend"]["recognition"] == "TemplateMatch"

    # Case 1: 72/12 是总拥有/需求，并不证明鱼苗有 12 条。
    own, need = map(int, re.search(r"需要：\s*(\d+)/(\d+)", "需要：72/12").groups())
    assert (own, need) == (72, 12)
    ctx = Context("select", count=(4, 12))
    ok, _ = run_order(ctx)
    assert ok and ctx.controller.clicks[0] == (1158, 82)
    assert (920, 660) not in ctx.controller.clicks
    print("[PASS] Case 1: 72/12 不作为可送判据，鱼苗 4/12 删除")

    # Case 2: 1/1 足量，只能送出、领奖、确认。
    ctx = Context("select", count=(1, 1))
    ok, _ = run_order(ctx)
    assert ok and ctx.controller.clicks == [(920, 660), (639, 600), (639, 600)]
    print("[PASS] Case 2: 1/1 送出并完成领奖")

    # Case 3: 4/7 不足，先关面板，后删本单。
    ctx = Context("select", count=(4, 7))
    ok, _ = run_order(ctx)
    assert ok and ctx.controller.clicks == [(1158, 82), (1246, 338), (826, 484)]
    print("[PASS] Case 3: 4/7 关闭选择面板并删除同卡订单")

    # Case 4: 无鱼提示无 X，安全点击窗外后才删。
    ctx = Context("no_fish")
    ok, _ = run_order(ctx)
    assert ok and ctx.controller.clicks == [(300, 300), (1246, 338), (826, 484)]
    print("[PASS] Case 4: 无鱼弹窗点窗外关闭、确认主页、删除")

    # Case 5: 3.5 秒后才出现面板，早期 miss 不跳行。
    ctx = Context("pending", count=(1, 1), delay_frames=8)
    ok, elapsed = run_order(ctx)
    assert ok and elapsed >= 3.5 and ctx.controller.clicks[0] == (920, 660)
    print("[PASS] Case 5: 弹窗延迟出现仍可继续")

    # Case 6: 全窗口未知，拒绝跳行和任何额外点击。
    ctx = Context("unknown")
    ok, elapsed = run_order(ctx)
    assert not ok and elapsed >= 9 and ctx.controller.clicks == []
    print("[PASS] Case 6: 未知分支限时后安全失败")

    # Case 7: 领奖动画内确定短暂消失，继续读新帧直到出现。
    ctx = Context("select", count=(1, 1), reward_delay_frames=10)
    ok, elapsed = run_order(ctx)
    assert ok and elapsed >= 4 and ctx.controller.clicks[-1] == (639, 600)
    print("[PASS] Case 7: 领取后延迟出现确定，仍点击实际 OCR 框")

    # Case 8/9: 锁定单的绿色钞票按钮不能靠颜色或相似外观入选。
    ctx = Context("main", send_items=[item("钞票 x5", [980, 625, 51, 29])])
    box = action.SecretRealmGateFindSendCardReco().analyze(ctx, SimpleNamespace(image="main"))
    assert box is None and ctx.controller.clicks == []
    ctx.send_items.append(item("送出", [980, 441, 51, 29]))
    box = action.SecretRealmGateFindSendCardReco().analyze(ctx, SimpleNamespace(image="main"))
    assert box == [980, 441, 51, 29]
    print("[PASS] Case 8/9: 钞票 xN 锁定态不点，只接受 OCR 完整送出")

    # Case 10: 原 slot2 送出框只允许 slot2 垃圾桶；其它槽即使返回模板命中也拒绝。
    secret_realm_gate_state["last_send_box"] = [980, 441, 51, 29]
    ctx = Context("main", delete_box=[1239, 513, 15, 17])
    with patch.object(action, "_capture_720p", lambda ctrl: ctrl.frame()):
        assert not action.SecretRealmGateClickDeleteAction().run(ctx, SimpleNamespace())
    assert ctx.controller.clicks == [] and ctx.delete_roi == [1206, 298, 80, 80]
    print("[PASS] Case 10: 跨槽删除模板被拒绝")

    interfaces = [json.loads((ROOT / path).read_text(encoding="utf-8")) for path in (
        "assets/interface.json", "client/interface.json", "client_avalonia/interface.json")]
    for interface in interfaces:
        assert all(task.get("entry") != "SecretRealmGateTask" for task in interface["task"])
        assert all(task.get("name") != "秘境之门" for preset in interface["preset"] for task in preset["task"])
        assert all(case["name"] != "秘境之门" for case in interface["option"]["日常收尾任务"]["cases"])
    assert pipeline["SecretRealmGateTask"]
    from agent.runtime_state import daily_routine_state
    assert action.InitDailyRoutineAction().run(
        SimpleNamespace(), SimpleNamespace(custom_action_param=json.dumps({"all_enabled": True})))
    assert "SECRET_REALM_GATE" not in daily_routine_state["queue"]
    daily_routine_state["active"] = False
    daily_routine_state["step"] = "INIT"
    daily_routine_state["queue"] = []
    print("[PASS] 三份界面配置隐藏用户入口，同时保留 Pipeline/Agent")
    print("[PASS] 秘境之门离线专项全部通过")


if __name__ == "__main__":
    run_tests()
