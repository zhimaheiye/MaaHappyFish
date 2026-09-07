import json
import math
import os
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional, Tuple

import cv2
import numpy as np

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

try:
    from runtime_state import (
        friend_gem_state,
        sea_otter_gem_state,
        band_fish_state,
        BAND_FISH_TARGETS,
        romantic_house_state,
        daily_routine_state,
        fishing_state,
        golden_dolphin_state,
    )
except ImportError:
    from agent.runtime_state import (
        friend_gem_state,
        sea_otter_gem_state,
        band_fish_state,
        BAND_FISH_TARGETS,
        romantic_house_state,
        daily_routine_state,
        fishing_state,
        golden_dolphin_state,
    )

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


def load_band_fish_skip_template() -> Optional[np.ndarray]:
    """
    加载乐队鱼“跳过”按钮模板图片。
    预留模板加载接口：若文件不存在或未配置，安全返回 None，绝不抛出异常。
    """
    try:
        template_path = os.path.join("assets", "resource", "image", "乐队鱼_跳过.png")
        if os.path.exists(template_path):
            return cv2.imread(template_path)
    except Exception as e:
        print(f"[乐队鱼演出] 加载跳过模板异常: {e}", flush=True)
    return None


def check_band_fish_skip_button(frame: Optional[np.ndarray]) -> Optional[Tuple[int, int]]:
    """
    检测乐队鱼演出界面的“跳过”按钮中心坐标 (x, y)。
    预留跳过按钮识别接口：若未识别到或模板不存在，安全返回 None。
    遵守动作前置状态确认与无盲点规则，严禁在未识别到模板时猜测固定坐标或盲点。
    """
    if frame is None:
        return None
    try:
        template = load_band_fish_skip_template()
        if template is None:
            return None

        # 预留模板匹配逻辑 (待后续实机采集 乐队鱼_跳过.png 样本后启用)
        # res = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        # min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        # if max_val >= 0.85:
        #     th, tw = template.shape[:2]
        #     return max_loc[0] + tw // 2, max_loc[1] + th // 2
    except Exception as e:
        print(f"[乐队鱼演出] 识别跳过按钮异常: {e}", flush=True)
    return None


@AgentServer.custom_action("BandFishPerformAction")
class BandFishPerformAction(CustomAction):
    """
    乐队鱼核心演出闭环动作 (Pass 2):
    职责分工:
    1. 开始演出: 识别或默认点击底部绿色“开始演出”按钮 (637, 630);
    2. 选曲确认: 动态等待“请选择您要演奏的乐章”选曲弹窗并点击右上角绿色【确定】(1023, 359) 消耗体力;
    3. 演出与跳过检测: 4 阶段状态机 (PLAYING -> WAIT_SKIP_BUTTON -> CLICK_SKIP -> WAIT_RESULT);
    4. 结算等待与领取: 等待“我的乐章”结算弹窗并点击【确定】按钮 (639, 680) 领取结算奖励;
    5. 状态沉淀: band_fish_state["status"] = "DONE", band_fish_state["performance_finished"] = True.
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[乐队鱼演出] 错误: 未获取到 Controller", flush=True)
                return False

            print("[乐队鱼演出] 检测到全员就绪，开始执行演出闭环流程...", flush=True)

            def capture_frame():
                job = ctrl.post_screencap()
                if not job:
                    return None
                job.wait()
                f = job.get()
                if f is not None:
                    fh, fw = f.shape[:2]
                    if fw != 1280 or fh != 720:
                        f = cv2.resize(f, (1280, 720))
                return f

            # 职责 1: 验证当前处于“开始演出”状态并点击
            f_init = capture_frame()
            btn_x, btn_y = 637, 630
            if f_init is not None and hasattr(context, "run_recognition"):
                res_ready = context.run_recognition("BandFishCheckReady", f_init)
                if res_ready and res_ready.hit:
                    bx, by, bw, bh = res_ready.box
                    btn_x, btn_y = bx + bw // 2, by + bh // 2
                    print(f"[乐队鱼演出] 识别到“开始演出”按钮中心: ({btn_x}, {btn_y})", flush=True)

            print(f"[乐队鱼演出] 点击【开始演出】按钮 ({btn_x}, {btn_y})...", flush=True)
            ctrl.post_click(btn_x, btn_y).wait()
            time.sleep(1.8)

            # 职责 2: 动态等待选曲弹窗打开并点击确定
            t_dlg = time.time()
            dlg_opened = False
            while time.time() - t_dlg < 5.0:
                f_dlg = capture_frame()
                if f_dlg is None:
                    time.sleep(0.3)
                    continue
                # 弹窗右上角“确定”按钮坐标约 (1023, 359)
                crop_ok = f_dlg[335:385, 980:1060]
                if crop_ok.size > 0:
                    hsv = cv2.cvtColor(crop_ok, cv2.COLOR_BGR2HSV)
                    mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))
                    if int(np.sum(mask > 0)) >= 100:
                        dlg_opened = True
                        break
                time.sleep(0.4)

            if dlg_opened:
                print("[乐队鱼演出] 选曲弹窗已打开，右上角【确定】按钮就绪", flush=True)
            else:
                print("[乐队鱼演出] 提示: 未检测到明显选曲弹窗绿色确定按钮，继续执行默认确定点击", flush=True)

            print("[乐队鱼演出] 点击乐章弹窗【确定】按钮 (1023, 359) 消耗体力开始演出...", flush=True)
            ctrl.post_click(1023, 359).wait()
            time.sleep(2.0)

            # 职责 3 & 4: 演出与跳过检测 (4 阶段状态机: PLAYING -> WAIT_SKIP_BUTTON -> CLICK_SKIP -> WAIT_RESULT)
            print("[乐队鱼演出] 演出已开始，进入演出动画等待与跳过/结算轮询 (最长等待 45s)...", flush=True)
            t_perf_start = time.time()
            t_skip_start = time.time()
            skip_window_sec = 6.0  # 前置跳过探测时间窗口
            settlement_detected = False
            confirm_settle_x, confirm_settle_y = 639, 680
            skip_x, skip_y = None, None

            stage = "PLAYING"
            print(f"[乐队鱼演出] 状态流转: 进入演出阶段 ({stage})", flush=True)
            stage = "WAIT_SKIP_BUTTON"
            print(f"[乐队鱼演出] 状态流转: PLAYING -> WAIT_SKIP_BUTTON (开始检测跳过按钮)", flush=True)

            while time.time() - t_perf_start < 45.0:
                time.sleep(1.5)
                f_cur = capture_frame()
                if f_cur is None:
                    continue

                if stage == "WAIT_SKIP_BUTTON":
                    skip_pos = check_band_fish_skip_button(f_cur)
                    if skip_pos is not None:
                        skip_x, skip_y = skip_pos
                        print(f"[乐队鱼演出] 检测到跳过按钮坐标: ({skip_x}, {skip_y})，状态流转: WAIT_SKIP_BUTTON -> CLICK_SKIP", flush=True)
                        stage = "CLICK_SKIP"
                    else:
                        # 检查是否已直接出现结算特征（防跳过窗口内演出已直接完成）
                        crop_confirm = f_cur[650:700, 595:685]
                        has_confirm = False
                        if crop_confirm.size > 0:
                            hsv_c = cv2.cvtColor(crop_confirm, cv2.COLOR_BGR2HSV)
                            mask_c = cv2.inRange(hsv_c, np.array([35, 80, 80]), np.array([85, 255, 255]))
                            if int(np.sum(mask_c > 0)) >= 150:
                                has_confirm = True

                        has_done = False
                        if hasattr(context, "run_recognition"):
                            res_done = context.run_recognition("BandFishCheckDone", f_cur)
                            if res_done and res_done.hit:
                                has_done = True

                        if has_confirm or has_done:
                            print("[乐队鱼演出] 检测到结算弹窗或演出已自然结束，状态流转: WAIT_SKIP_BUTTON -> WAIT_RESULT", flush=True)
                            settlement_detected = True
                            if has_done and not has_confirm:
                                confirm_settle_x = None
                            stage = "WAIT_RESULT"
                            break

                        if time.time() - t_skip_start >= skip_window_sec:
                            print("[乐队鱼演出] 跳过探测窗口结束 (未检测到跳过按钮或无需跳过)，状态流转: WAIT_SKIP_BUTTON -> WAIT_RESULT (进入结算等待)", flush=True)
                            stage = "WAIT_RESULT"

                if stage == "CLICK_SKIP":
                    if skip_x is not None and skip_y is not None:
                        print(f"[乐队鱼演出] 执行跳过点击 ({skip_x}, {skip_y})...", flush=True)
                        ctrl.post_click(skip_x, skip_y).wait()
                        time.sleep(1.0)
                    print("[乐队鱼演出] 点击跳过按钮完成，状态流转: CLICK_SKIP -> WAIT_RESULT (进入结算等待)", flush=True)
                    stage = "WAIT_RESULT"
                    continue

                if stage == "WAIT_RESULT":
                    # 检测结算弹窗底部绿色【确定】按钮 [580, 640, 120, 60]
                    crop_confirm = f_cur[650:700, 595:685]
                    if crop_confirm.size > 0:
                        hsv_c = cv2.cvtColor(crop_confirm, cv2.COLOR_BGR2HSV)
                        mask_c = cv2.inRange(hsv_c, np.array([35, 80, 80]), np.array([85, 255, 255]))
                        if int(np.sum(mask_c > 0)) >= 150:
                            settlement_detected = True
                            print("[乐队鱼演出] 检测到结算弹窗底部【确定】按钮！", flush=True)
                            break

                    # 辅助检查：如果已经返回“返场演出”页面，说明演出已自然结束
                    if hasattr(context, "run_recognition"):
                        res_done = context.run_recognition("BandFishCheckDone", f_cur)
                        if res_done and res_done.hit:
                            print("[乐队鱼演出] 画面已直接显示“返场演出”，演出已自动完成！", flush=True)
                            settlement_detected = True
                            confirm_settle_x = None  # 无需再点结算
                            break

            # 职责 4: 领取结算奖励
            if settlement_detected and confirm_settle_x is not None:
                print(f"[乐队鱼演出] 点击结算弹窗【确定】按钮 ({confirm_settle_x}, {confirm_settle_y}) 领取奖励...", flush=True)
                ctrl.post_click(confirm_settle_x, confirm_settle_y).wait()
                time.sleep(2.0)
            else:
                print("[乐队鱼演出] 演奏动画周期结束，保底点击中央结算区域并等待刷新...", flush=True)
                ctrl.post_click(639, 680).wait()
                time.sleep(1.5)

            # 职责 5: 沉淀完成状态
            band_fish_state["status"] = "DONE"
            band_fish_state["performance_finished"] = True
            print("[乐队鱼演出] 演出完整闭环执行完毕，状态已沉淀: DONE (performance_finished=True)", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼演出] 执行演出异常: {e}", flush=True)
            return False


SLOT_INVITE_COORDS = {
    1: (280, 418),
    2: (450, 470),
    4: (833, 470),
    5: (1025, 418),
}

SLOT_INVITE_INFO = {
    1: {"roi": (200, 385, 160, 65), "click": (280, 418)},
    2: {"roi": (380, 440, 150, 65), "click": (450, 470)},
    4: {"roi": (760, 440, 150, 65), "click": (833, 470)},
    5: {"roi": (950, 385, 160, 65), "click": (1025, 418)},
}



@AgentServer.custom_action("BandFishInviteLoopAction")
class BandFishInviteLoopAction(CustomAction):
    """
    乐队鱼动态全槽位邀请闭环动作 (基于纯列表 OCR 方案，严格绑定指定人机好友并执行名字识别与防误触核验):
    1. 动态扫描所有槽位 (1, 2, 4, 5)，检测是否存在绿色“邀请”按钮;
    2. 若存在空缺槽位 target_slot，获取对应指定人机好友名字 target_name:
       - 槽位 1 -> 不想上课
       - 槽位 2 -> 一只胖梨
       - 槽位 4 -> 扶摇
       - 槽位 5 -> 游来游去
    3. 点击对应槽位的“邀请”按钮，进入好友选择弹窗;
    4. 动态等待好友选择弹窗打开;
    5. 纯列表 OCR 匹配目标好友:
       a. 对当前页面执行 OCR，提取好友卡片名字，与 target_name 进行精确匹配;
       b. 若当前屏未检出，向上滑动列表继续检索 (最多滑动 2 次，严禁使用搜索框);
       c. 熔断防线: 若列表 OCR 遍历后仍未匹配到目标好友，立即安全熔断，点击左上角返回 (91, 46) 放弃，绝不误触/随机选择任何非目标好友！
    6. 点击目标好友卡片文字中心 (cx, cy);
    7. 选中与安全门禁核验:
       - 动态等待底部确认邀请按钮变为绿色 (is_confirm_green);
       - 若未变绿或选中异常，点击返回安全退出;
    8. 门禁通过后，点击底部绿色确认邀请按钮 (921, 664);
    9. 动态等待返回“我的演出”舞台且该槽位绿色邀请按钮消失;
    10. 重新进入下一轮扫描，直到舞台上所有绿色邀请按钮消失;
    11. 状态沉淀为 PENDING 并返回 True。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[乐队鱼邀请] 错误: 未获取到 Controller", flush=True)
                return False

            print("[乐队鱼邀请] 开始执行动态全槽位邀请循环 (严格绑定指定人机好友)...", flush=True)
            t_start = time.time()
            max_loop_duration = 120.0

            def detect_slot_green_btn(img, slot_id):
                roi = SLOT_INVITE_INFO[slot_id]["roi"]
                x, y, w, h = roi
                crop = img[y:y+h, x:x+w]
                if crop.size == 0:
                    return False
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))
                return int(np.sum(mask > 0)) >= 300

            def is_friend_dialog_open(img):
                h, w = img.shape[:2]
                if w != 1280 or h != 720:
                    img = cv2.resize(img, (1280, 720))
                crop = img[100:160, 500:700]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))
                return int(np.sum(mask > 0)) >= 500

            def is_confirm_green(img):
                h, w = img.shape[:2]
                if w != 1280 or h != 720:
                    img = cv2.resize(img, (1280, 720))
                crop = img[640:695, 800:1040]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))
                return int(np.sum(mask > 0)) >= 800

            def is_on_stage(img):
                h, w = img.shape[:2]
                if w != 1280 or h != 720:
                    img = cv2.resize(img, (1280, 720))
                crop = img[400:550, 400:880]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([20, 100, 150]), np.array([35, 255, 255]))
                return int(np.sum(mask > 0)) >= 5000

            def capture_frame():
                job = ctrl.post_screencap()
                if not job:
                    return None
                job.wait()
                f = job.get()
                if f is not None:
                    fh, fw = f.shape[:2]
                    if fw != 1280 or fh != 720:
                        f = cv2.resize(f, (1280, 720))
                return f

            def locate_target_card(img, name):
                if not hasattr(context, "run_recognition"):
                    return None
                # 1. 尝试全名匹配
                res = context.run_recognition(
                    "BandFishFriendCardTarget",
                    img,
                    pipeline_override={"BandFishFriendCardTarget": {"expected": name}}
                )
                if res and res.hit:
                    return res.box
                # 2. 尝试前缀模糊匹配 (若名字长度 >= 2)
                kw = name[:2] if len(name) >= 2 else name
                res_kw = context.run_recognition(
                    "BandFishFriendCardTarget",
                    img,
                    pipeline_override={"BandFishFriendCardTarget": {"expected": kw}}
                )
                if res_kw and res_kw.hit:
                    return res_kw.box
                return None

            round_count = 0
            while time.time() - t_start < max_loop_duration:
                round_count += 1
                frame = capture_frame()
                if frame is None:
                    time.sleep(0.5)
                    continue

                empty_slots = []
                for s in (1, 2, 4, 5):
                    if detect_slot_green_btn(frame, s):
                        empty_slots.append(s)

                print(f"[乐队鱼邀请] [轮次 {round_count}] 扫描舞台槽位，当前待邀请空槽: {empty_slots}", flush=True)

                if not empty_slots:
                    print("[乐队鱼邀请] 舞台上已无任何绿色邀请按钮，所有槽位邀请完毕！", flush=True)
                    break

                target_slot = empty_slots[0]
                target_name = BAND_FISH_TARGETS.get(target_slot)
                if not target_name:
                    print(f"[乐队鱼邀请] 错误: 槽位 {target_slot} 未配置目标好友，跳过", flush=True)
                    break

                btn_x, btn_y = SLOT_INVITE_INFO[target_slot]["click"]
                print(f"[乐队鱼邀请] 准备处理槽位 {target_slot} (目标【{target_name}】)，点击邀请按钮 ({btn_x}, {btn_y})...", flush=True)
                ctrl.post_click(btn_x, btn_y).wait()

                # 1. 动态等待好友选择弹窗打开
                dialog_opened = False
                t_open = time.time()
                while time.time() - t_open < 4.5:
                    time.sleep(0.3)
                    f_diag = capture_frame()
                    if f_diag is not None and is_friend_dialog_open(f_diag):
                        dialog_opened = True
                        break

                if not dialog_opened:
                    print(f"[乐队鱼邀请] 点击槽位 {target_slot} 后未检测到好友选择弹窗打开，重试...", flush=True)
                    continue

                print(f"[乐队鱼邀请] 好友选择弹窗已打开，正在对当前列表进行 OCR 匹配指定人机好友【{target_name}】...", flush=True)

                # 2. 对当前页面执行纯列表 OCR 匹配目标好友
                card_box = locate_target_card(f_diag, target_name)

                # 3. 若当前屏未匹配到，向上滑动卡片列表寻找（严禁使用搜索框）
                scroll_count = 0
                f_cur = f_diag
                while card_box is None and scroll_count < 2:
                    scroll_count += 1
                    print(f"[乐队鱼邀请] 当前页面未检出【{target_name}】，向上滑动列表检索更多卡片 (第 {scroll_count}/2 次)...", flush=True)
                    ctrl.post_swipe(640, 520, 640, 260, 400).wait()
                    time.sleep(1.0)
                    f_cur = capture_frame()
                    if f_cur is not None:
                        card_box = locate_target_card(f_cur, target_name)

                # 4. 严苛防线：若列表 OCR 遍历后仍未定位到目标好友，立即安全熔断退出，绝不点击任何其他好友！
                if card_box is None:
                    print(f"[乐队鱼邀请] 严重警告: 列表 OCR 遍历后未匹配到指定人机好友【{target_name}】！触发安全熔断，放弃邀请以防误触！", flush=True)
                    ctrl.post_click(91, 46).wait()
                    time.sleep(1.2)
                    continue

                # 5. 命中目标好友，点击文字中心 (cx, cy)
                bx, by, bw, bh = card_box
                cx, cy = bx + bw // 2, by + bh // 2
                print(f"[乐队鱼邀请] 列表 OCR 命中目标好友【{target_name}】: bbox=({bx}, {by}, {bw}, {bh})，点击中心 ({cx}, {cy})...", flush=True)
                ctrl.post_click(cx, cy).wait()
                time.sleep(0.6)

                # 6. 核验选中状态（底部确认按钮必须变绿）
                f_check = capture_frame()
                if f_check is None or not is_confirm_green(f_check):
                    print(f"[乐队鱼邀请] 警告: 点击【{target_name}】后底部确认按钮未变绿，核验失败！点击返回退出", flush=True)
                    ctrl.post_click(91, 46).wait()
                    time.sleep(1.0)
                    continue

                print(f"[乐队鱼邀请] 目标好友【{target_name}】选定核验通过，底部确认按钮已变绿！", flush=True)

                # 7. 点击底部绿色“邀请”确认按钮 (921, 664)
                print("[乐队鱼邀请] 点击底部绿色确认按钮 (921, 664) 发出邀请...", flush=True)
                ctrl.post_click(921, 664).wait()

                # 8. 动态等待：弹窗关闭 + 回到舞台 + 该槽位绿色邀请按钮消失
                t_close = time.time()
                slot_finished = False
                while time.time() - t_close < 6.0:
                    time.sleep(0.4)
                    f_ret = capture_frame()
                    if f_ret is None:
                        continue
                    if not is_friend_dialog_open(f_ret) and is_on_stage(f_ret):
                        if not detect_slot_green_btn(f_ret, target_slot):
                            print(f"[乐队鱼邀请] 槽位 {target_slot} (【{target_name}】) 邀请确认成功！绿色邀请按钮已消失，进入下一槽位", flush=True)
                            slot_finished = True
                            break

                if not slot_finished:
                    print(f"[乐队鱼邀请] 槽位 {target_slot} 等待状态刷新超时，继续循环观察...", flush=True)

                time.sleep(0.5)

            band_fish_state["status"] = "PENDING"
            print("[乐队鱼邀请] 动态邀请循环全部执行完毕，业务状态沉淀为 PENDING", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼邀请] 运行异常: {e}", flush=True)
            return False



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

            # 2. 纯列表 OCR 定位目标人机好友（严禁使用搜索框）
            print(f"[乐队鱼] 好友弹窗已打开，正在对当前列表进行 OCR 寻找指定人机好友【{target_name}】...", flush=True)

            def locate_in_frame(f):
                if not hasattr(context, "run_recognition"):
                    return None
                res = context.run_recognition(
                    "BandFishFriendCardTarget",
                    f,
                    pipeline_override={"BandFishFriendCardTarget": {"expected": target_name}}
                )
                if res and res.hit:
                    return res.box
                kw = target_name[:2] if len(target_name) >= 2 else target_name
                res_kw = context.run_recognition(
                    "BandFishFriendCardTarget",
                    f,
                    pipeline_override={"BandFishFriendCardTarget": {"expected": kw}}
                )
                if res_kw and res_kw.hit:
                    return res_kw.box
                return None

            job_cap = ctrl.post_screencap()
            frame_before = job_cap.wait().get() if job_cap else None
            card_box = locate_in_frame(frame_before) if frame_before is not None else None

            # 3. 若首屏未检出，向上滑动列表检索（严禁使用搜索框）
            scroll_count = 0
            while card_box is None and scroll_count < 2:
                scroll_count += 1
                print(f"[乐队鱼] 首屏未见【{target_name}】，向上滑动列表寻找 (第 {scroll_count}/2 次)...", flush=True)
                ctrl.post_swipe(640, 520, 640, 260, 400).wait()
                time.sleep(1.0)
                job_s = ctrl.post_screencap()
                frame_before = job_s.wait().get() if job_s else None
                if frame_before is not None:
                    card_box = locate_in_frame(frame_before)

            if card_box is None:
                print(f"[乐队鱼] 严重警告: 列表 OCR 遍历后未找到目标好友【{target_name}】，安全放弃点击，退出弹窗以防误触！", flush=True)
                ctrl.post_click(91, 46).wait()
                time.sleep(1.0)
                return False

            bx, by, bw, bh = card_box
            cx, cy = bx + bw // 2, by + bh // 2
            print(f"[乐队鱼] 列表 OCR 成功定位目标好友【{target_name}】: bbox=({bx}, {by}, {bw}, {bh}), 点击中心=({cx}, {cy})", flush=True)

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


def advance_daily_routine_step(task_name: str, biz_status: str):
    """
    更新日常收尾子任务状态并推进队列中的下一个任务
    """
    if not daily_routine_state.get("active"):
        return

    if task_name in daily_routine_state.get("tasks", {}):
        daily_routine_state["tasks"][task_name]["status"] = biz_status

    queue = daily_routine_state.get("queue", [])
    if queue:
        next_step = queue.pop(0)
        daily_routine_state["step"] = next_step
        if next_step == "BAND_FISH_PASS2":
            daily_routine_state["tasks"]["BandFish"]["stage"] = "PASS2"
        print(f"[日常收尾] 子任务【{task_name}】完成 ({biz_status})，推进至下一任务: 【{next_step}】", flush=True)
    else:
        daily_routine_state["step"] = "ALL_DONE"
        print(f"[日常收尾] 子任务【{task_name}】完成 ({biz_status})，所有勾选任务已执行完毕！", flush=True)


@AgentServer.custom_action("BandFishExitToTankAction")
class BandFishExitToTankAction(CustomAction):
    """
    乐队鱼结算并安全返回主鱼缸动作:
    1. 判断并沉淀业务状态 (DONE / PENDING);
    2. 若处于 DailyRoutineTask 流程中，同步子任务状态并推进下一阶段;
    3. 点击左上角返回 [91, 46] -> 关闭潜在浮层 [640, 150]，确保 100% 回到主鱼缸。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[乐队鱼退出] 错误: 未获取到 Controller", flush=True)
                return False

            status = band_fish_state.get("status")
            perf_finished = band_fish_state.get("performance_finished", False)
            if status == "DONE" or perf_finished:
                biz_status = "DONE"
            else:
                biz_status = "PENDING"

            if daily_routine_state.get("active"):
                stage = daily_routine_state["tasks"]["BandFish"].get("stage", "PASS1")
                daily_routine_state["tasks"]["BandFish"]["status"] = biz_status
                print(f"[日常收尾] 乐队鱼 ({stage}) 状态沉淀: {biz_status}", flush=True)
                advance_daily_routine_step("BandFish", biz_status)

            print(f"[乐队鱼退出] 业务状态: {biz_status}，执行物理退出回鱼缸...", flush=True)

            # 点击左上角返回按钮
            ctrl.post_click(91, 46).wait()
            time.sleep(1.8)

            # 保底点击安全区域关闭可能残留的游乐园面板
            ctrl.post_click(640, 150).wait()
            time.sleep(1.0)

            print("[乐队鱼退出] 已安全退出回主鱼缸", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[乐队鱼退出] 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("FishingExitToTankAction")
class FishingExitToTankAction(CustomAction):
    """
    钓鱼达人结算并安全返回主鱼缸动作:
    1. 判断业务状态: cast_count >= max_casts 判定为 DONE，否则判定为 NO_STAMINA (鱼饵耗尽/购买弹窗关闭);
    2. 若处于 DailyRoutineTask 流程中，同步状态并推进至 BAND_FISH_PASS2;
    3. 点击钓场左上角返回 [50, 45] -> 点击地点大地图右上角关闭 [1235, 45] -> 点击安全区 [640, 150]，确保 100% 回到主鱼缸。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[钓鱼退出] 错误: 未获取到 Controller", flush=True)
                return False

            casts = fishing_state.get("cast_count", 0)
            max_c = fishing_state.get("max_casts", 5)
            if casts >= max_c:
                biz_status = "DONE"
            else:
                biz_status = "NO_STAMINA"
            fishing_state["status"] = biz_status

            if daily_routine_state.get("active"):
                daily_routine_state["tasks"]["Fishing"]["status"] = biz_status
                print(f"[日常收尾] 钓鱼达人 状态沉淀: {biz_status} (已完成 {casts}/{max_c} 杆)", flush=True)
                advance_daily_routine_step("Fishing", biz_status)

            print(f"[钓鱼退出] 业务状态: {biz_status}，执行物理退出回鱼缸...", flush=True)

            # 1. 点击钓场左上角返回
            ctrl.post_click(50, 45).wait()
            time.sleep(2.0)

            # 2. 点击地点大地图右上角关闭按钮
            ctrl.post_click(1235, 45).wait()
            time.sleep(1.8)

            # 3. 保底点击安全区关闭游乐园面板
            ctrl.post_click(640, 150).wait()
            time.sleep(1.0)

            print("[钓鱼退出] 已安全退出回主鱼缸", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼退出] 异常: {e}", flush=True)
            return False


# ==============================================================================
# 金海豚小游戏基础设施与 Action 拆分 (Phase 2A-1)
# ==============================================================================

def _get_golden_dolphin_templates():
    """统一解析并加载金海豚关键视觉模板"""
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_dirs = [
        os.path.join(agent_dir, "../resource/image"),
        os.path.join(agent_dir, "../assets/resource/image"),
        os.path.join(agent_dir, "../../assets/resource/image"),
        os.path.abspath("assets/resource/image"),
        os.path.abspath("client_avalonia/resource/image"),
        os.path.abspath("resource/image"),
    ]
    tpl_dir = None
    for d in candidate_dirs:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "游乐园入口.png")):
            tpl_dir = os.path.abspath(d)
            break

    def _load_tpl(name: str):
        if not tpl_dir:
            return None
        p = os.path.join(tpl_dir, name)
        if not os.path.exists(p):
            return None
        return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)

    return {
        "tpl_dir": tpl_dir,
        "entrance": _load_tpl("游乐园入口.png"),
        "dolphin": _load_tpl("金海豚_图标.png"),
        "confirm": _load_tpl("金海豚_确定按钮.png"),
        "star": _load_tpl("金海豚_经验星.png"),
        "cancel": _load_tpl("金海豚_结束取消.png"),
    }


def _find_green_check(img):
    """HSV 双通道绿色对号按钮几何定位"""
    if img is None:
        return None
    if img.shape[0] != 720 or img.shape[1] != 1280:
        img = cv2.resize(img, (1280, 720))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([35, 70, 70]), np.array([85, 255, 255]))
    submask = np.zeros_like(mask)
    submask[410:560, 750:910] = mask[410:560, 750:910]
    cnts, _ = cv2.findContours(submask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        area = cv2.contourArea(c)
        if area > 1000:
            x, y, w, h = cv2.boundingRect(c)
            ar = w / float(h) if h > 0 else 0
            if 0.70 <= ar <= 1.30 and 45 <= w <= 85 and 45 <= h <= 85:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
    return None


@AgentServer.custom_action("GoldenDolphinNavigationAction")
class GoldenDolphinNavigationAction(CustomAction):
    """
    金海豚导航与进入动作 (职责 1):
    1. Deepest-First 状态判定 (弹窗界面 / 游乐园面板 / 主鱼缸场景)
    2. 打开游乐园并点击金海豚图标
    3. 弹窗裁决 (「机会已用完」vs「正常想玩」)
       - 耗尽: 闭环点击对号关闭弹窗，设置 status=NO_STAMINA，返回 True
       - 正常: 点击对号进入游戏，设置 status=READY_TO_PLAY，返回 True
       - 失败: 设置 status=FAILED，返回 False
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[金海豚导航] 错误: 未获取到 Controller", flush=True)
                golden_dolphin_state["status"] = "FAILED"
                return False

            tpls = _get_golden_dolphin_templates()
            tpl_ent = tpls.get("entrance")
            tpl_dolphin = tpls.get("dolphin")
            tpl_confirm = tpls.get("confirm")

            if tpl_ent is None or tpl_dolphin is None or tpl_confirm is None:
                print("[金海豚导航] ERROR: 缺少关键视觉模板，安全终止任务！", flush=True)
                golden_dolphin_state["status"] = "FAILED"
                return False

            print("[金海豚导航] 启动金海豚导航流程，检测当前页面状态...", flush=True)
            job = ctrl.post_screencap()
            if job: job.wait()
            screen = job.get() if job else None
            if screen is None:
                print("[金海豚导航] ERROR: 无法获取截屏，安全终止任务", flush=True)
                golden_dolphin_state["status"] = "FAILED"
                return False

            # Deepest-First 状态检查 0: 检查是否已经处于确认/机会用完弹窗
            gc_init = _find_green_check(screen)
            res_c_init = cv2.matchTemplate(screen, tpl_confirm, cv2.TM_CCOEFF_NORMED) if tpl_confirm is not None else None
            vc_init = cv2.minMaxLoc(res_c_init)[1] if res_c_init is not None else 0
            already_in_popup = (gc_init is not None or vc_init >= 0.70)

            screen_confirm = None
            has_confirm = False
            btn_cx, btn_cy = 828, 490

            if already_in_popup:
                print(f"[金海豚导航] 状态判定：当前已处于提示/确认弹窗界面 (green_check={gc_init}, match={vc_init:.3f})", flush=True)
                screen_confirm = screen
                has_confirm = True
                if gc_init:
                    btn_cx, btn_cy = gc_init
                elif res_c_init is not None:
                    loc_c = cv2.minMaxLoc(res_c_init)[3]
                    btn_cx = loc_c[0] + tpl_confirm.shape[1] // 2
                    btn_cy = loc_c[1] + tpl_confirm.shape[0] // 2
            else:
                # 状态判定 1: 检查是否已经处于游乐园面板中 (通过匹配金海豚图标)
                res_d = cv2.matchTemplate(screen, tpl_dolphin, cv2.TM_CCOEFF_NORMED)
                _, max_vd, _, loc_d = cv2.minMaxLoc(res_d)
                in_amusement_panel = (max_vd >= 0.70)

                if in_amusement_panel:
                    print(f"[金海豚导航] 状态判定：当前已处于游乐园面板内 (金海豚 match={max_vd:.3f})", flush=True)
                else:
                    # 状态判定 2: 主鱼缸场景，检测游乐园入口
                    print("[金海豚导航] 状态判定：当前未在游乐园面板，检测主鱼缸游乐园入口...", flush=True)
                    res_e = cv2.matchTemplate(screen, tpl_ent, cv2.TM_CCOEFF_NORMED)
                    _, max_ve, _, loc_e = cv2.minMaxLoc(res_e)
                    if max_ve < 0.70:
                        print(f"[金海豚导航] ERROR: 未识别到游乐园入口 (score={max_ve:.3f} < 0.70)，安全终止，坚决不盲目点击！", flush=True)
                        golden_dolphin_state["status"] = "FAILED"
                        return False

                    ent_cx = loc_e[0] + tpl_ent.shape[1] // 2
                    ent_cy = loc_e[1] + tpl_ent.shape[0] // 2
                    print(f"[金海豚导航] 识别到水族箱游乐园入口 (score={max_ve:.3f})，点击 ({ent_cx}, {ent_cy}) 打开游乐园...", flush=True)
                    ctrl.post_click(ent_cx, ent_cy).wait()

                    # 等待游乐园面板展开并验证 (最多轮询 3 次)
                    in_amusement_panel = False
                    for wait_idx in range(3):
                        time.sleep(1.2 if wait_idx == 0 else 0.8)
                        job = ctrl.post_screencap()
                        if job: job.wait()
                        screen = job.get() if job else None
                        if screen is None:
                            continue
                        res_d = cv2.matchTemplate(screen, tpl_dolphin, cv2.TM_CCOEFF_NORMED)
                        _, max_vd, _, loc_d = cv2.minMaxLoc(res_d)
                        if max_vd >= 0.65:
                            in_amusement_panel = True
                            break

                    if not in_amusement_panel:
                        print(f"[金海豚导航] ERROR: 打开游乐园后未检测到金海豚图标 (max_score={max_vd:.3f} < 0.65)，安全收起浮层退出！", flush=True)
                        ctrl.post_click(640, 150).wait()
                        time.sleep(1.0)
                        golden_dolphin_state["status"] = "FAILED"
                        return False

                # 2. 确认游乐园面板就绪后，点击金海豚图标
                dx = loc_d[0] + tpl_dolphin.shape[1] // 2
                dy = loc_d[1] + tpl_dolphin.shape[0] // 2
                print(f"[金海豚导航] 确认游乐园面板就绪，点击金海豚图标 (score={max_vd:.3f}) at ({dx}, {dy})...", flush=True)
                ctrl.post_click(dx, dy).wait()
                time.sleep(1.5)

                # 3. 检查是否弹出“您想玩这个小游戏吗？”确认弹窗 (轮询确认)
                for wait_c in range(4):
                    job = ctrl.post_screencap()
                    if job: job.wait()
                    screen_confirm = job.get() if job else None
                    if screen_confirm is not None:
                        gc = _find_green_check(screen_confirm)
                        res_c = cv2.matchTemplate(screen_confirm, tpl_confirm, cv2.TM_CCOEFF_NORMED) if tpl_confirm is not None else None
                        max_vc = cv2.minMaxLoc(res_c)[1] if res_c is not None else 0
                        if gc is not None:
                            has_confirm = True
                            btn_cx, btn_cy = gc
                            print(f"[金海豚导航] 准确定位到确认对号按钮 (HSV检测) at ({btn_cx}, {btn_cy})", flush=True)
                            break
                        elif max_vc >= 0.70:
                            has_confirm = True
                            loc_c = cv2.minMaxLoc(res_c)[3]
                            btn_cx = loc_c[0] + tpl_confirm.shape[1] // 2
                            btn_cy = loc_c[1] + tpl_confirm.shape[0] // 2
                            print(f"[金海豚导航] 匹配到确认对号按钮 (模板 score={max_vc:.3f}) at ({btn_cx}, {btn_cy})", flush=True)
                            break
                    time.sleep(0.6)

            if not has_confirm or screen_confirm is None:
                print("[金海豚导航] 未检测到确认对号按钮，安全收起面板退出", flush=True)
                golden_dolphin_state["status"] = "NO_STAMINA"
                ctrl.post_click(640, 150).wait()
                time.sleep(1.0)
                return True

            # 区分“机会已全部用完”与“您想玩这个小游戏吗”
            is_exhausted = False
            try:
                sc_720 = cv2.resize(screen_confirm, (1280, 720))
                red_patch = sc_720[430:490, 650:710]
                hsv_p = cv2.cvtColor(red_patch, cv2.COLOR_BGR2HSV)
                mask_r = ((hsv_p[:, :, 0] < 10) | (hsv_p[:, :, 0] > 170)) & (hsv_p[:, :, 1] > 90) & (hsv_p[:, :, 2] > 90)
                has_red_cancel = bool(np.sum(mask_r) > 400)
                if not has_red_cancel:
                    is_exhausted = True
            except Exception:
                pass

            if not is_exhausted:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    _ocr = RapidOCR()
                    res_ocr, _ = _ocr(screen_confirm)
                    for _, txt, _ in (res_ocr or []):
                        if any(k in txt for k in ("用完", "明天再来", "全部用完", "明天")):
                            is_exhausted = True
                            break
                except Exception:
                    pass

            if is_exhausted:
                print(f"[金海豚导航] 检测到提示「今天的机会已全部用完」，点击绿色对号按钮 ({btn_cx}, {btn_cy}) 关闭并验证...", flush=True)
                dialog_closed = False
                for click_retry in range(3):
                    ctrl.post_click(btn_cx, btn_cy).wait()
                    time.sleep(1.2)
                    job = ctrl.post_screencap()
                    if job: job.wait()
                    sc_after = job.get() if job else None
                    if sc_after is not None:
                        res_check = cv2.matchTemplate(sc_after, tpl_confirm, cv2.TM_CCOEFF_NORMED) if tpl_confirm is not None else None
                        max_vc_after = cv2.minMaxLoc(res_check)[1] if res_check is not None else 0
                        gc_after = _find_green_check(sc_after)
                        if max_vc_after < 0.65 and gc_after is None:
                            dialog_closed = True
                            print("[金海豚导航] 验证通过：机会耗尽提示弹窗已成功关闭！", flush=True)
                            break
                        else:
                            print(f"[金海豚导航] 提示弹窗仍在画面上 (重试 {click_retry+1}/3)，重新尝试点击对号...", flush=True)
                            if gc_after:
                                btn_cx, btn_cy = gc_after

                if not dialog_closed:
                    print("[金海豚导航] 警告: 尝试多次点击对号后弹窗仍未关闭，尝试保底点击对号坐标", flush=True)
                    ctrl.post_click(btn_cx, btn_cy).wait()
                    time.sleep(1.0)

                golden_dolphin_state["status"] = "NO_STAMINA"
                return True

            # 点击绿色确认按钮进入小游戏
            print(f"[金海豚导航] 点击确认按钮 ({btn_cx}, {btn_cy}) 进入小游戏...", flush=True)
            ctrl.post_click(btn_cx, btn_cy).wait()
            time.sleep(2.0)
            golden_dolphin_state["status"] = "READY_TO_PLAY"
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[金海豚导航] 运行异常: {e}", flush=True)
            golden_dolphin_state["status"] = "FAILED"
            return False


@AgentServer.custom_action("GoldenDolphinPlayGameAction")
class GoldenDolphinPlayGameAction(CustomAction):
    """
    金海豚小游戏拾取动作 (职责 2):
    仅负责游戏画面内的微观交互:
    1. 点击激活计时 (640, 360)
    2. 55s 高频抓帧与 Method E 黄色经验星拾取
    3. 游戏结束弹窗监听
    不包含：游乐园导航、返回鱼缸归位
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[金海豚游戏] 错误: 未获取到 Controller", flush=True)
                return False

            tpls = _get_golden_dolphin_templates()
            tpl_star = tpls.get("star")
            tpl_cancel = tpls.get("cancel")

            # 1. 点击中央激活计时
            print("[金海豚游戏] 执行游戏启动点击 (640, 360) 激活计时...", flush=True)
            ctrl.post_click(640, 360).wait()
            time.sleep(0.5)

            # 2. 进入 Method E 检测点击循环
            print("[金海豚游戏] 开始进入 Method E XP 经验星自动点击主循环...", flush=True)
            t_game_start = time.time()
            th_s, tw_s = (tpl_star.shape[:2]) if tpl_star is not None else (60, 60)
            game_done = False
            total_clicks = 0

            while time.time() - t_game_start < 55.0:
                elapsed = time.time() - t_game_start
                job = ctrl.post_screencap()
                if not job:
                    time.sleep(0.03)
                    continue
                job.wait()
                img = job.get()
                if img is None:
                    time.sleep(0.02)
                    continue

                h, w = img.shape[:2]
                if w != 1280 or h != 720:
                    img = cv2.resize(img, (1280, 720))

                # 超过 20 秒后开始检查游戏结束弹窗
                if elapsed > 20.0 and tpl_cancel is not None:
                    res_cancel = cv2.matchTemplate(img, tpl_cancel, cv2.TM_CCOEFF_NORMED)
                    _, max_cancel, _, loc_cancel = cv2.minMaxLoc(res_cancel)
                    if max_cancel >= 0.70:
                        print(f"[金海豚游戏] 检测到游戏结束结算弹窗 (score={max_cancel:.3f})，跳出游戏循环", flush=True)
                        game_done = True
                        break

                # Method E XP 检测
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([15, 65, 110]), np.array([35, 255, 255]))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                candidates = []
                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    x, y, cw, ch = cv2.boundingRect(cnt)
                    if y < 25 or y > 665:
                        continue
                    ar = cw / float(ch) if ch > 0 else 0
                    if 950 <= area <= 3300 and 0.80 <= ar <= 1.30 and 48 <= cw <= 78 and 44 <= ch <= 78:
                        cx, cy = x + cw // 2, y + ch // 2
                        if tpl_star is not None:
                            x1 = max(0, cx - tw_s // 2)
                            y1 = max(0, cy - th_s // 2)
                            x2 = min(img.shape[1], x1 + tw_s)
                            y2 = min(img.shape[0], y1 + th_s)
                            patch = img[y1:y2, x1:x2]
                            if patch.shape[:2] == tpl_star.shape[:2]:
                                score = float(cv2.matchTemplate(patch, tpl_star, cv2.TM_CCOEFF_NORMED)[0, 0])
                                if score >= 0.45:
                                    candidates.append((cx, cy, score))
                        else:
                            candidates.append((cx, cy, 0.5))

                if candidates:
                    golden = [c for c in candidates if 200 <= c[1] <= 540]
                    target = sorted(golden if golden else candidates, key=lambda c: c[1], reverse=True)[0]
                    ctrl.post_click(target[0], target[1])
                    total_clicks += 1
                    time.sleep(0.18)

            print(f"[金海豚游戏] 小游戏循环完成 (耗时 {time.time() - t_game_start:.1f}s, 总点击 XP {total_clicks} 次, 弹窗就绪={game_done})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[金海豚游戏] 运行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("GoldenDolphinExitAction")
class GoldenDolphinExitAction(CustomAction):
    """
    金海豚退出与归位动作 (职责 3):
    1. 点击结算取消按钮 (或保底点击)
    2. 关闭潜在浮层，确认回到主鱼缸
    3. 设置 golden_dolphin_state["status"] = "DONE"
    注意: 不负责推进日常收尾调度 (解耦设计)
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[金海豚退出] 错误: 未获取到 Controller", flush=True)
                return False

            tpls = _get_golden_dolphin_templates()
            tpl_cancel = tpls.get("cancel")

            # 1. 尝试识别结算弹窗中的取消按钮并点击
            job = ctrl.post_screencap()
            if job: job.wait()
            sc = job.get() if job else None

            exited = False
            if sc is not None and tpl_cancel is not None:
                if sc.shape[0] != 720 or sc.shape[1] != 1280:
                    sc = cv2.resize(sc, (1280, 720))
                res_cancel = cv2.matchTemplate(sc, tpl_cancel, cv2.TM_CCOEFF_NORMED)
                _, max_cancel, _, loc_cancel = cv2.minMaxLoc(res_cancel)
                if max_cancel >= 0.70:
                    cancel_x = loc_cancel[0] + tpl_cancel.shape[1] // 2
                    cancel_y = loc_cancel[1] + tpl_cancel.shape[0] // 2
                    print(f"[金海豚退出] 识别到结算取消按钮 (score={max_cancel:.3f})，点击 ({cancel_x}, {cancel_y})", flush=True)
                    ctrl.post_click(cancel_x, cancel_y).wait()
                    time.sleep(1.8)
                    exited = True

            if not exited:
                print("[金海豚退出] 未检出明确结算按钮，执行保底点击 (850, 574) 与 (640, 150)...", flush=True)
                ctrl.post_click(850, 574).wait()
                time.sleep(1.5)
                ctrl.post_click(640, 150).wait()
                time.sleep(1.0)

            golden_dolphin_state["status"] = "DONE"
            print("[金海豚退出] 结算退出完成，已设置 status=DONE，确认回到主鱼缸", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[金海豚退出] 运行异常: {e}", flush=True)
            return False

@AgentServer.custom_action("GoldenDolphinDoneAction")
class GoldenDolphinDoneAction(CustomAction):
    """
    金海豚结束节点动作:
    沉淀最终状态，若处于日常收尾流程中，通知日常收尾推进下一个任务。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        st = golden_dolphin_state.get("status", "DONE")
        if daily_routine_state.get("active"):
            advance_daily_routine_step("GoldenDolphin", st)
        print(f"[金海豚] 流程结束，最终状态: {st}", flush=True)
        return True


@AgentServer.custom_action("GoldenDolphinTaskAction")
class GoldenDolphinTaskAction(CustomAction):
    """
    金海豚任务总控入口适配器 (保持 Pipeline 100% 兼容):
    内部顺次协调调用:
    1. GoldenDolphinNavigationAction
    2. 若状态为 READY_TO_PLAY:
       -> GoldenDolphinPlayGameAction
       -> GoldenDolphinExitAction
    3. 若处于日常收尾流程，根据最终业务状态推进 DailyRoutine 队列
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            # 1. 导航与弹窗判定
            nav = GoldenDolphinNavigationAction()
            nav_ok = nav.run(context, argv)
            if not nav_ok:
                if daily_routine_state.get("active"):
                    advance_daily_routine_step("GoldenDolphin", "FAILED")
                return False

            st = golden_dolphin_state.get("status")
            if st == "NO_STAMINA":
                if daily_routine_state.get("active"):
                    advance_daily_routine_step("GoldenDolphin", "NO_STAMINA")
                return True

            if st == "READY_TO_PLAY":
                # 2. 小游戏主循环
                play = GoldenDolphinPlayGameAction()
                play.run(context, argv)

                # 3. 结算退出
                exit_act = GoldenDolphinExitAction()
                exit_ok = exit_act.run(context, argv)

                if daily_routine_state.get("active"):
                    final_st = golden_dolphin_state.get("status", "DONE")
                    advance_daily_routine_step("GoldenDolphin", final_st)
                return exit_ok

            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[金海豚总控] 运行异常: {e}", flush=True)
            golden_dolphin_state["status"] = "FAILED"
            if daily_routine_state.get("active"):
                advance_daily_routine_step("GoldenDolphin", "FAILED")
            return False


@AgentServer.custom_action("InitDailyRoutineAction")
class InitDailyRoutineAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            daily_routine_state["active"] = True
            daily_routine_state["tasks"] = {
                "BandFish": {"status": "IDLE", "stage": "PASS1"},
                "GoldenDolphin": {"status": "IDLE"},
                "Fishing": {"status": "IDLE"},
                "RomanticHouse": {"status": "IDLE"},
            }

            # 1. 优先从 custom_action_param 解析配置 (支持测试与外部传参)
            param = parse_dict_param(argv.custom_action_param)
            has_param = any(k in param for k in ("band_fish", "golden_dolphin", "fishing", "romantic_house"))

            if has_param:
                enable_bf = bool(param.get("band_fish", False))
                enable_gd = bool(param.get("golden_dolphin", False))
                enable_fi = bool(param.get("fishing", False))
                enable_rh = bool(param.get("romantic_house", False))
            else:
                # 2. 从 pipeline override 中的 Enable 节点读取配置
                def _is_node_enabled(node_name: str) -> bool:
                    try:
                        nd = context.get_node_data(node_name)
                        return bool(nd.get("enabled", False)) if nd else False
                    except Exception:
                        return False

                enable_bf = _is_node_enabled("DailyRoutineEnableBandFish")
                enable_gd = _is_node_enabled("DailyRoutineEnableGoldenDolphin")
                enable_fi = _is_node_enabled("DailyRoutineEnableFishing")
                enable_rh = _is_node_enabled("DailyRoutineEnableRomanticHouse")

            # 3. 按固定安全顺序构建待执行队列: 1. 乐队鱼 -> 2. 金海豚 -> 3. 钓鱼达人 -> 4. 浪漫满屋 -> 5. 乐队鱼二次巡检
            queue = []
            if enable_bf:
                queue.append("BAND_FISH_PASS1")
            if enable_gd:
                queue.append("GOLDEN_DOLPHIN")
            if enable_fi:
                queue.append("FISHING")
            if enable_rh:
                queue.append("ROMANTIC_HOUSE")
            if enable_bf:
                queue.append("BAND_FISH_PASS2")

            print("=" * 60, flush=True)
            print("[日常收尾] DailyRoutineTask 初始化成功，勾选子任务配置:", flush=True)
            print(f"  - 乐队鱼演出   : {'[ON]' if enable_bf else '[OFF]'}", flush=True)
            print(f"  - 金海豚小游戏 : {'[ON]' if enable_gd else '[OFF]'}", flush=True)
            print(f"  - 钓鱼达人     : {'[ON]' if enable_fi else '[OFF]'}", flush=True)
            print(f"  - 浪漫满屋     : {'[ON]' if enable_rh else '[OFF]'}", flush=True)
            print("=" * 60, flush=True)

            if queue:
                initial_step = queue.pop(0)
                daily_routine_state["queue"] = queue
                daily_routine_state["step"] = initial_step
                print(f"[日常收尾] 启动首个执行任务: 【{initial_step}】，后续排队: {queue}", flush=True)
            else:
                daily_routine_state["queue"] = []
                daily_routine_state["step"] = "ALL_DONE"
                print("[日常收尾] 未勾选任何日常子任务，直接跳过并完成", flush=True)

            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[日常收尾] 初始化异常: {e}", flush=True)
            return False


@AgentServer.custom_action("DailyRoutineSkipBandFishPass2Action")
class DailyRoutineSkipBandFishPass2Action(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[日常收尾] 乐队鱼状态无需二次巡检 (已完成/非待定)，跳过 Pass 2", flush=True)
            advance_daily_routine_step("BandFish", daily_routine_state["tasks"]["BandFish"].get("status", "DONE"))
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[日常收尾] 跳过 Pass 2 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("RomanticHouseExitToTankAction")
class RomanticHouseExitToTankAction(CustomAction):
    """
    浪漫满屋结算并推进日常收尾调度动作:
    1. 标记 romantic_house_state["status"] = "DONE";
    2. 若处于 DailyRoutineTask 流程中，同步状态并推进队列下一个任务;
    3. 返回 True。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[浪漫满屋退出] 已确认返回主鱼缸珊瑚", flush=True)
            romantic_house_state["status"] = "DONE"
            if daily_routine_state.get("active"):
                advance_daily_routine_step("RomanticHouse", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[浪漫满屋退出] 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("DailyRoutineFinishAction")
class DailyRoutineFinishAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            tasks = daily_routine_state.get("tasks", {})
            bf_st = tasks.get("BandFish", {}).get("status", "SKIPPED")
            gd_st = tasks.get("GoldenDolphin", {}).get("status", "SKIPPED")
            fi_st = tasks.get("Fishing", {}).get("status", "SKIPPED")
            rh_st = tasks.get("RomanticHouse", {}).get("status", "SKIPPED")

            print("=" * 60, flush=True)
            print("  【日常收尾 DailyRoutineTask】全部勾选子任务执行完毕！", flush=True)
            print(f"  - 乐队鱼演出 (BandFish)       : {bf_st}", flush=True)
            print(f"  - 金海豚小游戏 (GoldenDolphin) : {gd_st}", flush=True)
            print(f"  - 钓鱼达人 (Fishing)          : {fi_st}", flush=True)
            print(f"  - 浪漫满屋 (RomanticHouse)    : {rh_st}", flush=True)
            print("=" * 60, flush=True)

            daily_routine_state["active"] = False
            daily_routine_state["step"] = "ALL_DONE"
            daily_routine_state["queue"] = []
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[日常收尾] 结束汇总异常: {e}", flush=True)
            return False




