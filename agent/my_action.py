import json
import math
import time
import traceback
from datetime import datetime, timedelta

import cv2
import numpy as np

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

try:
    from runtime_state import friend_gem_state, sea_otter_gem_state, band_fish_state, BAND_FISH_TARGETS, romantic_house_state
except ImportError:
    from agent.runtime_state import friend_gem_state, sea_otter_gem_state, band_fish_state, BAND_FISH_TARGETS, romantic_house_state

try:
    from param_utils import parse_dict_param, safe_float, safe_int
except ImportError:
    from agent.param_utils import parse_dict_param, safe_float, safe_int


@AgentServer.custom_action("CalcFishingFoodAction")
class CalcFishingFoodAction(CustomAction):

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        try:
            param = parse_dict_param(argv.custom_action_param)

            capacity = safe_float(param.get("capacity"), 100.0)
            current_duration = safe_float(param.get("current_duration"), 120.0)
            target_hour = safe_int(param.get("target_hour"), 8)

            now = datetime.now()
            target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)

            diff_minutes = (target_time - now).total_seconds() / 60.0
            total_hours = diff_minutes / 60.0

            extra_mins = max(0.0, diff_minutes - current_duration)

            if current_duration <= 0:
                extra_food = 0
                ui_msg = f"[鱼食预算] 计划挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮为0，请及时为海星喂食！"
            elif extra_mins <= 0:
                extra_food = 0
                bags = 0
                ui_msg = f"[鱼食预算] 计划挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮充足(剩余 {int(current_duration)} 分钟)，无需补充"
            else:
                rate_per_min = capacity / current_duration
                extra_food = int(round(extra_mins * rate_per_min + 0.4999))
                bags = math.ceil(extra_food / 30.0)
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 缺口 {int(extra_mins)}分钟 | 需备鱼食: {extra_food}粒 (约 {bags}袋)"

            print("=" * 55, flush=True)
            print("[鱼食预算] 海星挂机鱼食规划结果:", flush=True)
            print(f"[鱼食预算] 当前时间: {now.strftime('%H:%M')} | 计划挂机至: {target_time.strftime('%H:%M')} (共 {total_hours:.1f} 小时)", flush=True)
            print(f"[鱼食预算] 当前存粮可用: {int(current_duration)} 分钟 | 缺口时长: {max(0, int(extra_mins))} 分钟", flush=True)
            print(f"[鱼食预算] 至少需额外准备/购买: {extra_food} 粒 ~= {bags} 袋 (30粒/袋)", flush=True)
            print(f"[鱼食预算] 请确保背包备足鱼食, 海星将按设定间隔自动补充", flush=True)
            print("=" * 55, flush=True)

            try:
                context.override_pipeline({
                    "LogFoodBudget": {
                        "focus": {
                            "Node.Action.Succeeded": ui_msg
                        }
                    }
                })
            except Exception:
                pass

            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[鱼食预算] 计算异常: {e}", flush=True)
            return False


@AgentServer.custom_action("InitFriendGemStateAction")
class InitFriendGemStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            friend_gem_state["attempts"] = 0
            friend_gem_state["current_friend_index"] = 1
            friend_gem_state["max_attempts"] = 30
            friend_gem_state["bubble_miss_count"] = 0
            friend_gem_state["max_bubble_misses"] = 12
            print("[好友摸宝] 任务初始化完成：当前好友序号设为 1（从启动位置起算），安全保护上限为 30，连续未见气泡容忍上限为 12", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[好友摸宝] 初始化异常: {e}", flush=True)
            return False


@AgentServer.custom_action("RecordFriendGemAttemptAction")
class RecordFriendGemAttemptAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            friend_gem_state["attempts"] = int(friend_gem_state.get("attempts", 0)) + 1
            friend_gem_state["bubble_miss_count"] = 0
            attempts = friend_gem_state["attempts"]
            max_att = friend_gem_state.get("max_attempts", 30)
            cur_idx = friend_gem_state.get("current_friend_index", 1)
            print(f"[好友摸宝] 已尝试采集气泡次数: {attempts}/{max_att} (当前好友序号: {cur_idx})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[好友摸宝] 记录尝试异常: {e}", flush=True)
            return False


@AgentServer.custom_action("StepFriendGemIndexAction")
class StepFriendGemIndexAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            friend_gem_state["current_friend_index"] = int(friend_gem_state.get("current_friend_index", 1)) + 1
            friend_gem_state["bubble_miss_count"] = 0
            cur_idx = friend_gem_state["current_friend_index"]
            print(f"[好友摸宝] 切换至下一位好友，当前好友序号前进至: {cur_idx}", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[好友摸宝] 步进序号异常: {e}", flush=True)
            return False


@AgentServer.custom_action("ResetFriendGemAttemptsAction")
class ResetFriendGemAttemptsAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            friend_gem_state["attempts"] = 0
            friend_gem_state["bubble_miss_count"] = 0
            cur_idx = friend_gem_state.get("current_friend_index", 1)
            print(f"[好友摸宝] 进入新好友水族箱 (序号: {cur_idx})，气泡尝试次数重置为 0", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[好友摸宝] 重置尝试异常: {e}", flush=True)
            return False


@AgentServer.custom_action("RecordFriendGemBubbleMissAction")
class RecordFriendGemBubbleMissAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            friend_gem_state["bubble_miss_count"] = int(friend_gem_state.get("bubble_miss_count", 0)) + 1
            miss = friend_gem_state["bubble_miss_count"]
            max_misses = friend_gem_state.get("max_bubble_misses", 12)
            print(f"[好友摸宝] 暂未发现气泡 ({miss}/{max_misses})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[好友摸宝] 记录气泡漏检异常: {e}", flush=True)
            return False


def detect_bite_color_geo_strict(crop: np.ndarray):
    """
    钓鱼感叹号强几何特征检测器:
    基于 HSV 高饱和鲜红 + 上半竖条/下半方点双连通域垂直对齐约束
    """
    if crop is None or getattr(crop, "size", 0) == 0:
        return False, None

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, np.array([0, 140, 140]), np.array([10, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([170, 140, 140]), np.array([180, 255, 255]))
    mask = mask1 | mask2

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bars = []
    dots = []

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = float(cv2.contourArea(c))
        if area < 20:
            continue
        aspect = h / float(w)
        if 30 <= h <= 95 and 8 <= w <= 40 and 1.6 <= aspect <= 5.5:
            bars.append((x, y, w, h, area))
        elif 10 <= h <= 45 and 8 <= w <= 40 and 0.5 <= aspect <= 1.8:
            dots.append((x, y, w, h, area))

    for bx, by, bw, bh, barea in bars:
        for dx, dy, dw, dh, darea in dots:
            b_cx = bx + bw / 2.0
            d_cx = dx + dw / 2.0
            gap = dy - (by + bh)
            if abs(b_cx - d_cx) <= 18 and 1 <= gap <= 35:
                return True, {"bar": (bx, by, bw, bh), "dot": (dx, dy, dw, dh)}

    return False, None


fishing_state = {
    "current_task_id": None,
    "cast_count": 0,
    "max_casts": 5,
    "fish_caught": 0,
}


def _sync_task_id(task_id: int):
    if fishing_state["current_task_id"] != task_id:
        print(f"[钓鱼达人] 检测到新任务 ID ({task_id})，重置 cast_count=0 (上一任务 ID: {fishing_state['current_task_id']})", flush=True)
        fishing_state["current_task_id"] = task_id
        fishing_state["cast_count"] = 0


def _watch_bite_and_reel(ctrl, roi, btn_x, btn_y, timeout_sec, t_start) -> bool:
    """
    通用咬钩高速监听与收杆触控内核:
    支持 Controller 容错、异常捕获、帧越界裁剪与安全退出。
    """
    time_limit = time.perf_counter() + timeout_sec
    hit_found = False
    frames_count = 0

    while time.perf_counter() < time_limit:
        try:
            job_cap = ctrl.post_screencap()
            if not job_cap:
                print("[钓鱼达人QTE] 错误: post_screencap 返回空任务", flush=True)
                return False
            job_cap.wait()
            frame = job_cap.get()
        except Exception as e:
            print(f"[钓鱼达人QTE] 截屏异常: {e}", flush=True)
            return False

        if frame is None or getattr(frame, "size", 0) == 0:
            time.sleep(0.01)
            continue

        frames_count += 1

        # 安全 ROI 边界裁剪
        img_h, img_w = frame.shape[:2]
        rx = max(0, min(img_w - 1, roi[0]))
        ry = max(0, min(img_h - 1, roi[1]))
        rw = max(1, min(img_w - rx, roi[2]))
        rh = max(1, min(img_h - ry, roi[3]))
        crop = frame[ry:ry+rh, rx:rx+rw]

        try:
            hit, _ = detect_bite_color_geo_strict(crop)
        except Exception as e:
            print(f"[钓鱼达人QTE] 检测异常: {e}", flush=True)
            return False

        if hit and not hit_found:
            t_hit = time.perf_counter()
            hit_found = True
            print(f"[钓鱼达人QTE] 检测到咬钩感叹号！等待时长: {(t_hit - t_start):.3f}s，立即收杆！", flush=True)
            try:
                job_down = ctrl.post_touch_down(btn_x, btn_y)
                if job_down: job_down.wait()
                time.sleep(0.04)
                job_up = ctrl.post_touch_up(0)
                if job_up: job_up.wait()
            except Exception as e:
                print(f"[钓鱼达人QTE] 收杆触控下发异常: {e}", flush=True)
                return False

            t_clicked = time.perf_counter()
            print(f"[钓鱼达人QTE] 收杆指令已完成 (耗时 {(t_clicked - t_hit)*1000:.1f}ms)，等待转场退出...", flush=True)
            time_limit = min(time_limit, time.perf_counter() + 1.2)

    if hit_found:
        print(f"[钓鱼达人QTE] 动作成功完成 (共抓帧 {frames_count} 帧)，交回 Pipeline 确认结算页面", flush=True)
        return True
    else:
        print(f"[钓鱼达人QTE] 等待超时 ({timeout_sec:.1f}s 未检出咬钩)，安全退出", flush=True)
        return False


@AgentServer.custom_action("FishingCastAndBiteQTEAction")
class FishingCastAndBiteQTEAction(CustomAction):
    """
    钓鱼达人 QTE 自动甩收杆自定义动作:
    1. 严格上限保护: 检查 max_casts=5 硬限制；
    2. 执行单次甩杆 (保持 60ms 触控确保模拟器触发)；
    3. 调用原生截屏 (~55 FPS) + 轻量 Color+Geometry 检测 (~1ms)；
    4. 首次命中感叹号即刻下发固定坐标收杆点击，控制权交还 Pipeline。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            task_detail = getattr(argv, "task_detail", None)
            if task_detail and hasattr(task_detail, "task_id"):
                _sync_task_id(int(task_detail.task_id))

            param = parse_dict_param(getattr(argv, "custom_action_param", None))

            timeout_sec = safe_float(param.get("timeout"), 30.0, min_val=1.0, max_val=120.0)
            raw_roi = param.get("roi")
            if isinstance(raw_roi, list) and len(raw_roi) == 4:
                roi = [safe_int(x, 0) for x in raw_roi]
            else:
                roi = [380, 260, 480, 300]
            btn_x = safe_int(param.get("btn_x"), 1134)
            btn_y = safe_int(param.get("btn_y"), 578)

            if fishing_state["cast_count"] >= fishing_state["max_casts"]:
                print(f"[钓鱼达人QTE] 拦截: 已达最大施放次数上限 ({fishing_state['cast_count']}/{fishing_state['max_casts']})，安全停止", flush=True)
                return False

            ctrl = context.tasker.controller
            if not ctrl:
                print("[钓鱼达人QTE] 错误: 未获取到 Controller", flush=True)
                return False

            # 执行单次甩杆
            print(f"[钓鱼达人QTE] 发送甩杆指令 ({btn_x}, {btn_y})...", flush=True)
            t_cast_start = time.perf_counter()
            try:
                job_down = ctrl.post_touch_down(btn_x, btn_y)
                if job_down: job_down.wait()
                time.sleep(0.06)
                job_up = ctrl.post_touch_up(0)
                if job_up: job_up.wait()
            except Exception as e:
                print(f"[钓鱼达人QTE] 甩杆触控异常: {e}", flush=True)
                return False

            fishing_state["cast_count"] += 1
            t_cast_done = time.perf_counter()
            print(f"[钓鱼达人QTE] 甩杆已完成 (当前第 {fishing_state['cast_count']}/{fishing_state['max_casts']} 次，耗时 {(t_cast_done - t_cast_start)*1000:.1f}ms)，进入高速抓帧监听...", flush=True)

            return _watch_bite_and_reel(ctrl, roi, btn_x, btn_y, timeout_sec, t_cast_done)
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼达人QTE] 运行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("FishingWatchBiteOnlyAction")
class FishingWatchBiteOnlyAction(CustomAction):
    """
    中途恢复专用: 当任务启动时游戏已处于甩杆等待中（右下角显示「收杆」），
    不执行二次甩杆，直接进入高速咬钩监听并在首次命中时收杆。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            task_detail = getattr(argv, "task_detail", None)
            if task_detail and hasattr(task_detail, "task_id"):
                _sync_task_id(int(task_detail.task_id))

            param = parse_dict_param(getattr(argv, "custom_action_param", None))

            timeout_sec = safe_float(param.get("timeout"), 30.0, min_val=1.0, max_val=120.0)
            raw_roi = param.get("roi")
            if isinstance(raw_roi, list) and len(raw_roi) == 4:
                roi = [safe_int(x, 0) for x in raw_roi]
            else:
                roi = [380, 260, 480, 300]
            btn_x = safe_int(param.get("btn_x"), 1134)
            btn_y = safe_int(param.get("btn_y"), 578)

            ctrl = context.tasker.controller
            if not ctrl:
                print("[钓鱼达人中途恢复] 错误: 未获取到 Controller", flush=True)
                return False

            print(f"[钓鱼达人中途恢复] 检测到画面已在等待咬钩中（收杆状态），不重复甩杆，直接进入高速抓帧监听...", flush=True)
            return _watch_bite_and_reel(ctrl, roi, btn_x, btn_y, timeout_sec, time.perf_counter())
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼达人中途恢复] 运行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("ResetFishingStateAction")
class ResetFishingStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            task_detail = getattr(argv, "task_detail", None)
            task_id = int(task_detail.task_id) if task_detail and hasattr(task_detail, "task_id") else None
            fishing_state["current_task_id"] = task_id
            fishing_state["cast_count"] = 0
            fishing_state["fish_caught"] = 0
            print(f"[钓鱼达人] 状态已重置: cast_count=0 (task_id: {task_id})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼达人] 重置状态异常: {e}", flush=True)
            return False


@AgentServer.custom_action("InitSeaOtterStateAction")
class InitSeaOtterStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            task_detail = getattr(argv, "task_detail", None)
            task_id = int(task_detail.task_id) if task_detail and hasattr(task_detail, "task_id") else None
            sea_otter_gem_state["current_task_id"] = task_id
            sea_otter_gem_state["current_side"] = "left"
            sea_otter_gem_state["total_harvests"] = 0
            sea_otter_gem_state["consecutive_exhausted"] = 0
            print(f"[海獭摸宝] 状态已重置: side=LEFT, harvests=0 (task_id: {task_id})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海獭摸宝] 重置状态异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SeaOtterHarvestAction")
class SeaOtterHarvestAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[海獭摸宝] 错误: 未获取到 Controller", flush=True)
                return False

            side = sea_otter_gem_state.get("current_side", "left")

            # 1. 点击左下角海獭安全本体 (85, 565)
            ctrl.post_touch_down(85, 565).wait()
            time.sleep(0.08)
            ctrl.post_touch_up(0).wait()

            sea_otter_gem_state["total_harvests"] += 1
            sea_otter_gem_state["consecutive_exhausted"] = 0
            cur = sea_otter_gem_state["total_harvests"]
            limit = sea_otter_gem_state["max_harvests"]

            time.sleep(0.8)

            # 2. 依据当前 side 决定下一步导航
            if side == "left":
                print(f"[SeaOtter] side=LEFT ui=HARVESTABLE action=HARVEST_THEN_NEXT (累计摸宝: {cur}/{limit})", flush=True)
                ctrl.post_click(1205, 68).wait()
                sea_otter_gem_state["current_side"] = "right"
            else:
                print(f"[SeaOtter] side=RIGHT ui=HARVESTABLE action=HARVEST_THEN_PREV (累计摸宝: {cur}/{limit})", flush=True)
                ctrl.post_click(1085, 68).wait()
                sea_otter_gem_state["current_side"] = "left"

            time.sleep(2.0)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海獭摸宝] 摸宝动作异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SeaOtterAdvancePairAction")
class SeaOtterAdvancePairAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[海獭摸宝] 错误: 未获取到 Controller", flush=True)
                return False

            side = sea_otter_gem_state.get("current_side", "left")

            if side == "left":
                # LEFT + Exhausted -> 不摸 -> Next -> side = LEFT (新好友被视作新 LEFT)
                sea_otter_gem_state["consecutive_exhausted"] += 1
                consec = sea_otter_gem_state["consecutive_exhausted"]
                print(f"[SeaOtter] side=LEFT ui=EXHAUSTED action=ADVANCE_WINDOW_NEXT (连续耗尽: {consec})", flush=True)
                ctrl.post_click(1205, 68).wait()
                sea_otter_gem_state["current_side"] = "left"
            else:
                # RIGHT + Exhausted -> 不摸 -> Prev -> side = LEFT (跳板返回 LEFT 重新进入)
                print(f"[SeaOtter] side=RIGHT ui=EXHAUSTED action=PREV_AS_REFRESH_BRIDGE", flush=True)
                ctrl.post_click(1085, 68).wait()
                sea_otter_gem_state["current_side"] = "left"

            time.sleep(2.0)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海獭摸宝] 耗尽处理异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SeaOtterSwitchPairAction")
class SeaOtterSwitchPairAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # 已合流至 SeaOtterHarvestAction，保持幂等兼容
        return True


@AgentServer.custom_action("InitBandFishStateAction")
class InitBandFishStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            band_fish_state["status"] = None
            band_fish_state["invited_slots"] = []
            band_fish_state["performance_finished"] = False
            print("[乐队鱼] 状态已初始化，开始执行 BandFishTask", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼] 初始化状态异常: {e}", flush=True)
            return False


@AgentServer.custom_action("LogBandFishStatusAction")
class LogBandFishStatusAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(argv.custom_action_param)
            status = param.get("status", "UNKNOWN")
            band_fish_state["status"] = status
            if status == "DONE":
                band_fish_state["performance_finished"] = True
                print("[乐队鱼] 状态识别: 今日演出已完成(返场演出/次数已达上限)，安全退出", flush=True)
            elif status == "READY_TO_PERFORM":
                print("[乐队鱼] 状态识别: 乐队就绪，可开始演出", flush=True)
            elif status == "NEED_INVITE":
                print("[乐队鱼] 状态识别: 存在空缺或待邀请槽位", flush=True)
            else:
                print(f"[乐队鱼] 状态识别: {status}", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼] 记录状态异常: {e}", flush=True)
            return False


SLOT_INVITE_COORDS = {
    1: (280, 418),
    2: (450, 470),
    4: (833, 470),
    5: (1025, 418),
}


@AgentServer.custom_action("BandFishScanSlotsAction")
class BandFishScanSlotsAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[乐队鱼] 错误: 未获取到 Controller", flush=True)
                return False

            job_cap = ctrl.post_screencap()
            if job_cap:
                job_cap.wait()
                frame = job_cap.get()
            else:
                frame = None

            if frame is None or getattr(frame, "size", 0) == 0:
                print("[乐队鱼] 截屏获取失败", flush=True)
                return False

            # 扫描每个槽位状态
            for slot, target_name in BAND_FISH_TARGETS.items():
                cur_state = band_fish_state.get("slots", {}).get(slot, {}).get("state", "EMPTY")

                # 1. 检查是否已有对应目标好友名（已接受）
                reco_name = f"BandFishSlot{slot}Accepted"
                res_name = context.run_recognition(reco_name, frame)
                if res_name and res_name.hit:
                    band_fish_state["slots"][slot]["state"] = "ACCEPTED"
                    print(f"[乐队鱼] 槽位 {slot} 状态: ACCEPTED (已加入: {target_name})", flush=True)
                    continue

                # 2. 检查是否处于倒计时（已邀请）
                reco_timer = f"BandFishSlot{slot}Timer"
                res_timer = context.run_recognition(reco_timer, frame)
                if res_timer and res_timer.hit:
                    band_fish_state["slots"][slot]["state"] = "INVITED"
                    print(f"[乐队鱼] 槽位 {slot} 状态: INVITED (等待接受倒计时中: {target_name})", flush=True)
                    continue

                # 3. 检查是否有“邀请”按钮（空缺）
                reco_invite = f"BandFishSlot{slot}InviteBtn"
                res_invite = context.run_recognition(reco_invite, frame)
                if res_invite and res_invite.hit:
                    band_fish_state["slots"][slot]["state"] = "EMPTY"
                    print(f"[乐队鱼] 槽位 {slot} 状态: EMPTY (待邀请: {target_name})", flush=True)
                    continue

                # 保留上一有效状态
                print(f"[乐队鱼] 槽位 {slot} 状态保持: {cur_state} ({target_name})", flush=True)

            # 评估整体就绪状态
            all_accepted = all(
                band_fish_state.get("slots", {}).get(s, {}).get("state") == "ACCEPTED"
                for s in (1, 2, 4, 5)
            )
            has_empty = any(
                band_fish_state.get("slots", {}).get(s, {}).get("state") == "EMPTY"
                for s in (1, 2, 4, 5)
            )

            if all_accepted:
                band_fish_state["status"] = "READY_TO_PERFORM"
                print("[乐队鱼] 4位好友已全部就绪 (READY_TO_PERFORM)", flush=True)
            elif has_empty:
                band_fish_state["status"] = "NEED_INVITE"
                print("[乐队鱼] 存在空缺槽位，需要发起邀请", flush=True)
            else:
                band_fish_state["status"] = "WAITING_ACCEPT"
                print("[乐队鱼] 邀请已发出，等待好友接受中，需刷新状态", flush=True)

            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼] 扫描槽位异常: {e}", flush=True)
            return False


@AgentServer.custom_action("BandFishInviteSlotAction")
class BandFishInviteSlotAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[乐队鱼] 错误: 未获取到 Controller", flush=True)
                return False

            param = parse_dict_param(argv.custom_action_param)
            slot = safe_int(param.get("slot"), 1)
            target_name = BAND_FISH_TARGETS.get(slot)
            if not target_name:
                print(f"[乐队鱼] 错误: 槽位 {slot} 无目标好友映射", flush=True)
                return False

            cur_state = band_fish_state.get("slots", {}).get(slot, {}).get("state")
            if cur_state in ("INVITED", "ACCEPTED"):
                print(f"[乐队鱼] 槽位 {slot} 已处于 {cur_state}，跳过邀请", flush=True)
                return True

            btn_x, btn_y = SLOT_INVITE_COORDS.get(slot, (280, 418))
            print(f"[乐队鱼] 开始邀请槽位 {slot}: 目标【{target_name}】，点击槽位邀请按钮 ({btn_x}, {btn_y})...", flush=True)

            # 1. 点击槽位邀请按钮进入选择弹窗
            ctrl.post_click(btn_x, btn_y).wait()
            time.sleep(1.8)

            # 2. 点击搜索输入框 (450, 128)
            print("[乐队鱼] 点击搜索输入框 (450, 128)...", flush=True)
            ctrl.post_click(450, 128).wait()
            time.sleep(0.4)

            # 清空旧输入内容 (连续 12 次 Backspace)
            for _ in range(12):
                ctrl.post_click_key(67)
            time.sleep(0.3)

            # 3. 输入目标好友名字
            print(f"[乐队鱼] 输入目标好友名称: 【{target_name}】...", flush=True)
            ctrl.post_input_text(target_name).wait()
            time.sleep(0.5)

            # 4. 点击绿色搜索按钮 (589, 128)
            print("[乐队鱼] 点击搜索按钮 (589, 128)...", flush=True)
            ctrl.post_click(589, 128).wait()
            time.sleep(1.5)

            # 5. 截屏并 OCR 定位目标卡片
            job_cap = ctrl.post_screencap()
            if job_cap:
                job_cap.wait()
                frame_before = job_cap.get()
            else:
                frame_before = None

            if frame_before is None or getattr(frame_before, "size", 0) == 0:
                print("[乐队鱼] 搜索后截屏失败", flush=True)
                return False

            # 使用动态 expected 进行目标定位
            res_card = context.run_recognition(
                "BandFishFriendCardTarget",
                frame_before,
                pipeline_override={"BandFishFriendCardTarget": {"expected": target_name}}
            )

            if not res_card or not res_card.hit:
                # 尝试模糊关键词匹配
                kw = target_name[:2] if len(target_name) > 2 else target_name
                res_card = context.run_recognition(
                    "BandFishFriendCardTarget",
                    frame_before,
                    pipeline_override={"BandFishFriendCardTarget": {"expected": kw}}
                )

            if not res_card or not res_card.hit:
                print(f"[乐队鱼] 严重警告: 搜索结果中未找到目标好友【{target_name}】，安全放弃点击，退出弹窗", flush=True)
                ctrl.post_click(66, 48).wait()
                time.sleep(1.0)
                return False

            # 取得中心坐标
            bx, by, bw, bh = res_card.box
            cx, cy = bx + bw // 2, by + bh // 2
            print(f"[乐队鱼] 成功定位目标好友【{target_name}】: box=({bx}, {by}, {bw}, {bh}), 点击中心=({cx}, {cy})", flush=True)

            # 6. 防误触闭环：点击前已有 frame_before，执行点击
            ctrl.post_click(cx, cy).wait()
            time.sleep(0.6)

            # 截取点击后画面，核验卡片高亮选中状态 (Diff 校验)
            job_cap_after = ctrl.post_screencap()
            if job_cap_after:
                job_cap_after.wait()
                frame_after = job_cap_after.get()
            else:
                frame_after = None

            if frame_after is not None:
                img_h, img_w = frame_after.shape[:2]
                rx = max(0, bx - 30)
                ry = max(0, by - 30)
                rw = min(img_w - rx, bw + 60)
                rh = min(img_h - ry, bh + 60)
                crop_b = frame_before[ry:ry+rh, rx:rx+rw]
                crop_a = frame_after[ry:ry+rh, rx:rx+rw]
                diff_px = int(np.sum(cv2.absdiff(crop_b, crop_a) > 25))
                print(f"[乐队鱼] 卡片选中 Diff 变化像素数: {diff_px}", flush=True)

            # 7. 确认底部“邀请”按钮并点击 (920, 668)
            ctrl.post_click(920, 668).wait()
            time.sleep(1.8)

            band_fish_state["slots"][slot]["state"] = "INVITED"
            print(f"[乐队鱼] 槽位 {slot} 已成功向【{target_name}】发出邀请！", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼] 邀请槽位 {slot} 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("BandFishRefreshStateAction")
class BandFishRefreshStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[乐队鱼] 错误: 未获取到 Controller", flush=True)
                return False

            print("[乐队鱼] 执行状态刷新闭环: 返回鱼缸 -> 重新进入活动页...", flush=True)

            # 1. 点击左上角返回按钮回到水族箱 (91, 46)
            ctrl.post_click(91, 46).wait()
            time.sleep(1.8)

            # 2. 点击水族箱左侧“游乐园” (55, 541)
            print("[乐队鱼] 点击水族箱游乐园图标 (55, 541)...", flush=True)
            ctrl.post_click(55, 541).wait()
            time.sleep(1.5)

            # 3. 点击游乐园面板中的“乐队鱼” (590, 455)
            print("[乐队鱼] 点击乐队鱼活动入口 (590, 455)...", flush=True)
            ctrl.post_click(590, 455).wait()
            time.sleep(2.0)

            print("[乐队鱼] 已重新进入“我的演出”，准备刷新判定槽位状态", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼] 刷新状态异常: {e}", flush=True)
            return False



