"""
dev/test_reindeer_fish.py
驯鹿鱼送收礼状态机与拓扑契约测试套件 (Case 1 ~ Case 7)
"""
import json
import os
import sys

PIPELINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "assets", "resource", "pipeline", "features", "reindeer_fish.json"
)


def load_pipeline():
    with open(PIPELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_topology_contracts():
    """静态拓扑契约断言"""
    pdata = load_pipeline()

    # 1. CollectAll 必须通过 AfterCollectRouter，不直连 RewardReturn 或 CommonBack
    collect_next = [n for n in pdata["ReindeerFishCollectAll"].get("next", []) if not n.startswith("[JumpBack]")]
    assert collect_next == ["ReindeerFishAfterCollectRouter"], f"CollectAll.next unexpected: {collect_next}"

    # 2. RewardReturn 关闭弹窗后必须重新进入 AfterCollectRouter，不能直接去 CommonBack
    reward_next = [n for n in pdata["ReindeerFishRewardReturn"].get("next", []) if not n.startswith("[JumpBack]")]
    assert reward_next == ["ReindeerFishAfterCollectRouter"], f"RewardReturn.next unexpected: {reward_next}"
    assert "ReindeerFishCommonBack" not in pdata["ReindeerFishRewardReturn"].get("next", [])

    # 3. AfterCollectRouter 结构与超时配置
    router = pdata["ReindeerFishAfterCollectRouter"]
    assert router["recognition"] == "DirectHit"
    assert 3000 <= router.get("timeout", 0) <= 5000, f"AfterCollectRouter timeout expected 3000~5000ms, got {router.get('timeout')}"
    router_next = [n for n in router.get("next", []) if not n.startswith("[JumpBack]")]
    assert router_next == [
        "ReindeerFishRewardReturn",
        "ReindeerFishReplyAll",
    ], f"AfterCollectRouter.next unexpected: {router_next}"

    # Contract 1: ReindeerFishClearAll must not be in any node's next list
    for node_name, node_data in pdata.items():
        if node_name != "ReindeerFishClearAll":
            assert "ReindeerFishClearAll" not in node_data.get("next", []), f"ReindeerFishClearAll found in {node_name}.next"

    # Contract 2: ReindeerFishClearAll action must not be Click
    if "ReindeerFishClearAll" in pdata:
        assert pdata["ReindeerFishClearAll"].get("action") != "Click", "ReindeerFishClearAll action must not be Click"

    assert router.get("on_error") == ["ReindeerFishAfterCollectNoReply"], f"AfterCollectRouter.on_error unexpected: {router.get('on_error')}"

    # 4. AfterCollectNoReply 兜底退出
    no_reply = pdata["ReindeerFishAfterCollectNoReply"]
    assert no_reply["recognition"] == "DirectHit"
    no_reply_next = [n for n in no_reply.get("next", []) if not n.startswith("[JumpBack]")]
    assert no_reply_next == ["ReindeerFishCommonBack"], f"AfterCollectNoReply.next unexpected: {no_reply_next}"

    # 5. ReplyAll 使用现场 OCR 的稳定子串与用户给定 ROI
    reply_all = pdata["ReindeerFishReplyAll"]
    assert reply_all["roi"] == [537, 611, 128, 44], f"ReplyAll ROI expected [537, 611, 128, 44], got {reply_all['roi']}"
    assert reply_all["expected"] == "键回礼"

    # 6. StartRouter 保留纯回礼直接入口
    start_next = [n for n in pdata["ReindeerFishStartRouter"].get("next", []) if not n.startswith("[JumpBack]")]
    assert "ReindeerFishReplyAll" in start_next, f"StartRouter missing ReplyAll: {start_next}"
    assert "ReindeerFishCollectAll" in start_next, f"StartRouter missing CollectAll: {start_next}"
    assert start_next[-1] == "ReindeerFishCommonBack", f"未知页面应最后点左上角返回: {start_next}"
    after_reply = [n for n in pdata["ReindeerFishAfterReplyRouter"].get("next", []) if not n.startswith("[JumpBack]")]
    assert after_reply == [
        "ReindeerFishDirectGift",
        "ReindeerFishReplyPopupReturn",
        "ReindeerFishCommonBack",
    ], f"AfterReplyRouter.next unexpected: {after_reply}"
    popup_return = pdata["ReindeerFishReplyPopupReturn"]
    assert popup_return["expected"] == "^返回$"
    assert popup_return["roi"] == [470, 380, 340, 200]
    assert popup_return["action"] == "Click"
    assert "target" not in popup_return
    popup_next = [n for n in popup_return.get("next", []) if not n.startswith("[JumpBack]")]
    assert popup_next == ["ReindeerFishCommonBack"]
    clear_all = pdata["ReindeerFishClearAll"]
    assert clear_all["expected"] == "键清除"
    assert clear_all["roi"] == [500, 560, 260, 100]
    assert clear_all["action"] == "DoNothing"
    assert "target" not in clear_all

    print("[PASS] 静态拓扑契约验证通过")


class MockMaaSimulator:
    """模拟 MaaFramework 状态机执行流"""

    def __init__(self, pdata):
        self.pdata = pdata

    def run(self, start_node, frame_generator):
        """
        frame_generator: 生成每一帧可见的元素集合 set[str]，例如 {"键收取"} 或 {"键回礼"} 或 {"返回"}
        返回执行过的业务节点名称列表
        """
        current_node = start_node
        history = [current_node]
        max_steps = 30

        for _ in range(max_steps):
            node_def = self.pdata[current_node]
            action = node_def.get("action", "DoNothing")

            # 如果到了结束/退出节点
            if current_node in ("ReindeerFishVerifyTank", "ReindeerFishAbort"):
                break

            # 评估 next 节点
            raw_next = [n for n in node_def.get("next", []) if not n.startswith("[JumpBack]")]
            timeout_ms = node_def.get("timeout", 1000)
            elapsed_ms = 0
            step_ms = 500
            matched_next = None

            while elapsed_ms <= timeout_ms:
                current_screen_elements = frame_generator(current_node, elapsed_ms, history)

                for candidate in raw_next:
                    cand_def = self.pdata[candidate]
                    cand_reco = cand_def.get("recognition")

                    if cand_reco == "DirectHit":
                        matched_next = candidate
                        break
                    elif cand_reco == "OCR":
                        expected = cand_def.get("expected")
                        if candidate in current_screen_elements or expected in current_screen_elements:
                            matched_next = candidate
                            break
                    elif cand_reco == "TemplateMatch":
                        tpl = cand_def.get("template")
                        if candidate in current_screen_elements or tpl in current_screen_elements:
                            matched_next = candidate
                            break

                if matched_next:
                    break
                elapsed_ms += step_ms

            if matched_next:
                current_node = matched_next
                history.append(current_node)
            else:
                # 超时无匹配，检查 on_error
                on_error = node_def.get("on_error", [])
                if on_error:
                    current_node = on_error[0]
                    history.append(current_node)
                else:
                    break

        return history


def test_cases():
    pdata = load_pipeline()
    sim = MockMaaSimulator(pdata)

    # -------------------------------------------------------------
    # Case 1: 初始只有一键收取，无回礼
    # CollectAll -> AfterCollectRouter -> 无 ReplyAll -> CommonBack -> VerifyTank
    # -------------------------------------------------------------
    def frames_case_1(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishCollectAll" not in history:
            return {"键收取"}
        # 收取后：无弹窗(无RewardReturn)、无回礼，仅左上角通用返回
        return {"ReindeerFishCommonBack"}

    hist1 = sim.run("ReindeerFishStartRouter", frames_case_1)
    assert "ReindeerFishCollectAll" in hist1
    assert "ReindeerFishAfterCollectRouter" in hist1
    assert "ReindeerFishAfterCollectNoReply" in hist1
    assert "ReindeerFishCommonBack" in hist1
    assert "ReindeerFishReplyAll" not in hist1
    print("[PASS] Case 1: 初始只有一键收取，超时无回礼后安全返回鱼缸")

    # -------------------------------------------------------------
    # Case 2: 一键收取后弹奖励窗
    # CollectAll -> RewardReturn -> AfterCollectRouter
    # 确认 RewardReturn 不能再直接指向 CommonBack
    # -------------------------------------------------------------
    def frames_case_2(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishCollectAll" not in history:
            return {"键收取"}
        if "ReindeerFishRewardReturn" not in history:
            # 弹出了奖励弹窗，中间有返回
            return {"ReindeerFishRewardReturn"}
        # 弹窗关闭后无回礼
        return {"ReindeerFishCommonBack"}

    hist2 = sim.run("ReindeerFishStartRouter", frames_case_2)
    assert "ReindeerFishCollectAll" in hist2
    assert "ReindeerFishRewardReturn" in hist2
    idx_reward = hist2.index("ReindeerFishRewardReturn")
    assert hist2[idx_reward + 1] == "ReindeerFishAfterCollectRouter", "RewardReturn 必须回到 AfterCollectRouter"
    assert "ReindeerFishCommonBack" != hist2[idx_reward + 1], "RewardReturn 绝不能直接进入 CommonBack"
    print("[PASS] Case 2: 一键收取后弹奖励窗，关闭弹窗后重新进入 AfterCollectRouter")

    # -------------------------------------------------------------
    # Case 3: 收取后出现一键回礼（先有弹窗，再有一键回礼）
    # CollectAll -> RewardReturn -> AfterCollectRouter -> ReplyAll -> ...
    # -------------------------------------------------------------
    def frames_case_3(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishCollectAll" not in history:
            return {"键收取"}
        if "ReindeerFishRewardReturn" not in history:
            return {"ReindeerFishRewardReturn"}  # 奖励弹窗中间返回
        if "ReindeerFishReplyAll" not in history:
            return {"键回礼"}  # 现场 OCR 会漏掉首字“一”
        # 回礼后无直接赠送弹窗，点左上角返回
        return {"ReindeerFishCommonBack"}

    hist3 = sim.run("ReindeerFishStartRouter", frames_case_3)
    assert "ReindeerFishCollectAll" in hist3
    assert "ReindeerFishRewardReturn" in hist3
    assert "ReindeerFishReplyAll" in hist3, "必须真正执行了 ReplyAll"
    assert "ReindeerFishAfterReplyRouter" in hist3
    assert "ReindeerFishCommonBack" in hist3
    assert "ReindeerFishAfterCollectNoReply" not in hist3
    print("[PASS] Case 3: 收取并关闭奖励窗后刷新出回礼，成功执行 ReplyAll 业务链")

    # -------------------------------------------------------------
    # Case 4: 无奖励弹窗但直接刷新成一键回礼
    # CollectAll -> AfterCollectRouter -> ReplyAll
    # -------------------------------------------------------------
    def frames_case_4(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishCollectAll" not in history:
            return {"键收取"}
        if "ReindeerFishReplyAll" not in history:
            return {"键回礼"}  # 无弹窗，直接就是一键回礼
        return {"ReindeerFishCommonBack"}

    hist4 = sim.run("ReindeerFishStartRouter", frames_case_4)
    assert "ReindeerFishCollectAll" in hist4
    assert "ReindeerFishRewardReturn" not in hist4
    assert "ReindeerFishReplyAll" in hist4
    assert "ReindeerFishAfterCollectNoReply" not in hist4
    print("[PASS] Case 4: 无奖励弹窗直接刷新成一键回礼，立即响应无需超时")

    # -------------------------------------------------------------
    # Case 5: 页面刷新稍慢（前 1500ms 没有 ReplyAll，随后出现）
    # -------------------------------------------------------------
    def frames_case_5(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishCollectAll" not in history:
            return {"键收取"}
        if "ReindeerFishReplyAll" not in history:
            if elapsed_ms < 1500:
                return {"ReindeerFishCommonBack"}  # 还在网络请求/重绘中，页面上只有通用返回，无回礼
            return {"键回礼"}  # 稍后出现
        return {"ReindeerFishCommonBack"}

    hist5 = sim.run("ReindeerFishStartRouter", frames_case_5)
    assert "ReindeerFishCollectAll" in hist5
    assert "ReindeerFishReplyAll" in hist5, "刷新稍慢时仍必须成功识别 ReplyAll，不可提前退出"
    assert "ReindeerFishAfterCollectNoReply" not in hist5
    print("[PASS] Case 5: 页面刷新稍慢时，AfterCollectRouter 窗口内成功捕获 ReplyAll")

    # -------------------------------------------------------------
    # Case 6: 初始就是一键回礼
    # StartRouter -> ReplyAll
    # -------------------------------------------------------------
    def frames_case_6(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishReplyAll" not in history:
            return {"键回礼"}  # 初始即回礼
        return {"ReindeerFishCommonBack"}

    hist6 = sim.run("ReindeerFishStartRouter", frames_case_6)
    assert "ReindeerFishCollectAll" not in hist6
    assert "ReindeerFishReplyAll" in hist6
    assert "ReindeerFishAfterReplyRouter" in hist6
    print("[PASS] Case 6: 初始就是一键回礼场景，直接进入回礼业务链")

    # -------------------------------------------------------------
    # Case 7: 确实没有回礼（稳定窗口 4000ms 期间一直未出现回礼）
    # -------------------------------------------------------------
    def frames_case_7(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishCollectAll" not in history:
            return {"键收取"}
        # 收取后始终无任何回礼或弹窗，仅有通用返回
        return {"ReindeerFishCommonBack"}

    hist7 = sim.run("ReindeerFishStartRouter", frames_case_7)
    assert "ReindeerFishCollectAll" in hist7
    assert "ReindeerFishAfterCollectRouter" in hist7
    assert "ReindeerFishAfterCollectNoReply" in hist7
    assert "ReindeerFishCommonBack" in hist7
    print("[PASS] Case 7: 稳定窗口期满后确认无回礼，安全触发 AfterCollectNoReply 返回")

    def frames_case_8(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        return {"键清除", "ReindeerFishCommonBack"}

    hist8 = sim.run("ReindeerFishStartRouter", frames_case_8)
    assert "ReindeerFishClearAll" not in hist8, "ReindeerFishClearAll should be ignored"
    assert "ReindeerFishCollectAll" not in hist8
    assert "ReindeerFishCommonBack" in hist8
    print("[PASS] Case 8: 礼物已送完页(有一键清除)不再误点清除，安全返回鱼缸")

    def frames_case_9(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        return {"ReindeerFishCommonBack"}

    hist9 = sim.run("ReindeerFishStartRouter", frames_case_9)
    assert "ReindeerFishClearAll" not in hist9
    assert "ReindeerFishCollectAll" not in hist9
    assert "ReindeerFishCommonBack" in hist9
    print("[PASS] Case 9: 未识别到收取/回礼/清除时点左上角返回")

    def frames_case_10(node, elapsed_ms, history):
        if "ReindeerFishCommonBack" in history:
            return {"主界面特征.png"}
        if "ReindeerFishReplyAll" not in history:
            return {"键回礼"}
        if "ReindeerFishReplyPopupReturn" not in history:
            return {"^返回$"}
        return {"ReindeerFishCommonBack"}

    hist10 = sim.run("ReindeerFishStartRouter", frames_case_10)
    assert "ReindeerFishReplyAll" in hist10
    assert "ReindeerFishReplyPopupReturn" in hist10
    assert "ReindeerFishCommonBack" in hist10
    print("[PASS] Case 10: 一键回礼后的结算弹窗点击返回，再离开页面")


def main():
    print("=" * 60)
    print("  ReindeerFish 送收礼功能拓扑与场景测试")
    print("=" * 60)
    test_topology_contracts()
    test_cases()
    print("=" * 60)
    print("  [ALL PASS] 驯鹿鱼专项场景测试全部通过！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
