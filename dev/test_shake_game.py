# -*- coding: utf-8 -*-
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import my_action, my_reco
from agent.runtime_state import shake_game_state


# =====================================================================
# A & B. Controller info 与 VM index 解析测试
# =====================================================================
def test_controller_info_parsing_normal():
    """测试正常从 controller.info (包含 extras.mumu) 解析 manager_path 与 vm_index"""
    with tempfile.TemporaryDirectory() as tmpdir:
        mumu_root = Path(tmpdir)
        nx_dir = mumu_root / "nx_main"
        nx_dir.mkdir(parents=True, exist_ok=True)
        fake_manager = nx_dir / "MuMuManager.exe"
        fake_manager.write_text("dummy", encoding="utf-8")

        mock_ctrl = MagicMock()
        mock_ctrl.info = json.dumps({
            "config": {
                "extras": {
                    "mumu": {
                        "path": str(mumu_root),
                        "index": 2,
                    }
                }
            }
        })

        manager_path, vm_index = my_action._get_mumu_manager_and_vm(mock_ctrl)
        assert manager_path is not None, "应当成功定位 MuMuManager.exe"
        assert manager_path.resolve() == fake_manager.resolve()
        assert vm_index == 2, f"vm_index 应当解析为 2，实际为 {vm_index}"


def test_controller_info_parsing_adb_fallback():
    """测试通过 adb_path 同级目录推导 MuMuManager.exe"""
    with tempfile.TemporaryDirectory() as tmpdir:
        bin_dir = Path(tmpdir) / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        fake_adb = bin_dir / "adb.exe"
        fake_adb.write_text("dummy", encoding="utf-8")
        fake_manager = bin_dir / "MuMuManager.exe"
        fake_manager.write_text("dummy", encoding="utf-8")

        mock_ctrl = MagicMock()
        mock_ctrl.info = {
            "adb_path": str(fake_adb),
            "config": {
                "extras": {
                    "mumu": {
                        "index": 1,
                    }
                }
            }
        }

        manager_path, vm_index = my_action._get_mumu_manager_and_vm(mock_ctrl)
        assert manager_path is not None
        assert manager_path.resolve() == fake_manager.resolve()
        assert vm_index == 1


def test_vm_index_missing_strict_none():
    """测试当缺少 vm_index 时严格返回 (None, None)，禁止回退默认 0"""
    with tempfile.TemporaryDirectory() as tmpdir:
        mumu_root = Path(tmpdir)
        nx_dir = mumu_root / "nx_main"
        nx_dir.mkdir(parents=True, exist_ok=True)
        (nx_dir / "MuMuManager.exe").write_text("dummy", encoding="utf-8")

        # Case 1: extras.mumu 中无 index 字段
        ctrl1 = MagicMock()
        ctrl1.info = {
            "config": {
                "extras": {
                    "mumu": {
                        "path": str(mumu_root),
                    }
                }
            }
        }
        p1, idx1 = my_action._get_mumu_manager_and_vm(ctrl1)
        assert p1 is None and idx1 is None, f"缺少 index 时应返回 (None, None)，实际为: ({p1}, {idx1})"
        assert idx1 != 0, "严禁默认将 index 设为 0！"

        # Case 2: index 为 None
        ctrl2 = MagicMock()
        ctrl2.info = {
            "config": {
                "extras": {
                    "mumu": {
                        "path": str(mumu_root),
                        "index": None,
                    }
                }
            }
        }
        p2, idx2 = my_action._get_mumu_manager_and_vm(ctrl2)
        assert p2 is None and idx2 is None
        assert idx2 != 0

        # Case 3: 只有 adb 连接端口，无任何 mumu extra
        ctrl3 = MagicMock()
        ctrl3.info = {"connection": "127.0.0.1:16416"}
        p3, idx3 = my_action._get_mumu_manager_and_vm(ctrl3)
        assert p3 is None and idx3 is None

        # Case 4: info 为 None 或空
        ctrl4 = MagicMock()
        ctrl4.info = None
        p4, idx4 = my_action._get_mumu_manager_and_vm(ctrl4)
        assert p4 is None and idx4 is None


# =====================================================================
# C. subprocess 命令参数拼接校验
# =====================================================================
def test_subprocess_command_format():
    """验证生成的命令行参数格式必须严格符合 MuMuManager RPC 要求"""
    manager = Path(r"C:\Program Files\Netease\MuMuPlayer-12.0\nx_main\MuMuManager.exe")
    vm_index = 3

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"errcode": 0, "errmsg": ""}', stderr="")
        ok = my_action._run_mumu_shake(manager, vm_index, timeout=2.0)
        assert ok is True

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        expected_cmd = [
            str(manager),
            "control",
            "-v",
            str(vm_index),
            "tool",
            "func",
            "-n",
            "shake",
        ]
        assert args[0] == expected_cmd, f"命令行不匹配: {args[0]} != {expected_cmd}"
        assert kwargs.get("shell") is False, "shell 必须为 False"
        assert kwargs.get("timeout") == 2.0


# =====================================================================
# D. MuMu 返回结果判定测试
# =====================================================================
def test_mumu_shake_returns():
    """测试各种 subprocess 退出码与 JSON errcode 返回的处理判定"""
    manager = Path(r"C:\fake\MuMuManager.exe")
    vm_index = 0

    # 1. 成功：returncode == 0 且 errcode == 0
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"errcode": 0, "errmsg": ""}', stderr="")
        assert my_action._run_mumu_shake(manager, vm_index) is True

    # 2. 失败：returncode != 0
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout='{"errcode": 0}', stderr="error")
        assert my_action._run_mumu_shake(manager, vm_index) is False

    # 3. 失败：returncode == 0 但 errcode != 0
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"errcode": -1, "errmsg": "vm not running"}', stderr="")
        assert my_action._run_mumu_shake(manager, vm_index) is False

    # 4. 失败：stdout 非合法 JSON
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='not a json output', stderr="")
        assert my_action._run_mumu_shake(manager, vm_index) is False

    # 5. 失败：stdout 为空
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr="")
        assert my_action._run_mumu_shake(manager, vm_index) is False

    # 6. 失败：subprocess 调用超时
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="shake", timeout=2.0)):
        assert my_action._run_mumu_shake(manager, vm_index) is False


# =====================================================================
# E. ShakeGamePlayAction 循环状态机测试
# =====================================================================
def test_shake_game_play_action_settlement_detected():
    """模拟摇晃数次后检测到结算弹窗：返回 True，状态置为 SETTLEMENT"""
    action = my_action.ShakeGamePlayAction()
    mock_context = MagicMock()
    mock_ctrl = MagicMock()
    mock_context.tasker.controller = mock_ctrl

    fake_manager = Path(r"C:\fake\MuMuManager.exe")
    fake_tpl = np.zeros((10, 10, 3), dtype=np.uint8)

    with patch.object(my_action, "_get_mumu_manager_and_vm", return_value=(fake_manager, 0)), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(my_action, "_get_shake_game_templates", return_value={"cancel": fake_tpl}), \
         patch.object(my_action, "_run_mumu_shake", return_value=True), \
         patch.object(my_action, "_task_cancelled", return_value=False), \
         patch.object(my_action, "_capture_720p", return_value=np.zeros((720, 1280, 3), dtype=np.uint8)), \
         patch("cv2.matchTemplate", return_value=np.array([[0.85]], dtype=np.float32)), \
         patch("time.sleep", return_value=None):

        res = action.run(mock_context, MagicMock())
        assert res is True
        assert shake_game_state["status"] == "SETTLEMENT"


def test_shake_game_play_action_user_cancelled():
    """模拟任务被用户取消：返回 False，状态置为 FAILED"""
    action = my_action.ShakeGamePlayAction()
    mock_context = MagicMock()
    mock_ctrl = MagicMock()
    mock_context.tasker.controller = mock_ctrl

    fake_manager = Path(r"C:\fake\MuMuManager.exe")
    fake_tpl = np.zeros((10, 10, 3), dtype=np.uint8)

    with patch.object(my_action, "_get_mumu_manager_and_vm", return_value=(fake_manager, 0)), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(my_action, "_get_shake_game_templates", return_value={"cancel": fake_tpl}), \
         patch.object(my_action, "_task_cancelled", return_value=True), \
         patch("time.sleep", return_value=None):

        res = action.run(mock_context, MagicMock())
        assert res is False
        assert shake_game_state["status"] == "FAILED"


def test_shake_game_play_action_consecutive_failures_tripped():
    """模拟连续 3 次 RPC 失败触发安全熔断：返回 False，状态置为 FAILED"""
    action = my_action.ShakeGamePlayAction()
    mock_context = MagicMock()
    mock_ctrl = MagicMock()
    mock_context.tasker.controller = mock_ctrl

    fake_manager = Path(r"C:\fake\MuMuManager.exe")
    fake_tpl = np.zeros((10, 10, 3), dtype=np.uint8)

    with patch.object(my_action, "_get_mumu_manager_and_vm", return_value=(fake_manager, 0)), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(my_action, "_get_shake_game_templates", return_value={"cancel": fake_tpl}), \
         patch.object(my_action, "_run_mumu_shake", return_value=False), \
         patch.object(my_action, "_task_cancelled", return_value=False), \
         patch.object(my_action, "_capture_720p", return_value=np.zeros((720, 1280, 3), dtype=np.uint8)), \
         patch("cv2.matchTemplate", return_value=np.array([[0.10]], dtype=np.float32)), \
         patch("time.sleep", return_value=None):

        res = action.run(mock_context, MagicMock())
        assert res is False
        assert shake_game_state["status"] == "FAILED"


def test_shake_game_play_action_timeout_without_settlement():
    """模拟达到最大时长但未检出结算弹窗：返回 False，状态置为 FAILED，严禁盲点假装成功"""
    action = my_action.ShakeGamePlayAction()
    mock_context = MagicMock()
    mock_ctrl = MagicMock()
    mock_context.tasker.controller = mock_ctrl

    fake_manager = Path(r"C:\fake\MuMuManager.exe")
    fake_tpl = np.zeros((10, 10, 3), dtype=np.uint8)

    # 通过将超时限制置为负值或微小值，强制单次或0次后直接超时
    with patch.object(my_action, "_get_mumu_manager_and_vm", return_value=(fake_manager, 0)), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(my_action, "_get_shake_game_templates", return_value={"cancel": fake_tpl}), \
         patch.object(my_action, "_run_mumu_shake", return_value=True), \
         patch.object(my_action, "_task_cancelled", return_value=False), \
         patch.object(my_action, "_capture_720p", return_value=np.zeros((720, 1280, 3), dtype=np.uint8)), \
         patch("cv2.matchTemplate", return_value=np.array([[0.20]], dtype=np.float32)), \
         patch.object(my_action, "SHAKE_GAME_MAX_DURATION_SECONDS", 0.001), \
         patch("time.sleep", return_value=None):

        res = action.run(mock_context, MagicMock())
        assert res is False, "超时未结算必须返回 False"
        assert shake_game_state["status"] == "FAILED"


# =====================================================================
# F. Pipeline 拓扑结构与注册一致性测试
# =====================================================================
def test_pipeline_contract_and_agent_registration():
    """验证 features/shake_game.json 节点拓扑及 CustomAction / CustomRecognition 注册"""
    pipeline_file = ROOT / "assets/resource/pipeline/features/shake_game.json"
    assert pipeline_file.is_file(), f"Pipeline 文件不存在: {pipeline_file}"

    data = json.loads(pipeline_file.read_text(encoding="utf-8"))
    expected_nodes = [
        "ShakeGameTask",
        "ShakeGameNavigation",
        "ShakeGamePlay",
        "ShakeGameExit",
        "ShakeGameRepeat",
        "ShakeGameDone",
        "ShakeGameVerifyTank",
    ]
    for n in expected_nodes:
        assert n in data, f"缺失预期节点: {n}"

    # 拓扑连接校验（剔除全局弹窗拦截节点）
    def business_next(node):
        return [x for x in node.get("next", []) if not x.startswith("[JumpBack]")]

    assert business_next(data["ShakeGameTask"]) == ["ShakeGameNavigation"]
    assert business_next(data["ShakeGameNavigation"]) == ["ShakeGamePlay", "ShakeGameDone"]
    assert business_next(data["ShakeGamePlay"]) == ["ShakeGameExit"]
    assert business_next(data["ShakeGameExit"]) == ["ShakeGameRepeat", "ShakeGameDone"]
    assert business_next(data["ShakeGameRepeat"]) == ["ShakeGameNavigation"]
    assert business_next(data["ShakeGameDone"]) == ["ShakeGameVerifyTank"]
    # 验证双出口路由：必须先尝试日常收尾返回，若非日常收尾则走独立完成
    assert business_next(data["ShakeGameVerifyTank"]) == [
        "DailyRoutineReturnIfActive",
        "DailyRoutineStandaloneDone",
    ]

    # Action / Reco 注册校验
    custom_actions = [
        "ShakeGameInitAction",
        "ShakeGameNavigationAction",
        "ShakeGamePlayAction",
        "ShakeGameExitAction",
        "ShakeGameDoneAction",
    ]
    for ca in custom_actions:
        assert hasattr(my_action, ca), f"agent.my_action 缺少 CustomAction: {ca}"

    assert hasattr(my_reco, "CheckShakeGameCanPlayReco"), "agent.my_reco 缺少 CustomRecognition: CheckShakeGameCanPlayReco"
    assert hasattr(my_reco, "CheckShakeGameRepeatReco"), "agent.my_reco 缺少 CustomRecognition: CheckShakeGameRepeatReco"
    assert hasattr(my_reco, "CheckDailyRoutineActiveReco"), "agent.my_reco 缺少 CustomRecognition: CheckDailyRoutineActiveReco"


def test_shake_game_standalone_and_daily_routine_exit_routing():
    """验证摇一摇在独立运行与日常收尾中的双出口路由分流行为 (Case A & Case B)"""
    from agent.runtime_state import daily_routine_state, shake_game_state
    from agent.my_action import ShakeGameDoneAction
    from agent.my_reco import CheckDailyRoutineActiveReco

    class DummyContext:
        pass

    class DummyArg:
        custom_action_param = ""
        custom_recognition_param = ""

    action = ShakeGameDoneAction()
    active_reco = CheckDailyRoutineActiveReco()
    ctx = DummyContext()
    arg = DummyArg()

    # Case A: 独立运行 ShakeGameTask (daily_routine_state["active"] == False)
    daily_routine_state["active"] = False
    daily_routine_state["step"] = "INIT"
    shake_game_state["status"] = "DONE"

    # 执行 ShakeGameDoneAction
    ret = action.run(ctx, arg)
    assert ret is True
    # 验证: 独立运行模式下，严禁 advance daily routine step
    assert daily_routine_state["step"] == "INIT"
    assert daily_routine_state["active"] is False
    # 验证: CheckDailyRoutineActiveReco 必须返回 None (不命中 DailyRoutineReturnIfActive，直接流向 DailyRoutineStandaloneDone 成功结束)
    assert active_reco.analyze(ctx, arg) is None

    # Case B: 作为 DailyRoutine 子任务运行 (daily_routine_state["active"] == True)
    daily_routine_state["active"] = True
    daily_routine_state["step"] = "SHAKE_GAME"
    daily_routine_state["queue"] = ["FISHING"]
    daily_routine_state["tasks"]["ShakeGame"]["status"] = "IDLE"

    # 执行 ShakeGameDoneAction
    ret = action.run(ctx, arg)
    assert ret is True
    # 验证: 日常收尾容器中，正常 advance step 至下一个任务
    assert daily_routine_state["step"] == "FISHING"
    assert daily_routine_state["tasks"]["ShakeGame"]["status"] == "DONE"
    # 验证: CheckDailyRoutineActiveReco 命中有效矩形，流向 DailyRoutineReturnIfActive -> DailyRoutineDispatcher
    hit = active_reco.analyze(ctx, arg)
    assert hit == (0, 0, 10, 10)


# =====================================================================
# G. interface.json 契约与配置测试
# =====================================================================
def test_interface_json_contract():
    """验证 interface.json 中摇一摇小游戏配置正确，且三份文件字节级一致"""
    paths = [
        ROOT / "assets/interface.json",
        ROOT / "client/interface.json",
        ROOT / "client_avalonia/interface.json",
    ]

    base_bytes = paths[0].read_bytes()
    for p in paths[1:]:
        assert p.read_bytes() == base_bytes, f"{p} 与 assets/interface.json 字节不一致！"

    cfg = json.loads(base_bytes.decode("utf-8"))
    tasks = cfg.get("task", [])
    shake_task = next((t for t in tasks if t.get("entry") == "ShakeGameTask"), None)

    assert shake_task is not None, "interface.json 缺失 ShakeGameTask 配置"
    assert shake_task.get("name") == "摇一摇小游戏"
    assert shake_task.get("default_check") is False, "第一版独立任务 default_check 必须为 false"

    # 验证加入日常收尾选项
    daily_option = cfg.get("option", {}).get("日常收尾任务", {})
    assert "摇一摇" in daily_option.get("default_case", []), "摇一摇 应当加入日常收尾任务默认勾选项"
    case_names = [c.get("name") for c in daily_option.get("cases", [])]
    assert "摇一摇" in case_names, "日常收尾任务 cases 中应当包含 摇一摇"


# =====================================================================
# H. 3 局循环与体力耗尽流转测试
# =====================================================================
def test_shake_game_three_rounds_lifecycle():
    """测试 3 局循环状态机: 第 1~2 局 NEXT_ROUND，第 3 局 DONE"""
    from agent.runtime_state import daily_routine_state

    init_action = my_action.ShakeGameInitAction()
    init_action.run(MagicMock(), MagicMock())
    assert shake_game_state["completed_rounds"] == 0
    assert shake_game_state["max_rounds"] == 3
    assert shake_game_state["status"] == "IDLE"

    repeat_reco = my_reco.CheckShakeGameRepeatReco()

    # 第 1 局结束
    st1 = my_action._complete_shake_game_round()
    assert st1 == "NEXT_ROUND"
    assert shake_game_state["completed_rounds"] == 1
    assert repeat_reco.analyze(MagicMock(), MagicMock()) is not None

    # 第 2 局结束
    st2 = my_action._complete_shake_game_round()
    assert st2 == "NEXT_ROUND"
    assert shake_game_state["completed_rounds"] == 2
    assert repeat_reco.analyze(MagicMock(), MagicMock()) is not None

    # 第 3 局结束
    st3 = my_action._complete_shake_game_round()
    assert st3 == "DONE"
    assert shake_game_state["completed_rounds"] == 3
    assert repeat_reco.analyze(MagicMock(), MagicMock()) is None

    # 验证 DoneAction 推进日常收尾
    daily_routine_state["active"] = True
    daily_routine_state["tasks"] = {"ShakeGame": {"status": "IDLE"}}
    daily_routine_state["queue"] = ["NEXT_TASK"]
    daily_routine_state["step"] = "SHAKE_GAME"

    done_action = my_action.ShakeGameDoneAction()
    assert done_action.run(MagicMock(), MagicMock()) is True
    assert daily_routine_state["tasks"]["ShakeGame"]["status"] == "DONE"
    assert daily_routine_state["step"] == "NEXT_TASK"
    daily_routine_state["active"] = False


def test_shake_game_no_stamina_handling():
    """测试体力耗尽 (NO_STAMINA) 时跳过游玩并正确推进日常收尾"""
    from agent.runtime_state import daily_routine_state

    shake_game_state["status"] = "NO_STAMINA"
    play_reco = my_reco.CheckShakeGameCanPlayReco()
    assert play_reco.analyze(MagicMock(), MagicMock()) is None, "NO_STAMINA 时 CheckShakeGameCanPlayReco 必须返回 None"

    daily_routine_state["active"] = True
    daily_routine_state["tasks"] = {"ShakeGame": {"status": "IDLE"}}
    daily_routine_state["queue"] = ["NEXT_TASK"]
    daily_routine_state["step"] = "SHAKE_GAME"

    done_action = my_action.ShakeGameDoneAction()
    assert done_action.run(MagicMock(), MagicMock()) is True
    assert daily_routine_state["tasks"]["ShakeGame"]["status"] == "NO_STAMINA"
    assert daily_routine_state["step"] == "NEXT_TASK"
    daily_routine_state["active"] = False



if __name__ == "__main__":
    print("[RUN] Running test_controller_info_parsing_normal...")
    test_controller_info_parsing_normal()
    print("[PASS] test_controller_info_parsing_normal")

    print("[RUN] Running test_controller_info_parsing_adb_fallback...")
    test_controller_info_parsing_adb_fallback()
    print("[PASS] test_controller_info_parsing_adb_fallback")

    print("[RUN] Running test_vm_index_missing_strict_none...")
    test_vm_index_missing_strict_none()
    print("[PASS] test_vm_index_missing_strict_none")

    print("[RUN] Running test_subprocess_command_format...")
    test_subprocess_command_format()
    print("[PASS] test_subprocess_command_format")

    print("[RUN] Running test_mumu_shake_returns...")
    test_mumu_shake_returns()
    print("[PASS] test_mumu_shake_returns")

    print("[RUN] Running test_shake_game_play_action_settlement_detected...")
    test_shake_game_play_action_settlement_detected()
    print("[PASS] test_shake_game_play_action_settlement_detected")

    print("[RUN] Running test_shake_game_play_action_user_cancelled...")
    test_shake_game_play_action_user_cancelled()
    print("[PASS] test_shake_game_play_action_user_cancelled")

    print("[RUN] Running test_shake_game_play_action_consecutive_failures_tripped...")
    test_shake_game_play_action_consecutive_failures_tripped()
    print("[PASS] test_shake_game_play_action_consecutive_failures_tripped")

    print("[RUN] Running test_shake_game_play_action_timeout_without_settlement...")
    test_shake_game_play_action_timeout_without_settlement()
    print("[PASS] test_shake_game_play_action_timeout_without_settlement")

    print("[RUN] Running test_pipeline_contract_and_agent_registration...")
    test_pipeline_contract_and_agent_registration()
    print("[PASS] test_pipeline_contract_and_agent_registration")

    print("[RUN] Running test_interface_json_contract...")
    test_interface_json_contract()
    print("[PASS] test_interface_json_contract")

    print("[RUN] Running test_shake_game_three_rounds_lifecycle...")
    test_shake_game_three_rounds_lifecycle()
    print("[PASS] test_shake_game_three_rounds_lifecycle")

    print("[RUN] Running test_shake_game_no_stamina_handling...")
    test_shake_game_no_stamina_handling()
    print("[PASS] test_shake_game_no_stamina_handling")

    print("[RUN] Running test_shake_game_standalone_and_daily_routine_exit_routing...")
    test_shake_game_standalone_and_daily_routine_exit_routing()
    print("[PASS] test_shake_game_standalone_and_daily_routine_exit_routing")

    print("\nALL SHAKE GAME TESTS PASSED 100%!")
