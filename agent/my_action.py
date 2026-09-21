import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional, Tuple

import cv2
import numpy as np

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.pipeline import JActionType, JLongPress
from maa.define import RectType

try:
    from runtime_state import (
        friend_gem_state,
        manatee_state,
        sea_otter_gem_state,
        band_fish_state,
        BAND_FISH_TARGETS,
        romantic_house_state,
        daily_routine_state,
        fishing_state,
        golden_dolphin_state,
        shake_game_state,
        gem_collect_state,
        mobile_ad_state,
        collect_fish_state,
        starfish_timer_state,
        green_wild_daily_state,
        hangup_schedule_state,
        secret_realm_gate_state,
    )
except ImportError:
    from agent.runtime_state import (
        friend_gem_state,
        manatee_state,
        sea_otter_gem_state,
        band_fish_state,
        BAND_FISH_TARGETS,
        romantic_house_state,
        daily_routine_state,
        fishing_state,
        golden_dolphin_state,
        shake_game_state,
        gem_collect_state,
        mobile_ad_state,
        collect_fish_state,
        starfish_timer_state,
        green_wild_daily_state,
        hangup_schedule_state,
        secret_realm_gate_state,
    )

try:
    from param_utils import parse_dict_param, safe_float, safe_int
except ImportError:
    from agent.param_utils import parse_dict_param, safe_float, safe_int

try:
    import local_state
except ImportError:
    from agent import local_state

try:
    from puzzle_solver import PUZZLE_SPEC_4X4, PUZZLE_SPEC_5X5, PUZZLE_SPEC_6X6, PuzzleSolver
    from puzzle_solver_5x5 import Puzzle5x5Solver, Puzzle6x6Solver, PuzzleSearchBudgetExceeded
    from puzzle_executor import (
        MaaPuzzleExecutor,
        PUZZLE_GEOMETRY_4X4,
        PUZZLE_GEOMETRY_5X5,
        PUZZLE_GEOMETRY_6X6,
    )
    from puzzle_position import PuzzlePositionError, parse_piece_positions
except ImportError:
    from agent.puzzle_solver import (
        PUZZLE_SPEC_4X4,
        PUZZLE_SPEC_5X5,
        PUZZLE_SPEC_6X6,
        PuzzleSolver,
    )
    from agent.puzzle_solver_5x5 import (
        Puzzle5x5Solver,
        Puzzle6x6Solver,
        PuzzleSearchBudgetExceeded,
    )
    from agent.puzzle_executor import (
        MaaPuzzleExecutor,
        PUZZLE_GEOMETRY_4X4,
        PUZZLE_GEOMETRY_5X5,
        PUZZLE_GEOMETRY_6X6,
    )
    from agent.puzzle_position import PuzzlePositionError, parse_piece_positions


def _capture_720p(controller):
    job = controller.post_screencap()
    if not job:
        return None
    job.wait()
    frame = job.get()
    if frame is None:
        return None
    height, width = frame.shape[:2]
    if width != 1280 or height != 720:
        frame = cv2.resize(frame, (1280, 720))
    return frame


_golden_dolphin_ocr = None


def _get_golden_dolphin_ocr():
    """RapidOCR lazy singleton：仅在疑似耗尽分支首次调用时加载模型。"""
    global _golden_dolphin_ocr
    if _golden_dolphin_ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _golden_dolphin_ocr = RapidOCR()
    return _golden_dolphin_ocr


def _confirm_golden_dolphin_dialog_closed(ctrl, tpl_confirm, screen_confirm, btn_cx, btn_cy):
    """普通“想玩”确认弹窗点击闭环：点击 → fresh 截图 → confirm 模板验证弹窗关闭。

    最多 3 次点击，每次重试前用 fresh 帧上的 HSV 中心更新坐标（不缓存旧坐标）。
    返回 (dialog_closed, btn_cx, btn_cy)。
    """
    dialog_closed = False
    for _attempt in range(3):
        ctrl.post_click(btn_cx, btn_cy).wait()
        time.sleep(0.8)
        job = ctrl.post_screencap()
        sc = job.get() if job else None
        if sc is None:
            continue
        confirm_score = 0.0
        if tpl_confirm is not None:
            res_c = cv2.matchTemplate(sc, tpl_confirm, cv2.TM_CCOEFF_NORMED)
            confirm_score = cv2.minMaxLoc(res_c)[1]
        if confirm_score < 0.65:
            dialog_closed = True
            break
        gc = _find_green_check(sc)
        if gc is not None:
            btn_cx, btn_cy = gc
    return dialog_closed, btn_cx, btn_cy


def _recognition_box(context: Context, node_name: str, frame):
    if frame is None or not hasattr(context, "run_recognition"):
        return None
    result = context.run_recognition(node_name, frame)
    if not result or not result.hit:
        return None
    return tuple(int(value) for value in result.box)


def _box_center(box):
    x, y, width, height = box
    return x + width // 2, y + height // 2


def _task_cancelled(context: Context) -> bool:
    try:
        return bool(context.tasker.stopping) or not bool(context.tasker.running)
    except Exception:
        return True


def _band_fish_locate_target_card(context: Context, frame, target_name: str):
    """在好友列表 OCR 结果中安全定位指定名字，并返回识别框与候选文本。"""
    if frame is None or not hasattr(context, "run_recognition"):
        return None, []

    seen_texts = []
    keywords = [target_name]
    # 台式机发行版 Maa OCR 会把“一只胖梨”稳定识别成“只胖梨”。
    # 仅放行日志已确认的专用别名，不泛化为任意首字缺失，避免误邀。
    if target_name == "一只胖梨":
        keywords.append("只胖梨")
    if len(target_name) >= 2:
        keywords.append(target_name[:2])

    for keyword in keywords:
        # Maa OCR 的 expected 使用整段正则匹配。好友名左侧的在线圆点、
        # 等级数字等有时会被 OCR 合并进同一文本框，因此允许固定名字
        # 前后存在附加字符，但仍只点击明确包含目标名字/前缀的 OCR 框。
        expected = f".*{re.escape(keyword)}.*"
        result = context.run_recognition(
            "BandFishFriendCardTarget",
            frame,
            pipeline_override={"BandFishFriendCardTarget": {"expected": expected}},
        )
        for item in getattr(result, "all_results", []) or []:
            text = str(getattr(item, "text", "")).strip()
            if text and text not in seen_texts:
                seen_texts.append(text)
        if result and result.hit:
            return tuple(int(value) for value in result.box), seen_texts

    return None, seen_texts


def _ocr_texts(result):
    texts = []
    if not result:
        return texts
    best = getattr(result, "best_result", None)
    if best:
        text = str(getattr(best, "text", "")).strip()
        if text:
            texts.append(text)
    for item in getattr(result, "all_results", []) or []:
        text = str(getattr(item, "text", "")).strip()
        if text and text not in texts:
            texts.append(text)
    return texts


def _recognition_number(context: Context, node_name: str, frame):
    if frame is None or not hasattr(context, "run_recognition"):
        return None
    result = context.run_recognition(node_name, frame)
    texts = _ocr_texts(result)
    text = texts[0] if texts else ""
    # Maa OCR 在这个白底数量框里会把单独的“1”认成相似笔画。
    # 该兼容只作用于数量专用 ROI，避免把同形字符扩散到其他 OCR 节点。
    if node_name == "BuyFishFoodQuantity" and text in {"」", "丨", "|", "I", "l", "i", "/", "／"}:
        text = "1"
    digits = "".join(char for char in text if char.isdigit())
    if digits:
        return int(digits)
    if node_name == "BuyFishFoodQuantity":
        print(f"[购买鱼食] 数量框 OCR 原文={texts!r}，无法解析为购买数量", flush=True)
    return None


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


@AgentServer.custom_action("FindCheapFishFoodAction")
class FindCheapFishFoodAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            controller = context.tasker.controller
            if not controller:
                print("[购买鱼食] 错误: 未获取到 Controller", flush=True)
                return False

            param = parse_dict_param(argv.custom_action_param)
            max_scrolls = safe_int(param.get("max_scrolls"), 4, min_val=0, max_val=8)

            first_frame = _capture_720p(controller)
            if (
                _recognition_box(context, "BuyFishFoodDetailIdentity", first_frame) is not None
                and _recognition_box(context, "BuyFishFoodUnitPrice", first_frame) is not None
            ):
                print("[购买鱼食] 已在廉价鱼食详情页，跳过商品列表查找", flush=True)
                return True

            for scroll_index in range(max_scrolls + 1):
                if _task_cancelled(context):
                    print("[购买鱼食] 已收到停止请求，终止查找", flush=True)
                    return False
                frame = _capture_720p(controller)
                store_box = _recognition_box(context, "BuyFishFoodStoreIdentity", frame)
                item_box = _recognition_box(context, "BuyFishFoodStoreItemIdentity", frame)
                if store_box is None or item_box is None:
                    print("[购买鱼食] 当前页面不是已确认的商品列表，停止查找", flush=True)
                    return False

                target_box = _recognition_box(context, "BuyFishFoodTargetCard", frame)
                if target_box is not None:
                    if _task_cancelled(context):
                        print("[购买鱼食] 已收到停止请求，未点击商品", flush=True)
                        return False
                    target_x, target_y = _box_center(target_box)
                    print(f"[购买鱼食] OCR 命中廉价鱼食，点击识别框中心 ({target_x}, {target_y})", flush=True)
                    controller.post_click(target_x, target_y).wait()
                    time.sleep(1.0)
                    detail_frame = _capture_720p(controller)
                    if _recognition_box(context, "BuyFishFoodDetailIdentity", detail_frame) is not None:
                        return True
                    print("[购买鱼食] 点击后未进入廉价鱼食详情页，停止操作", flush=True)
                    return False

                if scroll_index == max_scrolls:
                    break

                print(f"[购买鱼食] 当前屏未找到廉价鱼食，向下查找 ({scroll_index + 1}/{max_scrolls})", flush=True)
                # 已由 StoreIdentity + StoreItemIdentity 双重确认商品列表，滑动轨迹只作用于商品区域。
                if _task_cancelled(context):
                    print("[购买鱼食] 已收到停止请求，未继续滑动", flush=True)
                    return False
                controller.post_swipe(640, 580, 640, 240, 400).wait()
                time.sleep(0.8)

            print("[购买鱼食] 有限次滑动后仍未找到廉价鱼食，安全停止", flush=True)
            return False
        except Exception as e:
            traceback.print_exc()
            print(f"[购买鱼食] 查找廉价鱼食异常: {e}", flush=True)
            return False


@AgentServer.custom_action("BuyCheapFishFoodAction")
class BuyCheapFishFoodAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            controller = context.tasker.controller
            if not controller:
                print("[购买鱼食] 错误: 未获取到 Controller", flush=True)
                return False

            param = parse_dict_param(argv.custom_action_param)
            bags = safe_int(param.get("bags"), 1, min_val=1, max_val=999)

            if _task_cancelled(context):
                print("[购买鱼食] 已收到停止请求，未开始购买", flush=True)
                return False

            frame = _capture_720p(controller)
            required_nodes = (
                "BuyFishFoodDetailIdentity",
                "BuyFishFoodUnitPrice",
                "BuyFishFoodPlusButton",
                "BuyFishFoodPurchaseButton",
            )
            missing = [node for node in required_nodes if _recognition_box(context, node, frame) is None]
            if missing:
                print(f"[购买鱼食] 廉价鱼食详情页门禁不完整，缺: {', '.join(missing)}", flush=True)
                return False

            current_quantity = _recognition_number(context, "BuyFishFoodQuantity", frame)
            if current_quantity is None or current_quantity < 1 or current_quantity > bags:
                print(
                    f"[购买鱼食] 当前购买数量无法安全确认（读到={current_quantity}，目标={bags}袋），未执行购买",
                    flush=True,
                )
                return False

            print(f"[购买鱼食] 已确认廉价鱼食单价 400 金币，计划购买 {bags} 袋", flush=True)
            last_hold_delta = None
            while bags - current_quantity >= (20 if last_hold_delta is None else last_hold_delta + 3):
                if _task_cancelled(context):
                    print("[购买鱼食] 已收到停止请求，终止长按", flush=True)
                    return False
                current_frame = _capture_720p(controller)
                detail_box = _recognition_box(context, "BuyFishFoodDetailIdentity", current_frame)
                plus_box = _recognition_box(context, "BuyFishFoodPlusButton", current_frame)
                if detail_box is None or plus_box is None:
                    print("[购买鱼食] 长按前页面或加号识别失败，停止操作", flush=True)
                    return False

                hold_ms = 1000 if last_hold_delta is None else min(
                    5000,
                    max(1000, int((bags - current_quantity - 3) * 1000 / last_hold_delta)),
                )
                print(f"[购买鱼食] 剩余 {bags - current_quantity} 袋，长按加号 {hold_ms}ms", flush=True)
                action_detail = context.run_action_direct(
                    JActionType.LongPress,
                    JLongPress(duration=hold_ms),
                    box=plus_box,
                )
                if _task_cancelled(context):
                    print("[购买鱼食] 长按期间收到停止请求，终止购买", flush=True)
                    return False
                if not action_detail or not action_detail.success:
                    print("[购买鱼食] 长按动作失败，停止操作", flush=True)
                    return False

                quantity_frame = _capture_720p(controller)
                new_quantity = _recognition_number(context, "BuyFishFoodQuantity", quantity_frame)
                if new_quantity is None or new_quantity <= current_quantity:
                    print("[购买鱼食] 长按后数量未可靠增加，停止操作", flush=True)
                    return False
                last_hold_delta = new_quantity - current_quantity
                current_quantity = new_quantity

            if current_quantity > bags + 2:
                print("[购买鱼食] 长按后的数量超过允许误差，未提交购买", flush=True)
                return False

            for index in range(max(0, bags - current_quantity)):
                if _task_cancelled(context):
                    print("[购买鱼食] 已收到停止请求，终止增加数量", flush=True)
                    return False
                current_frame = _capture_720p(controller)
                detail_box = _recognition_box(context, "BuyFishFoodDetailIdentity", current_frame)
                plus_box = _recognition_box(context, "BuyFishFoodPlusButton", current_frame)
                if detail_box is None or plus_box is None:
                    print(f"[购买鱼食] 第 {index + 2} 袋前页面或加号识别失败，停止操作", flush=True)
                    return False
                plus_x, plus_y = _box_center(plus_box)
                controller.post_click(plus_x, plus_y).wait()
                if _task_cancelled(context):
                    print("[购买鱼食] 点击后收到停止请求，未继续操作", flush=True)
                    return False
                time.sleep(0.15)

            if _task_cancelled(context):
                print("[购买鱼食] 已收到停止请求，未提交购买", flush=True)
                return False
            final_frame = _capture_720p(controller)
            detail_box = _recognition_box(context, "BuyFishFoodDetailIdentity", final_frame)
            price_box = _recognition_box(context, "BuyFishFoodUnitPrice", final_frame)
            purchase_box = _recognition_box(context, "BuyFishFoodPurchaseButton", final_frame)
            if detail_box is None or price_box is None or purchase_box is None:
                print("[购买鱼食] 点击购买前最终门禁失败，未提交购买", flush=True)
                return False

            purchase_x, purchase_y = _box_center(purchase_box)
            print(f"[购买鱼食] 点击识别到的购买按钮中心 ({purchase_x}, {purchase_y})", flush=True)
            controller.post_click(purchase_x, purchase_y).wait()

            store_frame = None
            store_back_box = None
            for _ in range(10):
                if _task_cancelled(context):
                    print("[购买鱼食] 已收到停止请求，终止购买后导航", flush=True)
                    return False
                time.sleep(0.3)
                candidate = _capture_720p(controller)
                candidate_back = _recognition_box(context, "BuyFishFoodStoreIdentity", candidate)
                candidate_item = _recognition_box(context, "BuyFishFoodStoreItemIdentity", candidate)
                if candidate_back is not None and candidate_item is not None:
                    store_frame = candidate
                    store_back_box = candidate_back
                    break
            if store_frame is None or store_back_box is None:
                print("[购买鱼食] 购买后未确认返回商品列表，停止操作", flush=True)
                return False

            back_x, back_y = _box_center(store_back_box)
            print(f"[购买鱼食] 商品列表已确认，点击 OCR 返回按钮中心 ({back_x}, {back_y})", flush=True)
            if _task_cancelled(context):
                print("[购买鱼食] 已收到停止请求，未点击返回", flush=True)
                return False
            controller.post_click(back_x, back_y).wait()

            for _ in range(10):
                if _task_cancelled(context):
                    print("[购买鱼食] 已收到停止请求，终止返回确认", flush=True)
                    return False
                time.sleep(0.3)
                tank_frame = _capture_720p(controller)
                if _recognition_box(context, "BuyFishFoodTankIdentity", tank_frame) is not None:
                    print("[购买鱼食] 购买流程完成，已确认返回鱼缸", flush=True)
                    return True

            print("[购买鱼食] 返回后未识别到鱼缸，停止操作", flush=True)
            return False
        except Exception as e:
            traceback.print_exc()
            print(f"[购买鱼食] 购买异常: {e}", flush=True)
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
            manatee_state["return_mode"] = "friend_gem"
            manatee_state["last_feed_count"] = 0
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


@AgentServer.custom_action("InitManateeStateAction")
class InitManateeStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            return_mode = param.get("return_mode", "standalone")
            if return_mode not in {"standalone", "friend_gem"}:
                return_mode = "standalone"
            manatee_state["return_mode"] = return_mode
            manatee_state["last_feed_count"] = 0
            print(f"[海牛先生] 任务初始化完成，返回模式: {return_mode}", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海牛先生] 初始化异常: {e}", flush=True)
            return False


@AgentServer.custom_action("FeedManateeUntilExhaustedAction")
class FeedManateeUntilExhaustedAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            max_clicks = safe_int(param.get("max_clicks"), 120, 1, 300)
            controller = context.tasker.controller
            click_points = (
                (850, 360), (962, 360), (1075, 360),
                (850, 465), (962, 465), (1075, 465),
                (850, 570), (962, 570), (1075, 570),
            )

            for click_count in range(max_clicks + 1):
                if _task_cancelled(context):
                    print("[海牛先生] 已收到停止请求，终止喂食", flush=True)
                    return False

                frame = _capture_720p(controller)
                if frame is None:
                    print("[海牛先生] 截图失败，终止喂食", flush=True)
                    return False

                # 每次投喂前先确认体力：只要识别到"0剩余"立即停止，min_clicks 旧
                # 语义（至少投 30 次后才允许判断耗尽）已移除。
                if _recognition_box(
                    context, "ManateeExhausted", frame
                ) is not None:
                    manatee_state["last_feed_count"] = click_count
                    if click_count == 0:
                        print(
                            "[海牛先生] 已确认当前体力为 0，无需投喂，准备返回。",
                            flush=True,
                        )
                    else:
                        print(
                            f"[海牛先生] 已投喂 {click_count} 次并确认体力为 0，停止继续投喂。",
                            flush=True,
                        )
                    return True

                if click_count >= max_clicks:
                    break

                if _recognition_box(context, "ManateeTankIdentity", frame) is None:
                    print("[海牛先生] 喂食前未确认仍在海牛先生页面，安全停止", flush=True)
                    return False

                x, y = click_points[click_count % len(click_points)]
                controller.post_click(x, y).wait()
                manatee_state["last_feed_count"] = click_count + 1
                if (click_count + 1) % 10 == 0:
                    print(f"[海牛先生] 已执行 {click_count + 1} 次喂食点击", flush=True)
                time.sleep(0.2)

            print(
                f"[海牛先生] 已达到 {max_clicks} 次安全上限但仍未确认体力为 0，停止操作",
                flush=True,
            )
            return False
        except Exception as e:
            traceback.print_exc()
            print(f"[海牛先生] 喂食异常: {e}", flush=True)
            return False


def detect_bite_color_geo_strict(crop: np.ndarray, early: bool = False):
    """
    钓鱼感叹号几何特征检测器：默认识别完整形态；early=True 时兼容渐入早期的小尺寸形态。
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
        if early and 12 <= h <= 95 and 5 <= w <= 40 and 1.5 <= aspect <= 5.5:
            bars.append((x, y, w, h, area))
        elif not early and 30 <= h <= 95 and 8 <= w <= 40 and 1.6 <= aspect <= 5.5:
            bars.append((x, y, w, h, area))
        elif early and 4 <= h <= 45 and 5 <= w <= 40 and 0.45 <= aspect <= 1.8:
            dots.append((x, y, w, h, area))
        elif not early and 10 <= h <= 45 and 8 <= w <= 40 and 0.5 <= aspect <= 1.8:
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


def _watch_bite_and_reel(ctrl, roi, btn_x, btn_y, timeout_sec, t_start, early_after_sec=3.0) -> bool:
    """
    通用咬钩高速监听与收杆触控内核:
    支持 Controller 容错、异常捕获、帧越界裁剪与安全退出。
    """
    time_limit = time.perf_counter() + timeout_sec
    hit_found = False
    frames_count = 0
    capture_seconds = 0.0
    detection_seconds = 0.0

    while time.perf_counter() < time_limit:
        try:
            capture_start = time.perf_counter()
            job_cap = ctrl.post_screencap()
            if not job_cap:
                print("[钓鱼达人QTE] 错误: post_screencap 返回空任务", flush=True)
                return False
            job_cap.wait()
            frame = job_cap.get()
            capture_seconds += time.perf_counter() - capture_start
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
            detection_start = time.perf_counter()
            hit, _ = detect_bite_color_geo_strict(crop)
            detection_stage = "完整形态"
            if (
                not hit
                and fishing_state.get("bite_mode", "ordinary") == "ordinary"
                and time.perf_counter() - t_start >= early_after_sec
            ):
                hit, _ = detect_bite_color_geo_strict(crop, early=True)
                detection_stage = "渐入早期形态"
            detection_seconds += time.perf_counter() - detection_start
        except Exception as e:
            print(f"[钓鱼达人QTE] 检测异常: {e}", flush=True)
            return False

        if hit and not hit_found:
            t_hit = time.perf_counter()
            hit_found = True
            print(
                f"[钓鱼达人QTE] 检测到咬钩感叹号（{detection_stage}）！"
                f"等待时长: {(t_hit - t_start):.3f}s，立即收杆！",
                flush=True,
            )
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
        elapsed = max(time.perf_counter() - t_start, 0.001)
        print(
            f"[钓鱼达人QTE] 动作成功完成 (共抓帧 {frames_count} 帧/{frames_count / elapsed:.1f} FPS，"
            f"平均截图 {capture_seconds / max(frames_count, 1) * 1000:.1f}ms，"
            f"平均检测 {detection_seconds / max(frames_count, 1) * 1000:.2f}ms)，交回 Pipeline 确认结算页面",
            flush=True,
        )
        return True
    else:
        print(f"[钓鱼达人QTE] 等待超时 ({timeout_sec:.1f}s 未检出咬钩)，安全退出", flush=True)
        return False


@AgentServer.custom_action("FishingCastAndBiteQTEAction")
class FishingCastAndBiteQTEAction(CustomAction):
    """
    钓鱼达人 QTE 自动甩收杆自定义动作:
    1. 可选上限保护: max_casts > 0 时检查硬限制，0 表示持续到鱼饵耗尽；
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

            max_casts = fishing_state.get("max_casts", 0)
            if max_casts > 0 and fishing_state["cast_count"] >= max_casts:
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
            limit_text = str(max_casts) if max_casts > 0 else "不限"
            mode_text = "普通饵食快速模式" if fishing_state.get("bite_mode") == "ordinary" else "特殊饵食稳健模式"
            print(
                f"[钓鱼达人QTE] 甩杆已完成 (当前第 {fishing_state['cast_count']}/{limit_text} 次，"
                f"{mode_text}，耗时 {(t_cast_done - t_cast_start)*1000:.1f}ms)，进入高速抓帧监听...",
                flush=True,
            )

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
            return _watch_bite_and_reel(
                ctrl, roi, btn_x, btn_y, timeout_sec, time.perf_counter(), early_after_sec=0.0
            )
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼达人中途恢复] 运行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("ResetFishingStateAction")
class ResetFishingStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            max_casts = safe_int(param.get("max_casts"), 0, min_val=0, max_val=9999)
            bite_mode = str(param.get("bite_mode", "ordinary")).strip().lower()
            if bite_mode not in ("ordinary", "special"):
                bite_mode = "ordinary"
            force_raw = param.get("force_ordinary_bait", False)
            force_ordinary_bait = force_raw is True or str(force_raw).strip().lower() in (
                "1", "true", "yes", "on"
            )

            task_detail = getattr(argv, "task_detail", None)
            task_id = int(task_detail.task_id) if task_detail and hasattr(task_detail, "task_id") else None
            fishing_state["current_task_id"] = task_id
            fishing_state["cast_count"] = 0
            fishing_state["max_casts"] = max_casts
            fishing_state["bite_mode"] = bite_mode
            fishing_state["force_ordinary_bait"] = force_ordinary_bait
            fishing_state["fish_caught"] = 0
            fishing_state["status"] = "IDLE"
            limit_text = str(max_casts) if max_casts > 0 else "不限（直到鱼饵耗尽）"
            mode_text = "普通饵食快速模式" if bite_mode == "ordinary" else "特殊饵食稳健模式（旧版严格识别）"
            print(
                f"[钓鱼达人] 状态已重置: cast_count=0, max_casts={limit_text}, "
                f"bite_mode={mode_text}, force_ordinary_bait={force_ordinary_bait} (task_id: {task_id})",
                flush=True,
            )
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼达人] 重置状态异常: {e}", flush=True)
            return False


@AgentServer.custom_action("FishingSelectOrdinaryBaitAction")
class FishingSelectOrdinaryBaitAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[钓鱼达人] 错误: 选择普通饵食时未获取到 Controller", flush=True)
                return False
            box = tuple(int(value) for value in argv.box)
            if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
                print("[钓鱼达人] ERROR: 普通饵食模板未返回有效识别框，拒绝点击", flush=True)
                return False
            bait_x, bait_y = _box_center(box)
            ctrl.post_click(bait_x, bait_y).wait()
            fishing_state["force_ordinary_bait"] = False
            print(f"[钓鱼达人] 已点击识别到的普通黄色奶酪 ({bait_x}, {bait_y})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼达人] 选择普通饵食异常: {e}", flush=True)
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
            sea_otter_gem_state["completion_reason"] = None
            sea_otter_gem_state["normal_completion"] = False
            sea_otter_gem_state["daily_count_recorded"] = False
            try:
                count = local_state.get_sea_otter_daily_count()
                limit = local_state.SEA_OTTER_DAILY_LIMIT
                local_state.write_sea_otter_status_markdown()
                try:
                    context.override_pipeline({
                        "SeaOtterStartRouter": {
                            "focus": {
                                "Node.Action.Succeeded": (
                                    f"[海獭摸宝] 今日完整运行：{count}/{limit}（04:00刷新）"
                                )
                            },
                        }
                    })
                except Exception:
                    pass
                if count >= limit:
                    print(
                        f"[海獭摸宝] 今日完整运行次数：{count}/{limit}（已达到游戏每日上限记录）",
                        flush=True,
                    )
                elif count > 0:
                    game_day = local_state.get_current_game_day()
                    print(
                        f"[海獭摸宝] 今日完整运行次数：{count}/{limit}（游戏日 {game_day}，04:00 刷新）",
                        flush=True,
                    )
                else:
                    print("[海獭摸宝] 今日完整运行次数：0/3（04:00 刷新）", flush=True)
                print("[海獭摸宝] 计数仅作记录，不阻止任务启动。", flush=True)
            except Exception as e:
                print(f"[海獭摸宝] 读取本机每日计数失败（不影响任务）: {e}", flush=True)
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
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            stay_on_current = bool(param.get("stay_on_current", False))

            otter_x, otter_y = 85, 565
            try:
                raw_box = getattr(argv, "box", None)
                box = tuple(int(value) for value in raw_box) if raw_box is not None else None
                if box and len(box) == 4 and box[2] > 0 and box[3] > 0:
                    otter_x, otter_y = _box_center(box)
            except Exception:
                otter_x, otter_y = 85, 565
            ctrl.post_touch_down(otter_x, otter_y).wait()
            time.sleep(0.08)
            ctrl.post_touch_up(0).wait()

            sea_otter_gem_state["total_harvests"] += 1
            sea_otter_gem_state["consecutive_exhausted"] = 0
            cur = sea_otter_gem_state["total_harvests"]
            limit = sea_otter_gem_state["max_harvests"]

            time.sleep(0.8)

            # 2. 依据当前 side 决定下一步导航
            if stay_on_current:
                print(
                    f"[SeaOtter] side=LEFT ui=HARVESTABLE action=HARVEST_STAY_LAST_FRIEND "
                    f"(累计摸宝: {cur}/{limit})",
                    flush=True,
                )
                sea_otter_gem_state["current_side"] = "left"
            elif side == "left":
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


@AgentServer.custom_action("SeaOtterReturnFromRecommendedAction")
class SeaOtterReturnFromRecommendedAction(CustomAction):
    """RIGHT 时返回末位好友；LEFT 时说明末位好友已耗尽，正常结束。"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[海獭摸宝] 错误: 未获取到 Controller", flush=True)
                return False
            if _task_cancelled(context):
                print("[海獭摸宝] 收到停止请求，未从推荐玩家页面继续操作", flush=True)
                return False
            if sea_otter_gem_state.get("current_side", "left") == "left":
                sea_otter_gem_state["completion_reason"] = "LAST_FRIEND_EXHAUSTED"
                sea_otter_gem_state["normal_completion"] = True
                print(
                    "[SeaOtter] side=LEFT ui=RECOMMENDED action=DONE_LAST_FRIEND_EXHAUSTED",
                    flush=True,
                )
                return True

            print("[SeaOtter] side=RIGHT ui=RECOMMENDED action=PREV_AS_LAST_FRIEND_BRIDGE", flush=True)
            ctrl.post_click(1085, 68).wait()
            sea_otter_gem_state["current_side"] = "left"
            time.sleep(2.0)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海獭摸宝] 推荐玩家桥接异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SeaOtterSwitchPairAction")
class SeaOtterSwitchPairAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # 已合流至 SeaOtterHarvestAction，保持幂等兼容
        return True


@AgentServer.custom_action("SeaOtterMarkNormalCompletionAction")
class SeaOtterMarkNormalCompletionAction(CustomAction):
    """在 Pipeline 的正常业务终点节点上显式标记"本次运行为正常完整结束"。

    仅 NORMAL 终点允许挂载本 Action；Safety Limit / 异常 / 手动停止路径
    绝不会执行到它，从根源上保证每日计数只来自正常完整运行。
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            reason = str(param.get("reason") or "NORMAL_COMPLETION")
            sea_otter_gem_state["normal_completion"] = True
            sea_otter_gem_state["completion_reason"] = reason
            print(f"[海獭摸宝] 到达正常业务终点 ({reason})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海獭摸宝] 标记正常完成异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SeaOtterFinalizeAction")
class SeaOtterFinalizeAction(CustomAction):
    """SeaOtterDone 的统一终局动作：只有正常完整结束才持久化 +1。

    幂等保护：同一次任务（daily_count_recorded）重复进入本 Action 只计一次。
    计数落盘在本机 %LOCALAPPDATA% 状态文件中，仅作记录，不拦截任务。
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            if not sea_otter_gem_state.get("normal_completion"):
                reason = sea_otter_gem_state.get("completion_reason")
                if reason and str(reason).startswith("SAFETY_"):
                    print(
                        f"[海獭摸宝] 本次因安全保护结束 ({reason})，不计入今日完整运行次数。",
                        flush=True,
                    )
                else:
                    print(
                        "[海獭摸宝] 本次未以正常业务终点结束（手动停止/异常/中断），不计入今日完整运行次数。",
                        flush=True,
                    )
                return True

            if sea_otter_gem_state.get("daily_count_recorded"):
                print("[海獭摸宝] 本次任务的完整运行计数已记录过，跳过重复计数。", flush=True)
                return True

            count, limit = local_state.record_sea_otter_completed_run()
            sea_otter_gem_state["daily_count_recorded"] = True
            local_state.write_sea_otter_status_markdown()
            try:
                context.override_pipeline({
                    "SeaOtterDoneDisplay": {
                        "focus": {
                            "Node.Action.Succeeded": (
                                f"[海獭摸宝] 本次完整运行完成，今日：{count}/{limit}"
                            )
                        },
                    }
                })
            except Exception:
                pass
            print(
                f"[海獭摸宝] 本次完整运行成功，今日计数已更新：{count}/{limit}",
                flush=True,
            )
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[海獭摸宝] 记录每日计数异常（不影响任务收尾）: {e}", flush=True)
            return True


def _reset_band_fish_state():
    band_fish_state["status"] = None
    band_fish_state["invited_slots"] = []
    band_fish_state["performance_finished"] = False
    for slot in (1, 2, 4, 5):
        band_fish_state.setdefault("slots", {}).setdefault(slot, {})["state"] = "UNKNOWN"


@AgentServer.custom_action("InitBandFishStateAction")
class InitBandFishStateAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            _reset_band_fish_state()
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


_BAND_FISH_SKIP_ROI = (1010, 575, 155, 139)
_BAND_FISH_SKIP_THRESHOLD = 0.85


def load_band_fish_skip_template() -> Optional[np.ndarray]:
    """
    加载乐队鱼“跳过”按钮模板图片。
    同时兼容开发目录与发行包目录；若文件不存在或读取失败则安全返回 None。
    """
    try:
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_dirs = [
            os.path.join(agent_dir, "../resource/image"),
            os.path.join(agent_dir, "../assets/resource/image"),
            os.path.join(agent_dir, "../../assets/resource/image"),
            os.path.abspath("assets/resource/image"),
            os.path.abspath("client_avalonia/resource/image"),
            os.path.abspath("resource/image"),
        ]
        for directory in candidate_dirs:
            template_path = os.path.abspath(os.path.join(directory, "乐队鱼_跳过.png"))
            if not os.path.isfile(template_path):
                continue
            template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if template is not None and template.size > 0:
                return template
    except Exception as e:
        print(f"[乐队鱼演出] 加载跳过模板异常: {e}", flush=True)
    return None


def check_band_fish_skip_button(frame: Optional[np.ndarray]) -> Optional[Tuple[int, int]]:
    """
    检测乐队鱼演出界面的“跳过”按钮中心坐标 (x, y)。
    只在用户提供的 ROI EX [1010, 575, 155, 139] 内进行模板匹配。
    未识别到模板时安全返回 None，严禁猜测固定坐标或盲点。
    """
    if frame is None:
        return None
    try:
        height, width = frame.shape[:2]
        if width != 1280 or height != 720:
            frame = cv2.resize(frame, (1280, 720))

        template = load_band_fish_skip_template()
        if template is None:
            return None

        roi_x, roi_y, roi_w, roi_h = _BAND_FISH_SKIP_ROI
        search = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
        template_h, template_w = template.shape[:2]
        if search.size == 0 or template_w > search.shape[1] or template_h > search.shape[0]:
            return None

        result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_loc = cv2.minMaxLoc(result)
        if max_score >= _BAND_FISH_SKIP_THRESHOLD:
            return (
                roi_x + max_loc[0] + template_w // 2,
                roi_y + max_loc[1] + template_h // 2,
            )
    except Exception as e:
        print(f"[乐队鱼演出] 识别跳过按钮异常: {e}", flush=True)
    return None


def _band_fish_score_candidates(context: Context, frame, expected: str = ".+"):
    """读取选曲列表中的 OCR 结果，返回 [(name, box), ...]。"""
    if frame is None or not hasattr(context, "run_recognition"):
        return []
    result = context.run_recognition(
        "BandFishScoreName",
        frame,
        pipeline_override={"BandFishScoreName": {"expected": expected}},
    )
    if not result:
        return []

    items = getattr(result, "filtered_results", None) or []
    candidates = []
    for item in items:
        text = str(getattr(item, "text", "")).strip()
        box = getattr(item, "box", None)
        if not text or box is None:
            continue
        try:
            x, y, width, height = (int(value) for value in box)
        except (TypeError, ValueError):
            continue
        center_x = x + width // 2
        center_y = y + height // 2
        if 650 <= center_x <= 870 and 180 <= center_y <= 650:
            candidates.append((text, (x, y, width, height)))
    return candidates


def _band_fish_score_is_selected(frame, score_box) -> bool:
    """检测乐章卡片右侧的黄色选中箭头，确认选曲点击确实生效。"""
    if frame is None or score_box is None:
        return False
    _, y, _, _ = score_box
    height, width = frame.shape[:2]
    x1, x2 = max(0, 835), min(width, 868)
    y1, y2 = max(0, y - 85), min(height, y - 25)
    if x2 <= x1 or y2 <= y1:
        return False
    hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, np.array([10, 120, 140]), np.array([45, 255, 255]))
    return int(np.count_nonzero(yellow)) >= 200


def _band_fish_score_view_difference(before, after) -> float:
    if before is None or after is None:
        return float("inf")
    before_roi = before[180:650, 650:870]
    after_roi = after[180:650, 650:870]
    if before_roi.shape != after_roi.shape or before_roi.size == 0:
        return float("inf")
    return float(np.mean(cv2.absdiff(before_roi, after_roi)))


@AgentServer.custom_action("BandFishPerformAction")
class BandFishPerformAction(CustomAction):
    """
    乐队鱼核心演出闭环动作 (Pass 2):
    职责分工:
    1. 开始演出: 识别底部绿色“开始演出”按钮后点击;
    2. 选曲确认: 选择最新乐章或指定乐章，验证黄色选中态后才点击【确定】消耗体力;
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

            param = parse_dict_param(argv.custom_action_param)
            score_mode = str(param.get("score_mode", "latest")).strip().lower()
            score_name = str(param.get("score_name", "欢乐颂")).strip()
            score_ocr_keyword = str(param.get("score_ocr_keyword", score_name)).strip()
            if (
                score_mode not in ("latest", "named")
                or (score_mode == "named" and (not score_name or not score_ocr_keyword))
            ):
                print("[乐队鱼演出] 错误: 乐章配置无效，未开始演出", flush=True)
                return False

            score_label = "最新乐章" if score_mode == "latest" else f"指定乐章【{score_name}】"
            print(f"[乐队鱼演出] 检测到全员就绪，准备选择{score_label}...", flush=True)

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

            # 职责 1: 验证当前处于“开始演出”状态并点击，识别失败绝不盲点。
            f_init = capture_frame()
            ready_box = _recognition_box(context, "BandFishCheckReady", f_init)
            if ready_box is None:
                print("[乐队鱼演出] 错误: 未确认当前页面的“开始演出”按钮，安全停止", flush=True)
                return False
            btn_x, btn_y = _box_center(ready_box)
            print(f"[乐队鱼演出] 识别到“开始演出”按钮中心: ({btn_x}, {btn_y})", flush=True)

            print(f"[乐队鱼演出] 点击【开始演出】按钮 ({btn_x}, {btn_y})...", flush=True)
            ctrl.post_click(btn_x, btn_y).wait()
            time.sleep(1.8)

            # 职责 2: 必须同时识别弹窗标题和确定按钮，才允许在列表内操作。
            t_dlg = time.time()
            f_dlg = None
            confirm_box = None
            while time.time() - t_dlg < 5.0:
                candidate = capture_frame()
                if candidate is None:
                    time.sleep(0.3)
                    continue
                title_box = _recognition_box(context, "BandFishScoreDialogTitle", candidate)
                candidate_confirm = _recognition_box(context, "BandFishScoreConfirm", candidate)
                if title_box is not None and candidate_confirm is not None:
                    f_dlg = candidate
                    confirm_box = candidate_confirm
                    break
                time.sleep(0.4)

            if f_dlg is None or confirm_box is None:
                print("[乐队鱼演出] 错误: 未同时识别选曲弹窗标题与“确定”按钮，未消耗体力", flush=True)
                return False

            target_name = score_name
            target_box = None

            if score_mode == "latest":
                # 已确认选曲弹窗后，手势被限制在乐章列表内；滑到底部后选择最下方完整乐章。
                previous = f_dlg
                bottom_confirmed = False
                for swipe_index in range(8):
                    if _task_cancelled(context):
                        print("[乐队鱼演出] 已收到停止请求，未继续选曲", flush=True)
                        return False
                    ctrl.post_swipe(750, 590, 750, 250, 450).wait()
                    time.sleep(0.7)
                    current = capture_frame()
                    if (
                        _recognition_box(context, "BandFishScoreDialogTitle", current) is None
                        or _recognition_box(context, "BandFishScoreConfirm", current) is None
                    ):
                        print("[乐队鱼演出] 错误: 下滑后选曲弹窗门禁丢失，未消耗体力", flush=True)
                        return False
                    diff = _band_fish_score_view_difference(previous, current)
                    print(f"[乐队鱼演出] 下滑查找最新乐章 {swipe_index + 1}/8，列表变化={diff:.2f}", flush=True)
                    f_dlg = current
                    if diff <= 1.0:
                        bottom_confirmed = True
                        break
                    previous = current

                candidates = _band_fish_score_candidates(context, f_dlg)
                if not bottom_confirmed or not candidates:
                    print("[乐队鱼演出] 错误: 未确认已到达乐章列表底部，未消耗体力", flush=True)
                    return False
                target_name, target_box = max(candidates, key=lambda item: item[1][1])
                if target_box[1] + target_box[3] > 560:
                    print("[乐队鱼演出] 错误: 列表底部仍有被截断的乐章，拒绝猜测最新乐章", flush=True)
                    return False
            else:
                # 指定乐章先检查当前页；未命中则回到顶部，再逐页向下查找。
                score_expected = f".*{re.escape(score_ocr_keyword)}.*"
                candidates = _band_fish_score_candidates(context, f_dlg, score_expected)
                if candidates:
                    _, target_box = candidates[0]

                previous = f_dlg
                for _ in range(8):
                    if target_box is not None:
                        break
                    if _task_cancelled(context):
                        print("[乐队鱼演出] 已收到停止请求，未继续查找指定乐章", flush=True)
                        return False
                    ctrl.post_swipe(750, 250, 750, 590, 450).wait()
                    time.sleep(0.7)
                    current = capture_frame()
                    if (
                        _recognition_box(context, "BandFishScoreDialogTitle", current) is None
                        or _recognition_box(context, "BandFishScoreConfirm", current) is None
                    ):
                        print("[乐队鱼演出] 错误: 回到乐章列表顶部时弹窗门禁丢失，未消耗体力", flush=True)
                        return False
                    f_dlg = current
                    candidates = _band_fish_score_candidates(context, f_dlg, score_expected)
                    if candidates:
                        _, target_box = candidates[0]
                        break
                    diff = _band_fish_score_view_difference(previous, current)
                    previous = current
                    if diff <= 1.0:
                        break

                for _ in range(8):
                    if target_box is not None:
                        break
                    if _task_cancelled(context):
                        print("[乐队鱼演出] 已收到停止请求，未继续查找指定乐章", flush=True)
                        return False
                    ctrl.post_swipe(750, 590, 750, 250, 450).wait()
                    time.sleep(0.7)
                    current = capture_frame()
                    if (
                        _recognition_box(context, "BandFishScoreDialogTitle", current) is None
                        or _recognition_box(context, "BandFishScoreConfirm", current) is None
                    ):
                        print("[乐队鱼演出] 错误: 下滑查找指定乐章时弹窗门禁丢失，未消耗体力", flush=True)
                        return False
                    f_dlg = current
                    candidates = _band_fish_score_candidates(context, f_dlg, score_expected)
                    if candidates:
                        _, target_box = candidates[0]
                        break
                    diff = _band_fish_score_view_difference(previous, current)
                    previous = current
                    if diff <= 1.0:
                        break

            if target_box is None:
                print(f"[乐队鱼演出] 错误: OCR 未找到{score_label}，未消耗体力", flush=True)
                return False

            target_x, target_y = _box_center(target_box)
            print(f"[乐队鱼演出] OCR 定位乐章【{target_name}】于 ({target_x}, {target_y})，执行选择", flush=True)
            ctrl.post_click(target_x, target_y).wait()
            time.sleep(0.6)

            selected_frame = capture_frame()
            selected_expected = score_expected if score_mode == "named" else target_name
            selected_candidates = _band_fish_score_candidates(context, selected_frame, selected_expected)
            selected_box = selected_candidates[0][1] if selected_candidates else None
            if not _band_fish_score_is_selected(selected_frame, selected_box):
                print(f"[乐队鱼演出] 错误: 未确认【{target_name}】黄色选中态，未点击确定、未消耗体力", flush=True)
                return False
            if (
                _recognition_box(context, "BandFishScoreDialogTitle", selected_frame) is None
                or _recognition_box(context, "BandFishScoreConfirm", selected_frame) is None
            ):
                print("[乐队鱼演出] 错误: 选中后弹窗门禁不完整，未消耗体力", flush=True)
                return False
            if _task_cancelled(context):
                print("[乐队鱼演出] 已收到停止请求，未点击消耗体力的确定按钮", flush=True)
                return False

            confirm_x, confirm_y = _box_center(confirm_box)
            print(f"[乐队鱼演出] 已确认选中【{target_name}】，点击识别到的【确定】按钮 ({confirm_x}, {confirm_y}) 开始演出...", flush=True)
            ctrl.post_click(confirm_x, confirm_y).wait()
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
            elif not settlement_detected:
                print("[乐队鱼演出] 错误: 未识别到结算弹窗或返场状态，拒绝盲点结算区域", flush=True)
                return False

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

            def cancelled(stage):
                if not _task_cancelled(context):
                    return False
                print(f"[乐队鱼邀请] 收到停止请求，已在【{stage}】停止后续点击与滑动", flush=True)
                return True

            if cancelled("开始邀请前"):
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

            gate_frame = capture_frame()
            if gate_frame is None or not is_on_stage(gate_frame):
                print("[乐队鱼邀请] 当前不在乐队鱼舞台，拒绝把空槽当成邀请完成。", flush=True)
                return False

            round_count = 0
            while time.time() - t_start < max_loop_duration:
                if cancelled("槽位扫描"):
                    return False
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
                if cancelled(f"点击槽位 {target_slot} 邀请按钮前"):
                    return False
                ctrl.post_click(btn_x, btn_y).wait()

                # 1. 动态等待好友选择弹窗打开
                dialog_opened = False
                t_open = time.time()
                while time.time() - t_open < 4.5:
                    if cancelled("等待好友选择弹窗"):
                        return False
                    time.sleep(0.3)
                    f_diag = capture_frame()
                    if f_diag is not None and is_friend_dialog_open(f_diag):
                        dialog_opened = True
                        break

                if not dialog_opened:
                    print(f"[乐队鱼邀请] 点击槽位 {target_slot} 后未检测到好友选择弹窗打开，重试...", flush=True)
                    continue

                print(f"[乐队鱼邀请] 好友选择弹窗已打开，等待 1 秒让首屏列表稳定...", flush=True)
                time.sleep(1.0)
                if cancelled("等待好友列表稳定"):
                    return False
                f_diag = capture_frame()
                if f_diag is None or not is_friend_dialog_open(f_diag):
                    print(f"[乐队鱼邀请] 等待后好友选择弹窗门禁丢失，返回舞台重新扫描...", flush=True)
                    continue

                print(f"[乐队鱼邀请] 首屏列表已稳定，开始 OCR 匹配指定人机好友【{target_name}】...", flush=True)

                # 2. 对当前页面执行纯列表 OCR 匹配目标好友
                card_box, seen_texts = _band_fish_locate_target_card(context, f_diag, target_name)

                # 3. 若当前屏未匹配到，向上滑动卡片列表寻找（严禁使用搜索框）
                scroll_count = 0
                f_cur = f_diag
                while card_box is None and scroll_count < 2:
                    if cancelled("滑动好友列表前"):
                        return False
                    scroll_count += 1
                    print(f"[乐队鱼邀请] 当前页面未检出【{target_name}】，向上滑动列表检索更多卡片 (第 {scroll_count}/2 次)...", flush=True)
                    ctrl.post_swipe(640, 520, 640, 260, 400).wait()
                    time.sleep(1.0)
                    f_cur = capture_frame()
                    if f_cur is not None:
                        card_box, current_texts = _band_fish_locate_target_card(context, f_cur, target_name)
                        for text in current_texts:
                            if text not in seen_texts:
                                seen_texts.append(text)

                # 4. 严苛防线：若列表 OCR 遍历后仍未定位到目标好友，立即安全熔断退出，绝不点击任何其他好友！
                if card_box is None:
                    print(f"[乐队鱼邀请] OCR 候选文本: {seen_texts or ['<无>']}", flush=True)
                    print(f"[乐队鱼邀请] 严重警告: 列表 OCR 遍历后未匹配到指定人机好友【{target_name}】！触发安全熔断，放弃邀请以防误触！", flush=True)
                    if cancelled("安全退出好友列表前"):
                        return False
                    ctrl.post_click(91, 46).wait()
                    time.sleep(1.2)
                    continue

                # 5. 命中目标好友，点击文字中心 (cx, cy)
                bx, by, bw, bh = card_box
                cx, cy = bx + bw // 2, by + bh // 2
                print(f"[乐队鱼邀请] 列表 OCR 命中目标好友【{target_name}】: bbox=({bx}, {by}, {bw}, {bh})，点击中心 ({cx}, {cy})...", flush=True)
                if cancelled(f"点击好友【{target_name}】前"):
                    return False
                ctrl.post_click(cx, cy).wait()
                time.sleep(0.6)

                # 6. 核验选中状态（底部确认按钮必须变绿）
                f_check = capture_frame()
                if f_check is None or not is_confirm_green(f_check):
                    print(f"[乐队鱼邀请] 警告: 点击【{target_name}】后底部确认按钮未变绿，核验失败！点击返回退出", flush=True)
                    if cancelled("选中核验失败退出前"):
                        return False
                    ctrl.post_click(91, 46).wait()
                    time.sleep(1.0)
                    continue

                print(f"[乐队鱼邀请] 目标好友【{target_name}】选定核验通过，底部确认按钮已变绿！", flush=True)

                # 7. 点击底部绿色“邀请”确认按钮 (921, 664)
                print("[乐队鱼邀请] 点击底部绿色确认按钮 (921, 664) 发出邀请...", flush=True)
                if cancelled(f"确认邀请【{target_name}】前"):
                    return False
                ctrl.post_click(921, 664).wait()

                # 8. 动态等待：弹窗关闭 + 回到舞台 + 该槽位绿色邀请按钮消失
                t_close = time.time()
                slot_finished = False
                while time.time() - t_close < 6.0:
                    if cancelled("等待邀请结果"):
                        return False
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

            if cancelled("邀请循环结束"):
                return False
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
    点击当前页面真实识别到的钓鱼达人退出按钮。

    钓场退出后会先回到地点页，因此这里只负责第一次点击，不提前把
    日常收尾推进到下一项；最终状态由 FishingDoneAction 在确认主鱼缸后写入。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[钓鱼退出] 错误: 未获取到 Controller", flush=True)
                return False

            try:
                exit_box = tuple(int(value) for value in argv.box)
                if len(exit_box) != 4 or exit_box[2] <= 0 or exit_box[3] <= 0:
                    raise ValueError("invalid recognition box")
            except (AttributeError, TypeError, ValueError):
                print("[钓鱼退出] ERROR: 未取得有效的退出按钮识别框，拒绝盲点点击", flush=True)
                return False
            exit_x, exit_y = _box_center(exit_box)

            print(
                f"[钓鱼退出] 点击识别到的钓场退出按钮 ({exit_x}, {exit_y})，准备返回地点页...",
                flush=True,
            )
            ctrl.post_click(exit_x, exit_y).wait()
            time.sleep(1.8)

            print("[钓鱼退出] 已退出钓场，正在识别地点页退出按钮...", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼退出] 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("FishingDoneAction")
class FishingDoneAction(CustomAction):
    """确认已经回到主鱼缸后沉淀钓鱼结果，并按独立/日常模式结束。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            casts = fishing_state.get("cast_count", 0)
            max_casts = fishing_state.get("max_casts", 0)
            status = "DONE" if max_casts == 0 or casts >= max_casts else "NO_STAMINA"
            fishing_state["status"] = status
            print(
                f"[钓鱼退出] 已确认返回主鱼缸；业务状态={status}，完成杆数={casts}/"
                f"{'不限' if max_casts == 0 else max_casts}",
                flush=True,
            )
            if daily_routine_state.get("active"):
                advance_daily_routine_step("Fishing", status)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼退出] 完成状态写入异常: {e}", flush=True)
            return False


# ==============================================================================
# 宝石礼盒七配方兑换
# ==============================================================================

GEM_GIFT_BOX_LEVELS = (16, 21, 26, 31, 36, 41, 46)


def _gem_gift_box_recognition_box(context: Context, node_name: str, frame, override=None):
    if frame is None or not hasattr(context, "run_recognition"):
        return None
    result = context.run_recognition(node_name, frame, pipeline_override=override or {})
    if not result or not result.hit or result.box is None:
        return None
    try:
        return tuple(int(value) for value in result.box)
    except (TypeError, ValueError):
        return None


def _gem_gift_box_card_roi(recipe_box, kind: str):
    """根据配方文字所在卡片推导同卡片的 OK 或今日兑换计数范围。"""
    x, y, width, height = recipe_box
    is_left = x + width // 2 < 640
    if kind == "marker":
        # 用户给定基准：左列配方 [55,196,108,41] -> OK [587,195,47,35]。
        # 右列 OK 实机约 x=1199，宽度约 40，放宽为 [1180, ..., 80, ...] 避免左侧裁切。
        marker_x = 587 if is_left else 1180
        marker_width = 47 if is_left else 80
        marker_y = max(150, y - 25)
        return [marker_x, marker_y, marker_width, min(80, 720 - marker_y)]

    count_x = 0 if is_left else 640
    count_y = max(150, min(690, y + 60))
    return [count_x, count_y, 640, min(150, 720 - count_y)]


def _gem_gift_box_card_click_point(recipe_box, marker_box):
    """点击配方文字与同卡片 OK 标志的中心点，避免直接点击状态标志。"""
    recipe_x, recipe_y, recipe_width, recipe_height = recipe_box
    marker_x, marker_y, marker_width, marker_height = marker_box
    click_x = int(
        ((recipe_x + recipe_width / 2) + (marker_x + marker_width / 2)) / 2 + 0.5
    )
    click_y = int(
        ((recipe_y + recipe_height / 2) + (marker_y + marker_height / 2)) / 2 + 0.5
    )
    return click_x, click_y


@AgentServer.custom_action("GemGiftBoxExchangeAllAction")
class GemGiftBoxExchangeAllAction(CustomAction):
    """按配方等级逐一完成七张宝石礼盒卡片，使用每日 10/10 状态防重。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[宝石礼盒] 错误: 未获取到 Controller", flush=True)
                return False

            def cancelled(stage):
                if not _task_cancelled(context):
                    return False
                print(f"[宝石礼盒] 已收到停止请求，终止阶段: {stage}", flush=True)
                return True

            def capture_page():
                frame = _capture_720p(ctrl)
                if frame is None:
                    print("[宝石礼盒] 截屏失败", flush=True)
                    return None
                if _recognition_box(context, "GemGiftBoxRun", frame) is None:
                    print("[宝石礼盒] 当前画面未通过兑换列表页面门禁", flush=True)
                    return None
                return frame

            def wait_for(node_name, timeout_seconds):
                deadline = time.time() + timeout_seconds
                while time.time() < deadline:
                    if cancelled(f"等待 {node_name}"):
                        return None, None
                    frame = _capture_720p(ctrl)
                    box = _recognition_box(context, node_name, frame)
                    if box is not None:
                        return frame, box
                    time.sleep(0.25)
                return None, None

            # 只看真实顶部锚点决定是否继续回滚，不依赖上一次滚动位置。
            top_frame = None
            for attempt in range(5):
                if cancelled("列表回到顶部"):
                    return False
                frame = capture_page()
                if frame is None:
                    return False
                if _recognition_box(context, "GemGiftBoxTopRecipe", frame) is not None:
                    top_frame = frame
                    print(f"[宝石礼盒] 已确认列表顶部（回滚 {attempt} 次）", flush=True)
                    break
                if attempt == 4:
                    break
                print(f"[宝石礼盒] 未见 16级配方，向页面顶部回滚 ({attempt + 1}/4)", flush=True)
                ctrl.post_swipe(640, 240, 640, 620, 450).wait()
                time.sleep(0.8)
            if top_frame is None:
                print("[宝石礼盒] 回滚后仍未识别到 16级配方，安全停止", flush=True)
                return False

            def locate_recipe(level):
                expected = f"{level}级配方"
                for swipe_index in range(5):
                    if cancelled(f"查找 {expected}"):
                        return None, None
                    frame = capture_page()
                    if frame is None:
                        return None, None
                    box = _gem_gift_box_recognition_box(
                        context,
                        "GemGiftBoxRecipeLabel",
                        frame,
                        {"GemGiftBoxRecipeLabel": {"expected": expected}},
                    )
                    if box is not None and box[1] + box[3] // 2 <= 570:
                        return frame, box
                    if swipe_index == 4:
                        break
                    print(f"[宝石礼盒] 当前视区未完整显示 {expected}，向下查找 ({swipe_index + 1}/4)", flush=True)
                    ctrl.post_swipe(640, 610, 640, 260, 450).wait()
                    time.sleep(0.8)
                return None, None

            def is_completed(frame, recipe_box):
                count_roi = _gem_gift_box_card_roi(recipe_box, "count")
                override = {
                    "GemGiftBoxCompletedCount": {
                        "expected": ".*兑换.*10/10.*",
                        "roi": count_roi,
                    }
                }
                return _gem_gift_box_recognition_box(
                    context, "GemGiftBoxCompletedCount", frame, override
                ) is not None

            completed_levels = []
            full_exchanged_levels = []
            partial_exchanged_levels = []
            unavailable_levels = []
            for level in GEM_GIFT_BOX_LEVELS:
                frame, recipe_box = locate_recipe(level)
                if frame is None or recipe_box is None:
                    print(f"[宝石礼盒] 未定位到 {level}级配方，停止以避免漏兑", flush=True)
                    return False

                already_done = False
                for check_index in range(3):
                    if is_completed(frame, recipe_box):
                        already_done = True
                        break
                    if check_index < 2:
                        time.sleep(0.35)
                        frame = capture_page()
                        if frame is None:
                            return False
                if already_done:
                    completed_levels.append(level)
                    print(f"[宝石礼盒] {level}级配方今日已兑换 10/10，跳过且不重复点击 OK", flush=True)
                    continue

                marker_roi = _gem_gift_box_card_roi(recipe_box, "marker")
                marker_box = None
                for check_index in range(3):
                    marker_box = _gem_gift_box_recognition_box(
                        context,
                        "GemGiftBoxExchangeableMarker",
                        frame,
                        {"GemGiftBoxExchangeableMarker": {"roi": marker_roi}},
                    )
                    if marker_box is not None:
                        break
                    if check_index < 2:
                        time.sleep(0.35)
                        frame = capture_page()
                        if frame is None:
                            return False
                if marker_box is None:
                    unavailable_levels.append(level)
                    print(
                        f"[宝石礼盒] {level}级配方今日未满 10/10，但当前无可兑换 OK；"
                        f"视为本次不可兑换，跳过并继续下一配方",
                        flush=True,
                    )
                    continue

                card_x, card_y = _gem_gift_box_card_click_point(recipe_box, marker_box)
                if cancelled(f"点击 {level}级配方卡片"):
                    return False
                print(
                    f"[宝石礼盒] {level}级配方未满 10/10，已识别同卡片 OK；"
                    f"点击配方文字与 OK 的中点 ({card_x}, {card_y})",
                    flush=True,
                )
                ctrl.post_click(card_x, card_y).wait()

                dialog_frame, _ = wait_for("GemGiftBoxExchangeDialog", 5.0)
                if dialog_frame is None:
                    print(f"[宝石礼盒] 点击 {level}级配方后未确认兑换弹窗，安全停止", flush=True)
                    return False
                plus_box = _recognition_box(context, "GemGiftBoxPlusButton", dialog_frame)
                if plus_box is None:
                    print(f"[宝石礼盒] {level}级配方兑换弹窗未识别到加号，安全停止", flush=True)
                    return False

                plus_x, plus_y = _box_center(plus_box)
                print(f"[宝石礼盒] {level}级配方点击加号 9 次，将数量提高到本日剩余上限", flush=True)
                for click_index in range(9):
                    if cancelled(f"{level}级配方增加数量 {click_index + 1}/9"):
                        return False
                    ctrl.post_click(plus_x, plus_y).wait()
                    time.sleep(0.22)

                submit_frame = _capture_720p(ctrl)
                submit_box = _recognition_box(context, "GemGiftBoxExchangeButton", submit_frame)
                if submit_box is None:
                    print(f"[宝石礼盒] {level}级配方未识别到兑换按钮，未提交", flush=True)
                    return False
                submit_x, submit_y = _box_center(submit_box)
                print(f"[宝石礼盒] {level}级配方数量设置完成，点击识别到的兑换按钮", flush=True)
                ctrl.post_click(submit_x, submit_y).wait()

                _, confirm_box = wait_for("GemGiftBoxConfirmButton", 4.0)
                if confirm_box is None:
                    print(f"[宝石礼盒] {level}级配方未识别到结果确定按钮，安全停止", flush=True)
                    return False
                confirm_x, confirm_y = _box_center(confirm_box)
                print(f"[宝石礼盒] {level}级配方兑换结果已出现，点击确定", flush=True)
                ctrl.post_click(confirm_x, confirm_y).wait()

                returned = False
                for _ in range(12):
                    if cancelled(f"等待 {level}级配方返回列表"):
                        return False
                    time.sleep(0.25)
                    verify_frame = _capture_720p(ctrl)
                    if _recognition_box(context, "GemGiftBoxRun", verify_frame) is not None:
                        returned = True
                        break
                if not returned:
                    print(f"[宝石礼盒] {level}级配方确认后未返回兑换列表，安全停止", flush=True)
                    return False

                verified_full = False
                for verify_index in range(3):
                    if is_completed(verify_frame, recipe_box):
                        verified_full = True
                        break
                    if verify_index < 2:
                        time.sleep(0.4)
                        verify_frame = capture_page()
                        if verify_frame is None:
                            return False

                if verified_full:
                    full_exchanged_levels.append(level)
                    print(f"[宝石礼盒] {level}级配方已确认今日兑换 10/10，继续下一配方", flush=True)
                else:
                    partial_exchanged_levels.append(level)
                    print(
                        f"[宝石礼盒] {level}级配方兑换事务已成功完成，但今日尚未达到 10/10；"
                        f"视为部分兑换成功，本轮不重复提交，继续下一配方",
                        flush=True,
                    )

            print(
                f"[宝石礼盒] 七配方检查完成；"
                f"此前已满={completed_levels}，"
                f"本轮兑满={full_exchanged_levels}，"
                f"本轮部分兑换={partial_exchanged_levels}，"
                f"本轮不可兑换={unavailable_levels}",
                flush=True,
            )
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[宝石礼盒] 执行异常: {e}", flush=True)
            return False


# ==============================================================================
# 金海豚小游戏基础设施与 Action 拆分 (Phase 2A-1)
# ==============================================================================

GOLDEN_DOLPHIN_REWARD_ORDER = ("xp", "heart", "gem", "coin")
GOLDEN_DOLPHIN_REWARD_NAMES = {
    "xp": "经验星",
    "heart": "爱心",
    "gem": "宝石",
    "coin": "贝币",
}

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

    def _load_templates(*names: str):
        return tuple(
            template
            for template in (_load_tpl(name) for name in names)
            if template is not None and template.size > 0
        )

    activation_coin = _load_templates("金海豚_贝币.png")
    reward_templates = {
        "xp": _load_templates("金海豚_经验星1.png", "金海豚_经验星2.png"),
        "heart": _load_templates("金海豚_爱心.png"),
        "gem": _load_templates(
            "金海豚_宝石1.png",
            "金海豚_宝石2.png",
            "金海豚_宝石3.png",
            "金海豚_宝石4.png",
        ),
        "coin": _load_templates(
            "金海豚_贝币.png",
            "金海豚_贝币1.png",
            "金海豚_贝币2.png",
        ),
    }
    return {
        "tpl_dir": tpl_dir,
        "entrance": _load_tpl("游乐园入口.png"),
        "dolphin": _load_tpl("金海豚_图标.png"),
        "confirm": _load_tpl("金海豚_确定按钮.png"),
        "main": _load_tpl("主界面特征.png"),
        "rewards": reward_templates,
        "activation_coin": activation_coin,
        "coins": reward_templates["coin"],
        "hearts": reward_templates["heart"],
        "gems": reward_templates["gem"],
        "stars": reward_templates["xp"],
        "cancel": _load_tpl("金海豚_结束取消.png"),
    }


def _find_golden_dolphin_template_targets(frame, templates, threshold: float = 0.70):
    """在完整画面识别同类奖励的全部模板变体，并合并同一目标的重复命中。"""
    if isinstance(templates, np.ndarray):
        templates = (templates,)
    templates = tuple(
        template for template in (templates or ())
        if template is not None and template.size > 0
    )
    if frame is None or not templates:
        return []
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))

    raw = []
    for template in templates:
        template_h, template_w = template.shape[:2]
        if template_h > frame.shape[0] or template_w > frame.shape[1]:
            continue
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= threshold)
        raw.extend(
            (
                int(x + template_w // 2),
                int(y + template_h // 2),
                float(result[y, x]),
                template_w,
                template_h,
            )
            for y, x in zip(ys, xs)
        )

    candidates = []
    for x, y, score, width, height in sorted(raw, key=lambda item: item[2], reverse=True):
        if any(
            abs(x - selected_x) < max(width, selected_width) * 0.65
            and abs(y - selected_y) < max(height, selected_height) * 0.65
            for selected_x, selected_y, _, selected_width, selected_height in candidates
        ):
            continue
        candidates.append((x, y, score, width, height))
    return [
        (x, y, score)
        for x, y, score, _, _ in sorted(
            candidates,
            key=lambda candidate: (candidate[1], candidate[2]),
            reverse=True,
        )
    ]


def _find_golden_dolphin_activation_coin(frame, template, threshold: float = 0.70):
    """隐藏启动专用：在 y=120~650 ROI 内取最高置信度的唯一贝币。

    恢复 v0.5.1~v0.5.5 已实机验证的选择语义（ROI 先验排除顶部 HUD 与底部
    栏的边缘伪命中；minMaxLoc 只选 ROI 内最高分，而非全屏候选按 y 降序的
    bottom-most）。仅用于游戏尚未激活时的 activation 点击。
    """
    if frame is None or template is None or template.size == 0:
        return None
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))
    roi_top, roi_bottom = 120, 650
    search = frame[roi_top:roi_bottom]
    template_h, template_w = template.shape[:2]
    if template_h > search.shape[0] or template_w > search.shape[1]:
        return None
    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    if score < threshold:
        return None
    return (
        location[0] + template_w // 2,
        roi_top + location[1] + template_h // 2,
        float(score),
    )


def _find_golden_dolphin_coin(frame, templates, threshold: float = 0.70):
    """兼容旧调用：返回全屏识别到的首个贝币；未命中时不猜坐标。"""
    candidates = _find_golden_dolphin_template_targets(frame, templates, threshold)
    return candidates[0] if candidates else None


def _find_golden_dolphin_xp(frame, templates):
    """使用任一经验星模板识别候选，按接近底部优先且不重复点击。"""
    if isinstance(templates, np.ndarray):
        templates = (templates,)
    templates = tuple(
        template for template in (templates or ())
        if template is not None and template.size > 0
    )
    if frame is None or not templates:
        return []
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))

    playfield = frame
    hsv = cv2.cvtColor(playfield, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([15, 65, 110]), np.array([35, 255, 255]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    template_sizes = [(template, *template.shape[:2]) for template in templates]
    min_width = max(20, int(min(width for _, _, width in template_sizes) * 0.65))
    max_width = max(78, int(max(width for _, _, width in template_sizes) * 1.25))
    min_height = max(20, int(min(height for _, height, _ in template_sizes) * 0.65))
    max_height = max(78, int(max(height for _, height, _ in template_sizes) * 1.25))
    min_area = min(950, int(min(height * width for _, height, width in template_sizes) * 0.20))
    max_area = max(3300, int(max(height * width for _, height, width in template_sizes) * 0.90))
    candidates = []

    for contour in contours:
        area = cv2.contourArea(contour)
        x, y_local, width, height = cv2.boundingRect(contour)
        aspect_ratio = width / float(height) if height > 0 else 0
        if not (
            min_area <= area <= max_area
            and 0.75 <= aspect_ratio <= 1.35
            and min_width <= width <= max_width
            and min_height <= height <= max_height
        ):
            continue

        center_x = x + width // 2
        center_y = y_local + height // 2

        best_score = 0.0
        for template, template_h, template_w in template_sizes:
            left = center_x - template_w // 2
            top = center_y - template_h // 2
            right = left + template_w
            bottom = top + template_h
            if left < 0 or top < 0 or right > frame.shape[1] or bottom > frame.shape[0]:
                continue
            patch = frame[top:bottom, left:right]
            score = float(cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED)[0, 0])
            best_score = max(best_score, score)
        if best_score >= 0.45:
            candidates.append((center_x, center_y, best_score))

    return sorted(candidates, key=lambda candidate: (candidate[1], candidate[2]), reverse=True)


def _find_golden_dolphin_hearts(frame, templates, threshold: float = 0.70):
    return _find_golden_dolphin_template_targets(frame, templates, threshold)


def _select_golden_dolphin_frame_targets(
    frame,
    reward_templates,
    priority: str = "xp",
):
    """同一帧先找用户最高优先级；未命中就立即检查其余奖励。"""
    if priority not in GOLDEN_DOLPHIN_REWARD_ORDER:
        priority = "xp"
    search_order = (priority,) + tuple(
        category for category in GOLDEN_DOLPHIN_REWARD_ORDER if category != priority
    )
    for category in search_order:
        templates = reward_templates.get(category, ())
        if category == "xp":
            candidates = _find_golden_dolphin_xp(frame, templates)
        else:
            candidates = _find_golden_dolphin_template_targets(frame, templates)
        if candidates:
            return category, candidates[:4]
    return "wait", []


def _collect_golden_dolphin_frame_targets(
    frame,
    reward_templates,
    priority: str = "xp",
    max_targets: int = 4,
):
    """一帧内收集多种奖励，高优先级优先，总数不超过 max_targets"""
    if priority not in GOLDEN_DOLPHIN_REWARD_ORDER:
        priority = "xp"
    search_order = (priority,) + tuple(
        category for category in GOLDEN_DOLPHIN_REWARD_ORDER if category != priority
    )
    
    collected = []
    for category in search_order:
        if len(collected) >= max_targets:
            break
            
        templates = reward_templates.get(category, ())
        if category == "xp":
            candidates = _find_golden_dolphin_xp(frame, templates)
        else:
            candidates = _find_golden_dolphin_template_targets(frame, templates)
            
        for x, y, score in candidates:
            if len(collected) >= max_targets:
                break
            collected.append((category, x, y, score))
            
    return collected


def _complete_golden_dolphin_round():
    """记录一局结算；前三局之间继续，第三局后完成。"""
    completed = int(golden_dolphin_state.get("completed_rounds", 0)) + 1
    max_rounds = int(golden_dolphin_state.get("max_rounds", 3))
    golden_dolphin_state["completed_rounds"] = completed
    status = "NEXT_ROUND" if completed < max_rounds else "DONE"
    golden_dolphin_state["status"] = status
    return status


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


def _match_golden_dolphin_template(frame, template):
    """返回模板最高分和中心点；只负责识别，不提供固定坐标兜底。"""
    if frame is None or template is None or template.size == 0:
        return 0.0, None
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    return float(score), (
        location[0] + template.shape[1] // 2,
        location[1] + template.shape[0] // 2,
    )


def _return_golden_dolphin_to_tank(ctrl, templates, timeout: float = 8.0):
    """从结算页或已确认的游乐园面板安全归位，并以主界面模板作为成功门禁。"""
    tpl_main = templates.get("main")
    tpl_cancel = templates.get("cancel")
    tpl_dolphin = templates.get("dolphin")
    if tpl_main is None or tpl_cancel is None or tpl_dolphin is None:
        print("[金海豚退出] ERROR: 缺少归位所需视觉模板，安全终止", flush=True)
        return False

    deadline = time.monotonic() + timeout
    last_action_at = 0.0
    last_scores = (0.0, 0.0, 0.0)
    while time.monotonic() < deadline:
        frame = _capture_720p(ctrl)
        if frame is None:
            time.sleep(0.2)
            continue

        main_score, _ = _match_golden_dolphin_template(frame, tpl_main)
        cancel_score, cancel_center = _match_golden_dolphin_template(frame, tpl_cancel)
        panel_score, _ = _match_golden_dolphin_template(frame, tpl_dolphin)
        last_scores = (main_score, cancel_score, panel_score)
        if main_score >= 0.70:
            print(f"[金海豚退出] 已确认返回主鱼缸 (score={main_score:.3f})", flush=True)
            return True

        now = time.monotonic()
        if now - last_action_at >= 0.8 and cancel_score >= 0.70 and cancel_center:
            print(
                f"[金海豚退出] 识别到结算取消按钮 (score={cancel_score:.3f})，"
                f"点击 {cancel_center}",
                flush=True,
            )
            ctrl.post_click(*cancel_center).wait()
            last_action_at = now
        elif now - last_action_at >= 0.8 and panel_score >= 0.70:
            print(
                f"[金海豚退出] 已确认仍在游乐园面板 (score={panel_score:.3f})，收起面板后验证鱼缸",
                flush=True,
            )
            ctrl.post_click(640, 150).wait()
            last_action_at = now
        time.sleep(0.35)

    main_score, cancel_score, panel_score = last_scores
    print(
        "[金海豚退出] ERROR: 归位超时，未确认主鱼缸，"
        f"main={main_score:.3f}, result={cancel_score:.3f}, panel={panel_score:.3f}",
        flush=True,
    )
    return False


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
            # 绿色区域只能辅助定位按钮，不能单独证明弹窗存在；结算页或奖励动画
            # 也可能出现绿色目标，曾因此把结算页误判成“次数耗尽”弹窗。
            already_in_popup = (vc_init >= 0.70)

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

            # 区分“机会已全部用完”与“您想玩这个小游戏吗”（保留 HSV 红色取消几何判定）
            has_red_cancel = False
            try:
                sc_720 = cv2.resize(screen_confirm, (1280, 720))
                red_patch = sc_720[430:490, 650:710]
                hsv_p = cv2.cvtColor(red_patch, cv2.COLOR_BGR2HSV)
                mask_r = ((hsv_p[:, :, 0] < 10) | (hsv_p[:, :, 0] > 170)) & (hsv_p[:, :, 1] > 90) & (hsv_p[:, :, 2] > 90)
                has_red_cancel = bool(np.sum(mask_r) > 400)
            except Exception:
                pass

            if has_red_cancel:
                # 普通“想玩”确认弹窗：完全跳过 RapidOCR，立即进入确认点击闭环
                print(
                    f"[金海豚导航] 普通“想玩”确认弹窗已确认，跳过文字 OCR，"
                    f"立即点击绿色对号 ({btn_cx},{btn_cy})。",
                    flush=True,
                )
                dialog_closed, btn_cx, btn_cy = _confirm_golden_dolphin_dialog_closed(
                    ctrl, tpl_confirm, screen_confirm, btn_cx, btn_cy
                )
                if not dialog_closed:
                    print(
                        "[金海豚导航] ERROR: 确认弹窗连续 3 次点击后仍未关闭，"
                        "安全停止，不进入采集循环。",
                        flush=True,
                    )
                    golden_dolphin_state["status"] = "FAILED"
                    return False
                print("[金海豚导航] 已验证确认弹窗关闭，小游戏进入流程成立。", flush=True)
                golden_dolphin_state["status"] = "READY_TO_PLAY"
                return True

            # 无红 X：疑似耗尽弹窗（几何证据），RapidOCR 仅作辅助确认（lazy singleton）
            is_exhausted = True
            try:
                ocr = _get_golden_dolphin_ocr()
                res_ocr, _ = ocr(screen_confirm)
                for _, txt, _ in (res_ocr or []):
                    if any(k in txt for k in ("用完", "明天再来", "全部用完", "明天")):
                        print("[金海豚导航] OCR 命中耗尽文案，确认机会耗尽判定。", flush=True)
                        break
                else:
                    print("[金海豚导航] OCR 未命中耗尽文案，维持几何判定（疑似耗尽）。", flush=True)
            except Exception as e:
                print(f"[金海豚导航] OCR 辅助确认异常，维持疑似耗尽判定: {e}", flush=True)

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

                if not _return_golden_dolphin_to_tank(ctrl, tpls):
                    golden_dolphin_state["status"] = "FAILED"
                    return False
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


@AgentServer.custom_action("GoldenDolphinInitAction")
class GoldenDolphinInitAction(CustomAction):
    """为本次任务重置三局连续执行状态。"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        params = parse_dict_param(getattr(argv, "custom_action_param", None))
        reward_priority = str(params.get("reward_priority", "xp")).strip().lower()
        if reward_priority not in GOLDEN_DOLPHIN_REWARD_ORDER:
            print(
                f"[金海豚] 未知奖励优先级 {reward_priority!r}，回退为经验星",
                flush=True,
            )
            reward_priority = "xp"
        golden_dolphin_state["status"] = "IDLE"
        golden_dolphin_state["completed_rounds"] = 0
        golden_dolphin_state["max_rounds"] = 3
        golden_dolphin_state["reward_priority"] = reward_priority
        print(
            f"[金海豚] 任务开始：计划连续执行 3 局；最高优先级={GOLDEN_DOLPHIN_REWARD_NAMES[reward_priority]}；"
            "中途无次数则正常结束",
            flush=True,
        )
        return True


@AgentServer.custom_action("GoldenDolphinPlayGameAction")
class GoldenDolphinPlayGameAction(CustomAction):
    """
    金海豚小游戏拾取动作 (职责 2):
    仅负责游戏画面内的微观交互:
    1. 全屏识别经验星、爱心、宝石、贝币
    2. 每帧优先点击用户选择的奖励，未命中时立即点击其余已识别奖励
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
            reward_templates = tpls.get("rewards", {})
            tpl_cancel = tpls.get("cancel")
            priority = str(golden_dolphin_state.get("reward_priority", "xp")).lower()
            if priority not in GOLDEN_DOLPHIN_REWARD_ORDER:
                priority = "xp"

            expected_template_counts = {"xp": 2, "heart": 1, "gem": 4, "coin": 3}
            missing_categories = [
                GOLDEN_DOLPHIN_REWARD_NAMES[category]
                for category, expected_count in expected_template_counts.items()
                if len(reward_templates.get(category, ())) < expected_count
            ]
            if missing_categories:
                print(
                    f"[金海豚游戏] ERROR: 奖励模板未完整加载：{', '.join(missing_categories)}，安全终止任务",
                    flush=True,
                )
                return False

            print(
                f"[金海豚游戏] 当前策略：全屏识别四类奖励；最高优先级="
                f"{GOLDEN_DOLPHIN_REWARD_NAMES[priority]}；未命中时同一帧立即处理其他奖励",
                flush=True,
            )
            t_game_start = time.monotonic()
            active_start = None
            t_first_startup_click = None
            game_done = False
            reward_clicks = {category: 0 for category in GOLDEN_DOLPHIN_REWARD_ORDER}
            loop_count = 0

            while time.monotonic() - t_game_start < 75.0:
                if _task_cancelled(context):
                    print("[金海豚游戏] 收到停止请求，立即停止奖励点击", flush=True)
                    return False
                elapsed = time.monotonic() - t_game_start
                img = _capture_720p(ctrl)
                if img is None:
                    time.sleep(0.02)
                    continue
                loop_count += 1

                # 结算模板只需降频轮询，避免它阻塞每一帧奖励检测。
                if elapsed > 20.0 and loop_count % 5 == 0 and tpl_cancel is not None:
                    res_cancel = cv2.matchTemplate(img, tpl_cancel, cv2.TM_CCOEFF_NORMED)
                    _, max_cancel, _, loc_cancel = cv2.minMaxLoc(res_cancel)
                    if max_cancel >= 0.70:
                        print(f"[金海豚游戏] 检测到游戏结束结算弹窗 (score={max_cancel:.3f})，跳出游戏循环", flush=True)
                        game_done = True
                        break

                if active_start is None:
                    # v0.5.1~v0.5.5 已实机验证的 XP-only 启动门禁：Heart/Gem 不参与
                    # "是否已激活"的判定（全部真实 fixture 中不存在"已激活但 XP 缺席"
                    # 的样本，且三类全屏 gate 引入 6.47x 帧龄延迟导致下落贝币点空；
                    # Heart 模板在结束页还存在假阳性）。它们仍是正式阶段的合法奖励。
                    xp_candidates = _find_golden_dolphin_xp(
                        img, reward_templates.get("xp", ())
                    )
                    if xp_candidates:
                        active_start = time.monotonic()
                        print(
                            "[金海豚游戏] 已识别到经验星，隐藏启动阶段完成；"
                            "切换为四类奖励连续点击模式",
                            flush=True,
                        )
                        print(
                            f"[金海豚游戏] 隐藏启动完成：activation coin clicks="
                            f"{reward_clicks['coin']}, startup duration="
                            f"{active_start - t_game_start:.2f}s",
                            flush=True,
                        )
                    else:
                        # 隐藏启动仅使用无编号 金海豚_贝币.png 的 ROI+最高分旧语义，
                        # 不走全屏多候选 detector（v0.5.6 起的 bottom-most 回归已取证）。
                        activation_templates = tpls.get("activation_coin", ())
                        activation_coin = _find_golden_dolphin_activation_coin(
                            img,
                            activation_templates[0] if activation_templates else None,
                        )

                targets = []
                is_startup_coin = False

                if active_start is not None:
                    targets = _collect_golden_dolphin_frame_targets(
                        img, reward_templates, priority, max_targets=4
                    )
                elif activation_coin is not None:
                    is_startup_coin = True
                    targets = [("coin", *activation_coin)]

                if targets:
                    for category, target_x, target_y, score in targets:
                        if _task_cancelled(context):
                            print("[金海豚游戏] 收到停止请求，立即停止奖励点击", flush=True)
                            return False
                        
                        job = ctrl.post_click(target_x, target_y)
                        if is_startup_coin:
                            if job:
                                job.wait()

                        reward_clicks[category] += 1

                        if is_startup_coin:
                            if t_first_startup_click is None:
                                t_first_startup_click = time.monotonic()
                                print(
                                    f"[金海豚游戏] 首次启动贝币点击延迟："
                                    f"{t_first_startup_click - t_game_start:.2f}s",
                                    flush=True,
                                )
                            n_clicks = reward_clicks[category]
                            if n_clicks <= 5 or n_clicks % 10 == 0:
                                print(
                                    f"[金海豚游戏] 隐藏启动：已同步点击贝币\n"
                                    f"(第 {n_clicks} 次, x={target_x}, y={target_y}, "
                                    f"score={score:.4f})",
                                    flush=True,
                                )

                    time.sleep(0.01)

                if active_start is not None and time.monotonic() - active_start >= 45.0:
                    print(
                        "[金海豚游戏] ERROR: 正式掉落阶段已超过 45 秒仍未识别到结算页，安全停止",
                        flush=True,
                    )
                    return False

            duration = time.monotonic() - t_game_start
            average_fps = loop_count / duration if duration > 0 else 0.0
            print(
                f"[金海豚游戏] 小游戏循环完成 (耗时 {duration:.1f}s, 检测 {loop_count} 帧/{average_fps:.1f} FPS, "
                f"点击经验星 {reward_clicks['xp']} 次, 点击爱心 {reward_clicks['heart']} 次, "
                f"点击宝石 {reward_clicks['gem']} 次, 点击贝币 {reward_clicks['coin']} 次, "
                f"最高优先级={GOLDEN_DOLPHIN_REWARD_NAMES[priority]}, 弹窗就绪={game_done})",
                flush=True,
            )
            if not game_done:
                print("[金海豚游戏] ERROR: 未确认结算页，拒绝进入退出动作", flush=True)
                return False
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[金海豚游戏] 运行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("GoldenDolphinExitAction")
class GoldenDolphinExitAction(CustomAction):
    """
    金海豚退出与归位动作 (职责 3):
    1. 只点击实际识别到的结算取消按钮
    2. 关闭潜在浮层，确认回到主鱼缸
    3. 记录已完成局数；未满 3 局设置 NEXT_ROUND，否则设置 DONE
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

            # 结算页可能比游戏循环结束稍晚出现。必须等到真实页面可识别并确认
            # 回到主鱼缸后才记为完成，禁止未命中模板时盲点并提前推进日常收尾。
            if tpl_cancel is None or not _return_golden_dolphin_to_tank(ctrl, tpls, timeout=15.0):
                golden_dolphin_state["status"] = "FAILED"
                return False

            status = _complete_golden_dolphin_round()
            completed = golden_dolphin_state["completed_rounds"]
            max_rounds = golden_dolphin_state["max_rounds"]
            if status == "NEXT_ROUND":
                print(
                    f"[金海豚退出] 第 {completed}/{max_rounds} 局结算退出完成，回到主鱼缸后继续下一局",
                    flush=True,
                )
            else:
                print(f"[金海豚退出] 第 {completed}/{max_rounds} 局结算退出完成，三局任务完成", flush=True)
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
    1. 重置并循环 GoldenDolphinNavigationAction，最多 3 局
    2. 每局状态为 READY_TO_PLAY:
       -> GoldenDolphinPlayGameAction
       -> GoldenDolphinExitAction
    3. 任意一局 NO_STAMINA 均正常停止；最后根据业务状态推进 DailyRoutine 队列
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            GoldenDolphinInitAction().run(context, argv)
            while golden_dolphin_state["completed_rounds"] < golden_dolphin_state["max_rounds"]:
                nav_ok = GoldenDolphinNavigationAction().run(context, argv)
                if not nav_ok:
                    if daily_routine_state.get("active"):
                        advance_daily_routine_step("GoldenDolphin", "FAILED")
                    return False

                st = golden_dolphin_state.get("status")
                if st == "NO_STAMINA":
                    if daily_routine_state.get("active"):
                        advance_daily_routine_step("GoldenDolphin", "NO_STAMINA")
                    return True
                if st != "READY_TO_PLAY":
                    break

                if not GoldenDolphinPlayGameAction().run(context, argv):
                    golden_dolphin_state["status"] = "FAILED"
                    if daily_routine_state.get("active"):
                        advance_daily_routine_step("GoldenDolphin", "FAILED")
                    return False
                if not GoldenDolphinExitAction().run(context, argv):
                    if daily_routine_state.get("active"):
                        advance_daily_routine_step("GoldenDolphin", "FAILED")
                    return False

            final_st = golden_dolphin_state.get("status", "DONE")
            if daily_routine_state.get("active"):
                advance_daily_routine_step("GoldenDolphin", final_st)
            return final_st != "FAILED"
        except Exception as e:
            traceback.print_exc()
            print(f"[金海豚总控] 运行异常: {e}", flush=True)
            golden_dolphin_state["status"] = "FAILED"
            if daily_routine_state.get("active"):
                advance_daily_routine_step("GoldenDolphin", "FAILED")
            return False


@AgentServer.custom_action("InitGreenWildDailyAction")
class InitGreenWildDailyAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            green_wild_daily_state["pending_buy_fish"] = True
            try:
                context.override_pipeline({
                    "OpenShellShouldContinue": {
                        "custom_recognition_param": {
                            "target_count": 1
                        }
                    }
                })
            except Exception:
                pass
            print("[绿野寻仙踪日常] 开始执行：先开贝壳 1 次，再去商店买鱼。", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[绿野寻仙踪日常] 初始化异常: {e}", flush=True)
            return False


@AgentServer.custom_action("GreenWildDailyDoneAction")
class GreenWildDailyDoneAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            green_wild_daily_state["pending_buy_fish"] = False
            print("[绿野寻仙踪日常] 已确认返回主鱼缸，任务完成", flush=True)
            if daily_routine_state.get("active"):
                current_step = daily_routine_state.get("step")
                task_status = daily_routine_state.get("tasks", {}).get("GreenWildDaily", {}).get("status")
                if current_step == "GREEN_WILD_DAILY" and task_status != "DONE":
                    advance_daily_routine_step("GreenWildDaily", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[绿野寻仙踪日常] 完成状态写入异常: {e}", flush=True)
            return False


HANGUP_DAILY_ALL = {"all_enabled": True}


@AgentServer.custom_action("InitHangupScheduledDailyAction")
class InitHangupScheduledDailyAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            resume_to = param.get("resume_to") or "collect_fish"
            stack = hangup_schedule_state.setdefault("resume_stack", [])
            stack.append(resume_to)
            hangup_schedule_state["noon_daily_last_date"] = datetime.now().date().isoformat()
            print(
                f"[挂机日程] 已到 12:00，开始执行日常收尾（默认全选），完成后返回 {resume_to}。",
                flush=True,
            )
            class _Arg:
                custom_action_param = json.dumps(HANGUP_DAILY_ALL)
            return InitDailyRoutineAction().run(context, _Arg())
        except Exception as e:
            traceback.print_exc()
            print(f"[挂机日程] 启动十二点日常异常: {e}", flush=True)
            return False


@AgentServer.custom_action("InitHangupFriendGemAction")
class InitHangupFriendGemAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            resume_to = param.get("resume_to") or "collect_fish"
            stack = hangup_schedule_state.setdefault("resume_stack", [])
            stack.append(resume_to)
            hour = datetime.now().hour
            today = datetime.now().date().isoformat()
            if hour >= 22:
                hangup_schedule_state["friend_gem_evening_date"] = today
                slot = "晚上十点"
            else:
                hangup_schedule_state["friend_gem_morning_date"] = today
                slot = "上午十点"
            print(f"[挂机日程] 已到{slot}，开始好友摸宝兜底，完成后返回 {resume_to}。", flush=True)
            return InitFriendGemStateAction().run(context, argv)
        except Exception as e:
            traceback.print_exc()
            print(f"[挂机日程] 启动好友摸宝异常: {e}", flush=True)
            return False


@AgentServer.custom_action("HangupPopResumeAction")
class HangupPopResumeAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            stack = hangup_schedule_state.setdefault("resume_stack", [])
            target = stack.pop() if stack else None
            print(f"[挂机日程] 子任务结束，返回挂机循环: {target}", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[挂机日程] 返回挂机异常: {e}", flush=True)
            return False


@AgentServer.custom_action("InitDailyRoutineAction")
class InitDailyRoutineAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            daily_routine_state["active"] = True
            daily_routine_state["tasks"] = {
                "FreeGift": {"status": "IDLE"},
                "ReindeerFish": {"status": "IDLE"},
                "GoldShellCoupon": {"status": "IDLE"},
                "GreenWildDaily": {"status": "IDLE"},
                "BandFish": {"status": "IDLE", "stage": "PASS1"},
                "GoldenDolphin": {"status": "IDLE"},
                "ShakeGame": {"status": "IDLE"},
                "Fishing": {"status": "IDLE"},
                "GemGiftBox": {"status": "IDLE"},
                "GemOrder": {"status": "IDLE"},
                "RomanticHouse": {"status": "IDLE"},
                "SecretRealmGate": {"status": "IDLE"},
                "PrincessTask": {"status": "IDLE"},
            }

            # 1. 优先从 custom_action_param 解析配置 (支持测试与外部传参)
            param = parse_dict_param(argv.custom_action_param)
            has_param = any(k in param for k in ("all_enabled", "free_gift", "reindeer_fish", "gold_shell_coupon", "green_wild_daily", "band_fish", "golden_dolphin", "shake_game", "fishing", "gem_gift_box", "gem_order", "romantic_house", "secret_realm_gate", "princess_task"))

            if param.get("all_enabled"):
                enable_fg = enable_rf = enable_gsc = enable_gwd = True
                enable_bf = enable_gd = enable_sg = enable_fi = True
                enable_ggb = enable_go = enable_rh = True
                enable_srg = enable_pt = True
            elif has_param:
                enable_fg = bool(param.get("free_gift", False))
                enable_rf = bool(param.get("reindeer_fish", False))
                enable_gsc = bool(param.get("gold_shell_coupon", False))
                enable_gwd = bool(param.get("green_wild_daily", False))
                enable_bf = bool(param.get("band_fish", False))
                enable_gd = bool(param.get("golden_dolphin", False))
                enable_sg = bool(param.get("shake_game", False))
                enable_fi = bool(param.get("fishing", False))
                enable_ggb = bool(param.get("gem_gift_box", False))
                enable_go = bool(param.get("gem_order", False))
                enable_rh = bool(param.get("romantic_house", False))
                enable_srg = bool(param.get("secret_realm_gate", False))
                enable_pt = bool(param.get("princess_task", False))
            else:
                # 2. 从 pipeline override 中的 Enable 节点读取配置
                def _is_node_enabled(node_name: str) -> bool:
                    try:
                        nd = context.get_node_data(node_name)
                        return bool(nd.get("enabled", False)) if nd else False
                    except Exception:
                        return False

                enable_fg = _is_node_enabled("DailyRoutineEnableFreeGift")
                enable_rf = _is_node_enabled("DailyRoutineEnableReindeerFish")
                enable_gsc = _is_node_enabled("DailyRoutineEnableGoldShellCoupon")
                enable_gwd = _is_node_enabled("DailyRoutineEnableGreenWildDaily")
                enable_bf = _is_node_enabled("DailyRoutineEnableBandFish")
                enable_gd = _is_node_enabled("DailyRoutineEnableGoldenDolphin")
                enable_sg = _is_node_enabled("DailyRoutineEnableShakeGame")
                enable_fi = _is_node_enabled("DailyRoutineEnableFishing")
                enable_ggb = _is_node_enabled("DailyRoutineEnableGemGiftBox")
                enable_go = _is_node_enabled("DailyRoutineEnableGemOrder")
                enable_rh = _is_node_enabled("DailyRoutineEnableRomanticHouse")
                enable_srg = _is_node_enabled("DailyRoutineEnableSecretRealmGate")
                enable_pt = _is_node_enabled("DailyRoutineEnablePrincessTask")

            # 3. 按固定安全顺序构建待执行队列。
            queue = []
            if enable_bf:
                _reset_band_fish_state()
                queue.append("BAND_FISH_PASS1")
            if enable_fg:
                queue.append("FREE_GIFT")
            if enable_rf:
                queue.append("REINDEER_FISH")
            if enable_gsc:
                queue.append("GOLD_SHELL_COUPON")
            if enable_gwd:
                queue.append("GREEN_WILD_DAILY")
            if enable_srg:
                queue.append("SECRET_REALM_GATE")
            if enable_pt:
                queue.append("PRINCESS_TASK")
            if enable_gd:
                queue.append("GOLDEN_DOLPHIN")
            if enable_sg:
                queue.append("SHAKE_GAME")
            if enable_fi:
                queue.append("FISHING")
            if enable_ggb:
                queue.append("GEM_GIFT_BOX")
            if enable_go:
                queue.append("GEM_ORDER")
            if enable_rh:
                queue.append("ROMANTIC_HOUSE")
            if enable_bf:
                queue.append("BAND_FISH_PASS2")

            print("=" * 60, flush=True)
            print("[日常收尾] DailyRoutineTask 初始化成功，勾选子任务配置:", flush=True)
            print(f"  - 每日免费礼包 : {'[ON]' if enable_fg else '[OFF]'}", flush=True)
            print(f"  - 驯鹿鱼送收礼 : {'[ON]' if enable_rf else '[OFF]'}", flush=True)
            print(f"  - 兑换金贝壳券 : {'[ON]' if enable_gsc else '[OFF]'}", flush=True)
            print(f"  - 绿野寻仙踪日常 : {'[ON]' if enable_gwd else '[OFF]'}", flush=True)
            print(f"  - 秘境之门     : {'[ON]' if enable_srg else '[OFF]'}", flush=True)
            print(f"  - 公主任务     : {'[ON]' if enable_pt else '[OFF]'}", flush=True)
            print(f"  - 乐队鱼演出   : {'[ON]' if enable_bf else '[OFF]'}", flush=True)
            print(f"  - 金海豚小游戏 : {'[ON]' if enable_gd else '[OFF]'}", flush=True)
            print(f"  - 摇一摇小游戏 : {'[ON]' if enable_sg else '[OFF]'}", flush=True)
            print(f"  - 钓鱼达人     : {'[ON]' if enable_fi else '[OFF]'}", flush=True)
            print(f"  - 宝石礼盒兑换 : {'[ON]' if enable_ggb else '[OFF]'}", flush=True)
            print(f"  - 宝石订单     : {'[ON]' if enable_go else '[OFF]'}", flush=True)
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

            task_labels = (
                ("每日免费礼包", enable_fg), ("驯鹿鱼送收礼物", enable_rf),
                ("兑换金贝壳券", enable_gsc), ("绿野寻仙踪日常", enable_gwd), ("秘境之门", enable_srg), ("公主任务", enable_pt), ("乐队鱼", enable_bf),
                ("金海豚", enable_gd), ("摇一摇", enable_sg),
                ("钓鱼达人", enable_fi), ("宝石礼盒兑换", enable_ggb),
                ("宝石订单", enable_go), ("浪漫满屋", enable_rh),
            )
            selected = "、".join(label for label, enabled in task_labels if enabled) or "无"
            skipped = "、".join(label for label, enabled in task_labels if not enabled) or "无"
            ui_message = (
                f"[日常收尾] 已选择：{selected}；因未勾选跳过：{skipped}。"
            )
            try:
                context.override_pipeline({
                    "DailyRoutineInitLog": {
                        "focus": {"Node.Action.Succeeded": ui_message}
                    }
                })
            except Exception:
                pass

            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[日常收尾] 初始化异常: {e}", flush=True)
            return False


@AgentServer.custom_action("DailyFreeGiftDoneAction")
class DailyFreeGiftDoneAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[每日免费礼包] 已确认返回鱼缸，继续日常收尾", flush=True)
            advance_daily_routine_step("FreeGift", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[每日免费礼包] 完成状态写入异常: {e}", flush=True)
            return False


@AgentServer.custom_action("ReindeerFishDoneAction")
class ReindeerFishDoneAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[驯鹿鱼送收礼] 已确认返回鱼缸，继续日常收尾", flush=True)
            advance_daily_routine_step("ReindeerFish", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[驯鹿鱼送收礼] 完成状态写入异常: {e}", flush=True)
            return False


@AgentServer.custom_action("GemGiftBoxDoneAction")
class GemGiftBoxDoneAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[宝石礼盒] 已确认返回鱼缸，继续日常收尾", flush=True)
            advance_daily_routine_step("GemGiftBox", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[宝石礼盒] 完成状态写入异常: {e}", flush=True)
            return False


@AgentServer.custom_action("GemOrderDoneAction")
class GemOrderDoneAction(CustomAction):
    """宝石订单确认回到主鱼缸后，按独立/日常模式完成或推进队列。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[宝石订单] 已确认返回鱼缸，任务完成", flush=True)
            if daily_routine_state.get("active"):
                advance_daily_routine_step("GemOrder", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[宝石订单] 完成状态写入异常: {e}", flush=True)
            return False


@AgentServer.custom_action("GoldShellCouponDoneAction")
class GoldShellCouponDoneAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            print("[兑换金贝壳券] 已确认返回鱼缸，继续日常收尾", flush=True)
            if daily_routine_state.get("active"):
                # 幂等保护：仅当当前 step 确为 GOLD_SHELL_COUPON 且状态未为 DONE 时推进
                current_step = daily_routine_state.get("step")
                task_status = daily_routine_state.get("tasks", {}).get("GoldShellCoupon", {}).get("status")
                if current_step == "GOLD_SHELL_COUPON" and task_status != "DONE":
                    advance_daily_routine_step("GoldShellCoupon", "DONE")
                else:
                    print(f"[兑换金贝壳券] 幂等守卫生效：忽略重复或非本阶段推进请求 (step={current_step}, status={task_status})", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[兑换金贝壳券] 完成状态写入异常: {e}", flush=True)
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
            print("[浪漫满屋退出] 已确认返回主鱼缸", flush=True)
            romantic_house_state["status"] = "DONE"
            if daily_routine_state.get("active"):
                advance_daily_routine_step("RomanticHouse", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[浪漫满屋退出] 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SecretRealmGateClickSendAction")
class SecretRealmGateClickSendAction(CustomAction):
    """点击任务列表中的"送出"按钮，并记录其 OCR 命中框供分支二相对定位。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[秘境之门] 错误: 未获取到 Controller", flush=True)
                return False
            box = getattr(argv, "box", None)
            if not box or len(box) != 4:
                print("[秘境之门] 错误: 送出按钮识别框缺失", flush=True)
                return False
            box = [int(v) for v in box]
            cx = box[0] + box[2] // 2
            cy = box[1] + box[3] // 2
            ctrl.post_click(cx, cy).wait()
            secret_realm_gate_state["last_send_box"] = box
            secret_realm_gate_state["send_wait_started"] = None
            print(f"[秘境之门] 已点击送出按钮 {box}（中心 {cx},{cy}），已记录位置", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[秘境之门] 点击送出异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SecretRealmGateClickDeleteAction")
class SecretRealmGateClickDeleteAction(CustomAction):
    """分支二："您没有这种鱼"时删除对应卡片垃圾桶。

    相对位置（用户提供实测值）：送出按钮 [980,441,51,29] 时垃圾桶在 [1239,330,15,17]，
    即垃圾桶中心相对送出按钮中心偏移 (+241, -117)。先按偏移推算期望位置，
    再在小容差窗口内用 秘境之门_删除.png 模板确认后才点击，绝不盲点。
    """

    SEND_TO_DELETE_OFFSET = (241, -117)
    TOLERANCE = 40

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[秘境之门] 错误: 未获取到 Controller", flush=True)
                return False
            send_box = secret_realm_gate_state.get("last_send_box")
            if not send_box or len(send_box) != 4:
                print("[秘境之门] 错误: 缺少送出按钮位置记录，无法定位对应垃圾桶", flush=True)
                return False

            send_cx = send_box[0] + send_box[2] // 2
            send_cy = send_box[1] + send_box[3] // 2
            exp_cx = send_cx + self.SEND_TO_DELETE_OFFSET[0]
            exp_cy = send_cy + self.SEND_TO_DELETE_OFFSET[1]
            roi = [
                max(0, exp_cx - self.TOLERANCE),
                max(0, exp_cy - self.TOLERANCE),
                self.TOLERANCE * 2,
                self.TOLERANCE * 2,
            ]
            result = context.run_recognition(
                "SecretRealmGateDeleteIcon",
                pipeline_override={
                    "recognition": "TemplateMatch",
                    "template": "秘境之门_删除.png",
                    "threshold": 0.7,
                    "roi": roi,
                    "order_by": "Distance",
                },
            )
            if not result or not result.hit:
                print(
                    f"[秘境之门] 错误: 送出按钮 {send_box} 对应垃圾桶期望位置 ({exp_cx},{exp_cy}) "
                    "未命中删除图标模板，拒绝盲点",
                    flush=True,
                )
                return False
            del_box = [int(v) for v in result.box]
            dx = del_box[0] + del_box[2] // 2
            dy = del_box[1] + del_box[3] // 2
            ctrl.post_click(dx, dy).wait()
            secret_realm_gate_state["last_send_box"] = None
            print(
                f"[秘境之门] 已按相对偏移点击对应垃圾桶 {del_box}（中心 {dx},{dy}），"
                f"期望位置 ({exp_cx},{exp_cy})",
                flush=True,
            )
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[秘境之门] 点击删除异常: {e}", flush=True)
            return False


@AgentServer.custom_recognition("SecretRealmGateFindSendCardReco")
class SecretRealmGateFindSendCardReco(CustomRecognition):
    """显式逐卡选择：OCR 任务列表全部“送出”，按 center_y 从上往下，
    跳过当前布局内已验证无响应的行，返回第一张可处理卡的 OCR 命中框。
    纯读取：只读 runtime_state，不修改任何状态（skip 清空由 Action 负责）。
    """

    ROW_TOLERANCE = 40

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        frame = argv.image
        if frame is None:
            return None
        result = context.run_recognition(
            "SecretRealmGateSendOcrAll",
            frame,
            pipeline_override={"SecretRealmGateSendOcrAll": {
                "recognition": "OCR",
                "expected": ".*送\\s*出.*",
                "roi": [930, 149, 149, 522],
            }},
        )
        rows = []
        for item in getattr(result, "all_results", None) or []:
            box = getattr(item, "box", None)
            text = str(getattr(item, "text", ""))
            if not box or len(box) != 4:
                continue
            if not re.search(".*送\\s*出.*", text):
                continue
            center_y = int(box[1]) + int(box[3]) // 2
            rows.append((center_y, [int(v) for v in box]))
        if not rows:
            return None
        rows.sort(key=lambda r: r[0])

        # 列表布局签名：行集合变化 = 列表发生业务变化（完成/删除）→ skip 失效
        signature = tuple(r[0] for r in rows)
        if secret_realm_gate_state.get("last_row_signature") != signature:
            secret_realm_gate_state["no_response_rows"] = []
            secret_realm_gate_state["last_row_signature"] = signature

        skipped = secret_realm_gate_state.get("no_response_rows", [])
        for center_y, box in rows:
            if any(abs(center_y - sy) <= self.ROW_TOLERANCE for sy in skipped):
                continue
            return box
        return None


@AgentServer.custom_recognition("CheckSecretRealmGateSendWaitReco")
class CheckSecretRealmGateSendWaitReco(CustomRecognition):
    """"无送出"稳定观察窗口：单帧 OCR miss 不等于列表为空。

    首次评估记录观察起点，2.5 秒内命中（继续等待重试）；超时返回 None，
    由 WaitSendRetry 自身 on_error 流向 NoMoreSend → 退出链。
    点击送出成功后窗口重置（分支处理完回来重新计时）。
    """
    WAIT_WINDOW_SECONDS = 2.5

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        task_id = argv.task_detail.task_id
        now = time.monotonic()

        if secret_realm_gate_state.get("wait_task_id") != task_id:
            secret_realm_gate_state["wait_task_id"] = task_id
            secret_realm_gate_state["send_wait_started"] = None

        started = secret_realm_gate_state.get("send_wait_started")
        if started is None:
            secret_realm_gate_state["send_wait_started"] = now
            print("[秘境之门] 暂未识别到送出，进入稳定观察窗口", flush=True)
            return (0, 0, 10, 10)

        if now - started < self.WAIT_WINDOW_SECONDS:
            return (0, 0, 10, 10)

        print("[秘境之门] 观察窗口内稳定无送出，判定任务列表为空", flush=True)
        return None


@AgentServer.custom_action("SecretRealmGateMarkNoResponseAction")
class SecretRealmGateMarkNoResponseAction(CustomAction):
    """无响应确认：主页仍在 + 刚点击行的“送出”仍在 → 该行标记 no-response。

    主页 miss = 未知页面（弹窗盖住/未知状态）→ return False → 节点失败 →
    on_error 列表交给 SendPopup/NoFishCheck/Abort 处理（不吞未知页）。
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            frame = _capture_720p(context.tasker.controller)
            if frame is None:
                print("[秘境之门] ERROR: 标记无响应时截图失败", flush=True)
                return False
            main_box = _recognition_box(context, "SecretRealmGateMainPage", frame)
            if main_box is None:
                print("[秘境之门] 主页门禁未命中，无法确认无响应状态", flush=True)
                return False

            last_box = secret_realm_gate_state.get("last_send_box")
            if not last_box or len(last_box) != 4:
                print("[秘境之门] ERROR: 缺少送出按钮位置记录", flush=True)
                return False
            row_y = last_box[1] + last_box[3] // 2

            result = context.run_recognition(
                "SecretRealmGateSendOcrAll",
                frame,
                pipeline_override={"SecretRealmGateSendOcrAll": {
                    "recognition": "OCR",
                    "expected": ".*送\\s*出.*",
                    "roi": [930, 149, 149, 522],
                }},
            )
            same_row_found = False
            for item in getattr(result, "all_results", None) or []:
                b = getattr(item, "box", None)
                if not b or len(b) != 4:
                    continue
                cy = int(b[1]) + int(b[3]) // 2
                if abs(cy - row_y) <= 40:
                    same_row_found = True
                    break

            if same_row_found:
                rows = secret_realm_gate_state.setdefault("no_response_rows", [])
                if not any(abs(r - row_y) <= 40 for r in rows):
                    rows.append(row_y)
                print(
                    f"[秘境之门] 第 {row_y} 行送出确认无响应，已标记跳过"
                    f"（当前跳过行: {sorted(secret_realm_gate_state['no_response_rows'])}）",
                    flush=True,
                )
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[秘境之门] 标记无响应异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SecretRealmGateListChangedAction")
class SecretRealmGateListChangedAction(CustomAction):
    """列表业务变化（分支一完成 / 分支二删除）→ 清空 no-response 跳过行，
    使逐卡扫描从顶部重新开始（卡片位置固定的前提是列表布局已变化）。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            if secret_realm_gate_state.get("no_response_rows"):
                print("[秘境之门] 列表已发生业务变化，清空无响应跳过行记录", flush=True)
            secret_realm_gate_state["no_response_rows"] = []
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[秘境之门] 清空跳过行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("SecretRealmGateDoneAction")
class SecretRealmGateDoneAction(CustomAction):
    """秘境之门结算：确认回到主鱼缸后标记完成；日常收尾中则推进队列。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            if daily_routine_state.get("active"):
                advance_daily_routine_step("SecretRealmGate", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[秘境之门] 结算异常: {e}", flush=True)
            return False


@AgentServer.custom_action("PrincessTaskDoneAction")
class PrincessTaskDoneAction(CustomAction):
    """公主任务结算：确认回到主鱼缸后标记完成；日常收尾中则推进队列。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            if daily_routine_state.get("active"):
                advance_daily_routine_step("PrincessTask", "DONE")
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[公主任务] 结算异常: {e}", flush=True)
            return False


@AgentServer.custom_action("EmulatorAdClosePageAction")
class EmulatorAdClosePageAction(CustomAction):
    """模拟器看广告：关闭当前层广告/落地页，并对同一关闭链做连续层数保护。"""

    MAX_CONSECUTIVE_CLOSES = 4

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[模拟器看广告] 错误: 未获取到 Controller", flush=True)
                return False
            raw_box = getattr(argv, "box", None)
            if raw_box is None:
                print("[模拟器看广告] 错误: 关闭按钮识别框缺失", flush=True)
                return False
            try:
                box = [int(v) for v in raw_box]
            except (TypeError, ValueError):
                print("[模拟器看广告] 错误: 关闭按钮识别框格式无效", flush=True)
                return False
            if len(box) != 4:
                print("[模拟器看广告] 错误: 关闭按钮识别框缺失", flush=True)
                return False
            cx = box[0] + box[2] // 2
            cy = box[1] + box[3] // 2
            ctrl.post_click(cx, cy).wait()

            count = int(mobile_ad_state.get("consecutive_close_count", 0)) + 1
            mobile_ad_state["consecutive_close_count"] = count
            print(
                f"[模拟器看广告] 已关闭第 {count} 层广告/落地页页面 (x={cx}, y={cy})",
                flush=True,
            )
            if count > self.MAX_CONSECUTIVE_CLOSES:
                print(
                    "[模拟器看广告] ERROR: 连续关闭多层广告页面达到安全上限，"
                    "仍未回到已知状态，停止避免重复点击同一 X。",
                    flush=True,
                )
                return False
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[模拟器看广告] 关闭落地页异常: {e}", flush=True)
            return False


@AgentServer.custom_action("EmulatorAdCloseRewardAction")
class EmulatorAdCloseRewardAction(CustomAction):
    """模拟器看广告：以领奖弹窗绿色对号为门禁，点击同弹窗左侧红叉退出。"""

    RED_CLOSE_OFFSET_X = -102

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[模拟器看广告] 错误: 未获取到 Controller", flush=True)
                return False
            raw_box = getattr(argv, "box", None)
            if raw_box is None:
                print("[模拟器看广告] 错误: 领奖弹窗对号识别框缺失", flush=True)
                return False
            try:
                box = [int(v) for v in raw_box]
            except (TypeError, ValueError):
                print("[模拟器看广告] 错误: 领奖弹窗对号识别框格式无效", flush=True)
                return False
            if len(box) != 4:
                print("[模拟器看广告] 错误: 领奖弹窗对号识别框缺失", flush=True)
                return False
            cx = box[0] + box[2] // 2 + self.RED_CLOSE_OFFSET_X
            cy = box[1] + box[3] // 2
            if cx < 0 or cy < 0:
                print("[模拟器看广告] 错误: 领奖弹窗红叉坐标越界", flush=True)
                return False
            ctrl.post_click(cx, cy).wait()
            print(
                f"[模拟器看广告] 已点击领奖弹窗红叉 (x={cx}, y={cy})",
                flush=True,
            )
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[模拟器看广告] 关闭领奖弹窗异常: {e}", flush=True)
            return False


@AgentServer.custom_action("DailyRoutineFinishAction")
class DailyRoutineFinishAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            tasks = daily_routine_state.get("tasks", {})
            fg_st = tasks.get("FreeGift", {}).get("status", "SKIPPED")
            rf_st = tasks.get("ReindeerFish", {}).get("status", "SKIPPED")
            gsc_st = tasks.get("GoldShellCoupon", {}).get("status", "SKIPPED")
            bf_st = tasks.get("BandFish", {}).get("status", "SKIPPED")
            gd_st = tasks.get("GoldenDolphin", {}).get("status", "SKIPPED")
            sg_st = tasks.get("ShakeGame", {}).get("status", "SKIPPED")
            fi_st = tasks.get("Fishing", {}).get("status", "SKIPPED")
            ggb_st = tasks.get("GemGiftBox", {}).get("status", "SKIPPED")
            go_st = tasks.get("GemOrder", {}).get("status", "SKIPPED")
            rh_st = tasks.get("RomanticHouse", {}).get("status", "SKIPPED")
            srg_st = tasks.get("SecretRealmGate", {}).get("status", "SKIPPED")
            pt_st = tasks.get("PrincessTask", {}).get("status", "SKIPPED")

            print("=" * 60, flush=True)
            print("  【日常收尾 DailyRoutineTask】全部勾选子任务执行完毕！", flush=True)
            print(f"  - 每日免费礼包 (FreeGift)     : {fg_st}", flush=True)
            print(f"  - 驯鹿鱼送收礼 (ReindeerFish) : {rf_st}", flush=True)
            print(f"  - 兑换金贝壳券 (GoldShellCoupon) : {gsc_st}", flush=True)
            gwd_st = tasks.get("GreenWildDaily", {}).get("status", "SKIPPED")
            print(f"  - 绿野寻仙踪日常 (GreenWildDaily) : {gwd_st}", flush=True)
            print(f"  - 乐队鱼演出 (BandFish)       : {bf_st}", flush=True)
            print(f"  - 金海豚小游戏 (GoldenDolphin) : {gd_st}", flush=True)
            print(f"  - 摇一摇小游戏 (ShakeGame)     : {sg_st}", flush=True)
            print(f"  - 钓鱼达人 (Fishing)          : {fi_st}", flush=True)
            print(f"  - 宝石礼盒兑换 (GemGiftBox)   : {ggb_st}", flush=True)
            print(f"  - 宝石订单 (GemOrder)         : {go_st}", flush=True)
            print(f"  - 浪漫满屋 (RomanticHouse)    : {rh_st}", flush=True)
            print(f"  - 秘境之门 (SecretRealmGate)  : {srg_st}", flush=True)
            print(f"  - 公主任务 (PrincessTask)     : {pt_st}", flush=True)
            print("=" * 60, flush=True)

            daily_routine_state["active"] = False
            daily_routine_state["step"] = "ALL_DONE"
            daily_routine_state["queue"] = []
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[日常收尾] 结束汇总异常: {e}", flush=True)
            return False


# ==========================================
# 摇一摇小游戏 (ShakeGame) 核心控制参数与动作
# ==========================================
SHAKE_GAME_INTERVAL_SECONDS = 0.8
SHAKE_GAME_MAX_DURATION_SECONDS = 40.0
SHAKE_GAME_MAX_CONSECUTIVE_FAILURES = 3


def _get_mumu_manager_and_vm(ctrl) -> Tuple[Optional[Path], Optional[int]]:
    """
    从 Controller 上下文动态解析 MuMuManager.exe 路径与 VM 实例号。
    严格安全规则：
    1. 从 ctrl.info 读取真实配置；
    2. mumu_path / adb_path 推导的 MuMuManager.exe 必须真实存在于文件系统中；
    3. VM index 必须由 Controller 明确提供 (extras.mumu.index)；
    4. 若 VM index 缺失或为 None，严格返回 (None, None)，绝不猜测或默认 vm_index = 0！
    """
    try:
        raw_info = getattr(ctrl, "info", None)
        if raw_info is None:
            return None, None
        info = json.loads(raw_info) if isinstance(raw_info, str) else raw_info
        if not isinstance(info, dict):
            return None, None

        cfg = info.get("config", {})
        mumu_cfg = cfg.get("extras", {}).get("mumu", {})
        mumu_path = mumu_cfg.get("path")
        vm_index = mumu_cfg.get("index")

        # 严格门禁：VM index 必须明确取得，禁止盲目默认
        if vm_index is None:
            return None, None

        # 1. 尝试从 extras.mumu.path 定位
        candidate = None
        if mumu_path:
            candidate = Path(mumu_path) / "nx_main" / "MuMuManager.exe"

        # 2. 若 extras 未配置路径，尝试从 adb_path 所在目录推导
        if not candidate or not candidate.exists():
            adb_path = info.get("adb_path")
            if adb_path:
                candidate = Path(adb_path).parent / "MuMuManager.exe"

        if not candidate or not candidate.exists():
            return None, None

        return candidate, int(vm_index)
    except Exception:
        return None, None


def _run_mumu_shake(manager_path: Path, vm_index: int, timeout: float = 2.0) -> bool:
    """
    通过 MuMuManager 执行一次 shake 命令。
    必须同时满足:
    1. subprocess returncode == 0
    2. stdout 为合法 JSON
    3. JSON 中 errcode == 0
    """
    cmd = [
        str(manager_path),
        "control",
        "-v",
        str(vm_index),
        "tool",
        "func",
        "-n",
        "shake",
    ]
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            print(f"[摇一摇] 警告: MuMuManager 进程退出码非零 ({proc.returncode}): {proc.stderr.strip()}", flush=True)
            return False

        stdout_text = proc.stdout.strip()
        if not stdout_text:
            print("[摇一摇] 警告: MuMuManager stdout 为空", flush=True)
            return False

        data = json.loads(stdout_text)
        if not isinstance(data, dict):
            print(f"[摇一摇] 警告: MuMuManager 返回非字典数据: {stdout_text}", flush=True)
            return False

        errcode = data.get("errcode")
        if errcode != 0:
            errmsg = data.get("errmsg", "")
            print(f"[摇一摇] 警告: MuMuManager 报告错误 (errcode={errcode}, errmsg={errmsg})", flush=True)
            return False

        return True
    except subprocess.TimeoutExpired:
        print(f"[摇一摇] 警告: MuMuManager 调用超时 ({timeout}s)", flush=True)
        return False
    except json.JSONDecodeError as e:
        print(f"[摇一摇] 警告: MuMuManager 返回非有效 JSON: {proc.stdout.strip()} ({e})", flush=True)
        return False
    except Exception as e:
        print(f"[摇一摇] 警告: 调用 MuMuManager 异常: {e}", flush=True)
        return False


def _get_shake_game_templates():
    """解析并加载摇一摇小游戏所需的关键视觉模板"""
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
        "entrance": _load_tpl("游乐园入口.png"),
        "shake_entrance": _load_tpl("摇一摇_入口.png"),
        "confirm": _load_tpl("金海豚_确定按钮.png"),
        "cancel": _load_tpl("金海豚_结束取消.png"),
    }


def _complete_shake_game_round():
    """记录一局结算；前三局之间继续，第三局后完成。"""
    completed = int(shake_game_state.get("completed_rounds", 0)) + 1
    max_rounds = int(shake_game_state.get("max_rounds", 3))
    shake_game_state["completed_rounds"] = completed
    status = "NEXT_ROUND" if completed < max_rounds else "DONE"
    shake_game_state["status"] = status
    return status


@AgentServer.custom_action("ShakeGameInitAction")
class ShakeGameInitAction(CustomAction):
    """重置摇一摇状态 (支持最多 3 局)"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        shake_game_state["status"] = "IDLE"
        shake_game_state["completed_rounds"] = 0
        shake_game_state["max_rounds"] = 3
        print("[摇一摇] 任务启动，重置状态为 IDLE (0/3局)", flush=True)
        return True


@AgentServer.custom_action("ShakeGameNavigationAction")
class ShakeGameNavigationAction(CustomAction):
    """
    摇一摇导航与进入动作:
    1. Deepest-First 状态判定 (确认/耗尽弹窗 -> 游乐园面板 -> 主鱼缸场景)
    2. 打开游乐园并识别点击 摇一摇_入口.png
    3. 弹窗裁决 (「机会已用完」vs「正常想玩」)
       - 耗尽: 点击对号关闭弹窗，设置 status=NO_STAMINA，返回 True (流向 Done 正常结束)
       - 正常: 点击对号进入游戏，设置 status=READY_TO_PLAY，返回 True
       - 失败: 设置 status=FAILED，返回 False
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[摇一摇导航] 错误: 未获取到 Controller", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            tpls = _get_shake_game_templates()
            tpl_ent = tpls.get("entrance")
            tpl_shake = tpls.get("shake_entrance")
            tpl_confirm = tpls.get("confirm")

            if tpl_ent is None or tpl_shake is None or tpl_confirm is None:
                print("[摇一摇导航] ERROR: 缺少关键视觉模板，安全终止任务！", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            print("[摇一摇导航] 启动导航流程，检测当前页面状态...", flush=True)
            screen = _capture_720p(ctrl)
            if screen is None:
                print("[摇一摇导航] ERROR: 无法获取截屏，安全终止任务", flush=True)
                shake_game_state["status"] = "FAILED"
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
                print("[摇一摇导航] 状态判定：当前已处于提示/确认弹窗界面", flush=True)
                screen_confirm = screen
                has_confirm = True
                if gc_init:
                    btn_cx, btn_cy = gc_init
                elif res_c_init is not None:
                    loc_c = cv2.minMaxLoc(res_c_init)[3]
                    btn_cx = loc_c[0] + tpl_confirm.shape[1] // 2
                    btn_cy = loc_c[1] + tpl_confirm.shape[0] // 2
            else:
                # 状态判定 1: 检查是否已经处于游乐园面板内
                res_s = cv2.matchTemplate(screen, tpl_shake, cv2.TM_CCOEFF_NORMED)
                _, max_vs, _, loc_s = cv2.minMaxLoc(res_s)
                in_amusement_panel = (max_vs >= 0.65)

                if in_amusement_panel:
                    print(f"[摇一摇导航] 状态判定：当前已处于游乐园面板内 (摇一摇入口 match={max_vs:.3f})", flush=True)
                else:
                    # 状态判定 2: 主鱼缸场景，检测游乐园入口
                    print("[摇一摇导航] 状态判定：当前未在游乐园面板，检测主鱼缸游乐园入口...", flush=True)
                    res_e = cv2.matchTemplate(screen, tpl_ent, cv2.TM_CCOEFF_NORMED)
                    _, max_ve, _, loc_e = cv2.minMaxLoc(res_e)
                    if max_ve < 0.70:
                        print(f"[摇一摇导航] ERROR: 未识别到游乐园入口 (score={max_ve:.3f} < 0.70)，安全终止！", flush=True)
                        shake_game_state["status"] = "FAILED"
                        return False

                    ent_cx = loc_e[0] + tpl_ent.shape[1] // 2
                    ent_cy = loc_e[1] + tpl_ent.shape[0] // 2
                    print(f"[摇一摇导航] 识别到游乐园入口 (score={max_ve:.3f})，点击 ({ent_cx}, {ent_cy}) 打开游乐园...", flush=True)
                    ctrl.post_click(ent_cx, ent_cy).wait()

                    # 等待游乐园面板展开
                    in_amusement_panel = False
                    for wait_idx in range(3):
                        time.sleep(1.2 if wait_idx == 0 else 0.8)
                        screen = _capture_720p(ctrl)
                        if screen is None:
                            continue
                        res_s = cv2.matchTemplate(screen, tpl_shake, cv2.TM_CCOEFF_NORMED)
                        _, max_vs, _, loc_s = cv2.minMaxLoc(res_s)
                        if max_vs >= 0.65:
                            in_amusement_panel = True
                            break

                    if not in_amusement_panel:
                        print(f"[摇一摇导航] ERROR: 打开游乐园后未检测到摇一摇图标 (max_score={max_vs:.3f} < 0.65)，安全收起浮层！", flush=True)
                        ctrl.post_click(640, 150).wait()
                        time.sleep(1.0)
                        shake_game_state["status"] = "FAILED"
                        return False

                # 2. 点击摇一摇入口图标
                sx = loc_s[0] + tpl_shake.shape[1] // 2
                sy = loc_s[1] + tpl_shake.shape[0] // 2
                print(f"[摇一摇导航] 点击摇一摇入口图标 (score={max_vs:.3f}) at ({sx}, {sy})...", flush=True)
                ctrl.post_click(sx, sy).wait()
                time.sleep(1.5)

                # 3. 轮询确认弹窗
                for wait_c in range(4):
                    screen_confirm = _capture_720p(ctrl)
                    if screen_confirm is not None:
                        gc = _find_green_check(screen_confirm)
                        res_c = cv2.matchTemplate(screen_confirm, tpl_confirm, cv2.TM_CCOEFF_NORMED) if tpl_confirm is not None else None
                        max_vc = cv2.minMaxLoc(res_c)[1] if res_c is not None else 0
                        if gc is not None:
                            has_confirm = True
                            btn_cx, btn_cy = gc
                            print(f"[摇一摇导航] 准确定位到确认对号按钮 (HSV检测) at ({btn_cx}, {btn_cy})", flush=True)
                            break
                        elif max_vc >= 0.70:
                            has_confirm = True
                            loc_c = cv2.minMaxLoc(res_c)[3]
                            btn_cx = loc_c[0] + tpl_confirm.shape[1] // 2
                            btn_cy = loc_c[1] + tpl_confirm.shape[0] // 2
                            print(f"[摇一摇导航] 匹配到确认对号按钮 (模板 score={max_vc:.3f}) at ({btn_cx}, {btn_cy})", flush=True)
                            break
                    time.sleep(0.6)

            if not has_confirm or screen_confirm is None:
                print("[摇一摇导航] 未检测到确认对号按钮，安全收起面板退出", flush=True)
                shake_game_state["status"] = "NO_STAMINA"
                ctrl.post_click(640, 150).wait()
                time.sleep(1.0)
                return True

            # 区分“今天的机会已全部用完”与“您想玩这个小游戏吗”
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
                print(f"[摇一摇导航] 检测到提示「今天的机会已全部用完」，点击绿色对号按钮 ({btn_cx}, {btn_cy}) 关闭并验证...", flush=True)
                for click_retry in range(3):
                    ctrl.post_click(btn_cx, btn_cy).wait()
                    time.sleep(1.2)
                    sc_after = _capture_720p(ctrl)
                    if sc_after is not None:
                        res_check = cv2.matchTemplate(sc_after, tpl_confirm, cv2.TM_CCOEFF_NORMED) if tpl_confirm is not None else None
                        max_vc_after = cv2.minMaxLoc(res_check)[1] if res_check is not None else 0
                        gc_after = _find_green_check(sc_after)
                        if max_vc_after < 0.65 and gc_after is None:
                            print("[摇一摇导航] 验证通过：机会耗尽提示弹窗已成功关闭！", flush=True)
                            break
                        if gc_after:
                            btn_cx, btn_cy = gc_after

                shake_game_state["status"] = "NO_STAMINA"
                return True

            # 点击绿色确认按钮进入小游戏
            print(f"[摇一摇导航] 点击确认按钮 ({btn_cx}, {btn_cy}) 进入小游戏...", flush=True)
            ctrl.post_click(btn_cx, btn_cy).wait()
            time.sleep(2.0)
            shake_game_state["status"] = "READY_TO_PLAY"
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[摇一摇导航] 运行异常: {e}", flush=True)
            shake_game_state["status"] = "FAILED"
            return False


@AgentServer.custom_action("ShakeGamePlayAction")
class ShakeGamePlayAction(CustomAction):
    """
    摇一摇小游戏核心执行动作 (单局):
    1. 解析 MuMuManager 路径与 VM index (缺失时安全终止，禁止盲目默认)
    2. 以安全节奏循环调用 shake 命令，并周期截屏检查结算弹窗
    3. 成功条件: 检测到结算弹窗 -> SETTLEMENT, return True
    4. 失败条件: 超时未检出结算 / 连续3次RPC失败 / 任务取消 -> FAILED, return False
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[摇一摇] 错误: 未获取到 Controller", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            manager_path, vm_index = _get_mumu_manager_and_vm(ctrl)
            if not manager_path or not manager_path.exists():
                print(f"[摇一摇] ERROR: 未能定位有效的 MuMuManager.exe (路径={manager_path})，安全终止任务", flush=True)
                shake_game_state["status"] = "FAILED"
                return False
            if vm_index is None:
                print("[摇一摇] ERROR: 未能从 Controller 明确获取当前 VM index，安全终止任务 (禁止猜测默认值)", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            tpls = _get_shake_game_templates()
            tpl_cancel = tpls.get("cancel")
            if tpl_cancel is None:
                print("[摇一摇] ERROR: 缺少结算取消模板 (金海豚_结束取消.png)，安全终止！", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            shake_game_state["status"] = "PLAYING"
            print(f"[摇一摇] 已确认模拟器管理器: {manager_path} (VM={vm_index})，开始摇晃主循环...", flush=True)

            start_time = time.time()
            shake_count = 0
            consecutive_failures = 0
            settlement_detected = False

            while time.time() - start_time < SHAKE_GAME_MAX_DURATION_SECONDS:
                if _task_cancelled(context):
                    print("[摇一摇] 收到任务停止信号，退出摇晃循环", flush=True)
                    shake_game_state["status"] = "FAILED"
                    return False

                # 1. 执行单次 shake RPC 命令
                ok = _run_mumu_shake(manager_path, vm_index, timeout=2.0)
                if ok:
                    shake_count += 1
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    print(f"[摇一摇] shake 执行失败 ({consecutive_failures}/{SHAKE_GAME_MAX_CONSECUTIVE_FAILURES})", flush=True)
                    if consecutive_failures >= SHAKE_GAME_MAX_CONSECUTIVE_FAILURES:
                        print("[摇一摇] ERROR: 连续 3 次 shake RPC 失败，触发安全熔断！", flush=True)
                        shake_game_state["status"] = "FAILED"
                        return False

                time.sleep(SHAKE_GAME_INTERVAL_SECONDS)

                # 2. 采样截屏检测结算弹窗是否出现
                frame = _capture_720p(ctrl)
                if frame is not None:
                    res = cv2.matchTemplate(frame, tpl_cancel, cv2.TM_CCOEFF_NORMED)
                    score = cv2.minMaxLoc(res)[1]
                    if score >= 0.70:
                        print(f"[摇一摇] 检出结算弹窗 (score={score:.3f})，提前结束摇晃 (累计摇晃 {shake_count} 次)", flush=True)
                        settlement_detected = True
                        break

            if settlement_detected:
                shake_game_state["status"] = "SETTLEMENT"
                print(f"[摇一摇] 摇晃阶段完成，耗时 {time.time() - start_time:.1f}s，累计摇晃 {shake_count} 次，进入结算", flush=True)
                return True
            else:
                print(f"[摇一摇] ERROR: 达到最大时长 {SHAKE_GAME_MAX_DURATION_SECONDS}s 且未检出结算弹窗，保留现场安全终止！", flush=True)
                shake_game_state["status"] = "FAILED"
                return False
        except Exception as e:
            traceback.print_exc()
            print(f"[摇一摇] 运行异常: {e}", flush=True)
            shake_game_state["status"] = "FAILED"
            return False


@AgentServer.custom_action("ShakeGameExitAction")
class ShakeGameExitAction(CustomAction):
    """
    摇一摇结算与退出动作:
    只在确认出现结算状态后，识别并点击结算取消按钮，关闭可能的游乐园抽屉，确认返回主鱼缸。
    禁止在超时未检测到结算时盲点固定坐标。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = context.tasker.controller
            if not ctrl:
                print("[摇一摇退出] 错误: 未获取到 Controller", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            tpls = _get_shake_game_templates()
            tpl_cancel = tpls.get("cancel")

            frame = _capture_720p(ctrl)
            if frame is None or tpl_cancel is None:
                print("[摇一摇退出] ERROR: 无法获取截屏或缺少结算模板", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            res = cv2.matchTemplate(frame, tpl_cancel, cv2.TM_CCOEFF_NORMED)
            score, _, loc = cv2.minMaxLoc(res)[1], None, cv2.minMaxLoc(res)[3]
            if score < 0.70:
                print(f"[摇一摇退出] ERROR: 未能确认结算取消按钮 (score={score:.3f} < 0.70)，安全终止以保留现场", flush=True)
                shake_game_state["status"] = "FAILED"
                return False

            cx = loc[0] + tpl_cancel.shape[1] // 2
            cy = loc[1] + tpl_cancel.shape[0] // 2
            print(f"[摇一摇退出] 识别到结算取消按钮 (score={score:.3f})，点击 ({cx}, {cy}) 关闭结算...", flush=True)
            ctrl.post_click(cx, cy).wait()
            time.sleep(1.8)

            # 检查若游乐园抽屉仍在展开状态，点击 (640, 150) 收起
            ctrl.post_click(640, 150).wait()
            time.sleep(1.0)

            status = _complete_shake_game_round()
            completed = shake_game_state["completed_rounds"]
            max_rounds = shake_game_state["max_rounds"]
            if status == "NEXT_ROUND":
                print(
                    f"[摇一摇退出] 第 {completed}/{max_rounds} 局结算退出完成，回到主鱼缸后继续下一局",
                    flush=True,
                )
            else:
                print(f"[摇一摇退出] 第 {completed}/{max_rounds} 局结算退出完成，三局任务完成", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[摇一摇退出] 运行异常: {e}", flush=True)
            shake_game_state["status"] = "FAILED"
            return False


@AgentServer.custom_action("ShakeGameDoneAction")
class ShakeGameDoneAction(CustomAction):
    """
    摇一摇结束节点动作:
    沉淀最终状态，若处于日常收尾流程中，通知日常收尾推进下一个任务。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        st = shake_game_state.get("status", "DONE")
        if st not in ("DONE", "NO_STAMINA", "FAILED"):
            st = "DONE"
            shake_game_state["status"] = "DONE"
        if daily_routine_state.get("active"):
            advance_daily_routine_step("ShakeGame", st)
        print(f"[摇一摇] 流程结束，最终状态: {st}", flush=True)
        return True


# =========================================================================
# 摇一摇收宝石实验任务 (ShakeGemCollectTestTask)
# =========================================================================
SHAKE_GEM_TEST_COUNT = 6
SHAKE_GEM_TEST_INTERVAL_SECONDS = 0.8
SHAKE_GEM_MAX_CONSECUTIVE_FAILURES = 3


@AgentServer.custom_action("ShakeGemCollectAction")
class ShakeGemCollectAction(CustomAction):
    """
    摇一摇收宝石实验动作：
    从 Controller 获取 MuMuManager 及 VM 实例，在主鱼缸连续触发模拟摇晃命令。
    具备任务取消检查与连续失败安全熔断机制。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(argv.custom_action_param)
            count = int(param.get("count", SHAKE_GEM_TEST_COUNT)) if param else SHAKE_GEM_TEST_COUNT
            interval = float(param.get("interval", SHAKE_GEM_TEST_INTERVAL_SECONDS)) if param else SHAKE_GEM_TEST_INTERVAL_SECONDS

            ctrl = getattr(getattr(context, "tasker", None), "controller", None)
            if ctrl is None:
                print("[摇一摇收宝石] 错误: 未获取到 Controller", flush=True)
                return False

            manager_path, vm_index = _get_mumu_manager_and_vm(ctrl)
            if not manager_path or vm_index is None:
                print(
                    "[摇一摇收宝石] ERROR: 无法解析 MuMuManager 路径或 VM index！"
                    "请确认运行在 MuMu 模拟器环境且配置完整。",
                    flush=True,
                )
                return False

            print(
                f"[摇一摇收宝石] 已确认模拟器管理器: {manager_path} (VM={vm_index})，"
                f"开始执行连续 {count} 次摇晃测试 (间隔 {interval}s)...",
                flush=True,
            )

            consecutive_failures = 0
            for i in range(count):
                if _task_cancelled(context):
                    print("[摇一摇收宝石] 收到任务停止信号，安全退出摇晃循环", flush=True)
                    return False

                ok = _run_mumu_shake(manager_path, vm_index, timeout=2.0)
                if ok:
                    consecutive_failures = 0
                    print(f"[摇一摇收宝石] 模拟摇晃 ({i + 1}/{count}) 成功", flush=True)
                else:
                    consecutive_failures += 1
                    print(
                        f"[摇一摇收宝石] 模拟摇晃 ({i + 1}/{count}) 失败 "
                        f"({consecutive_failures}/{SHAKE_GEM_MAX_CONSECUTIVE_FAILURES})",
                        flush=True,
                    )
                    if consecutive_failures >= SHAKE_GEM_MAX_CONSECUTIVE_FAILURES:
                        print("[摇一摇收宝石] ERROR: 连续 3 次 shake RPC 失败，触发安全熔断！", flush=True)
                        return False

                if i < count - 1:
                    time.sleep(interval)

            print("[摇一摇收宝石] 连续摇晃完毕，等待 1.0 秒缓冲使宝石下落...", flush=True)
            time.sleep(1.0)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[摇一摇收宝石] 执行异常: {e}", flush=True)
            return False


@AgentServer.custom_action("ShakeGemCollectDoneAction")
class ShakeGemCollectDoneAction(CustomAction):
    """
    摇一摇收宝石实验任务完成动作：
    输出测试完成日志。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        print("[摇一摇收宝石] 实验流程全部执行完毕（连续摇晃 + 底部滑动收宝）。", flush=True)
        return True


# =========================================================================
# 统一鱼缸收宝石双模式 (IMAGE / SHAKE)
# =========================================================================
GEM_SHAKE_CYCLES = 5
GEM_SHAKE_SETTLE_DELAY_SECONDS = 1.5          # 每次摇晃后等待宝石下落沉降时间 (调参值)
GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS = 1.5    # 全部摇晃完成后，最终补刀扫底前的额外沉降等待时间 (调参值)
GEM_SHAKE_MAX_CONSECUTIVE_FAILURES = 3
GEM_SHAKE_RPC_TIMEOUT_SECONDS = 5.0           # 挂机收宝允许 MuMu 短暂繁忙，比小游戏 2s 更宽
SWEEP_BOTTOM_BEGIN = (221, 663)
SWEEP_BOTTOM_END = (1007, 663)
SWEEP_BOTTOM_DURATION_MS = 250
SWEEP_BOTTOM_POST_DELAY_SECONDS = 0.12


def perform_fish_tank_bottom_sweep(ctrl, post_delay_seconds: float = SWEEP_BOTTOM_POST_DELAY_SECONDS) -> None:
    """在鱼缸底部执行左到右、再右到左的双向往复扫底。"""
    ctrl.post_swipe(
        SWEEP_BOTTOM_BEGIN[0],
        SWEEP_BOTTOM_BEGIN[1],
        SWEEP_BOTTOM_END[0],
        SWEEP_BOTTOM_END[1],
        SWEEP_BOTTOM_DURATION_MS,
    ).wait()
    ctrl.post_swipe(
        SWEEP_BOTTOM_END[0],
        SWEEP_BOTTOM_END[1],
        SWEEP_BOTTOM_BEGIN[0],
        SWEEP_BOTTOM_BEGIN[1],
        SWEEP_BOTTOM_DURATION_MS,
    ).wait()
    if post_delay_seconds > 0:
        time.sleep(post_delay_seconds)


def execute_shake_gem_collect_cycle(
    context: Context,
    ctrl,
    cycles: int = GEM_SHAKE_CYCLES,
    delay_between: float = GEM_SHAKE_SETTLE_DELAY_SECONDS,
    final_delay: float = GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS,
) -> bool:
    """
    统一执行一次鱼缸摇晃收宝循环:
    严格交替模式与充分沉降等待:
    Shake 1 -> Settle 1 -> Sweep 1 -> ... -> Shake N -> Settle N -> Sweep N -> Final Settle -> Final Sweep (补刀)
    连续 3 次 shake 失败时跳过本轮剩余摇晃，仍扫底后返回 True，避免把整次收鱼/巡检挂机判失败。
    检测到任务取消立即退出。
    """
    manager_path, vm_index = _get_mumu_manager_and_vm(ctrl)
    if not manager_path or vm_index is None:
        print(
            "[统一收宝石] ERROR: 无法解析 MuMuManager 路径或 VM index！"
            "请确认运行在 MuMu 模拟器环境且配置完整。",
            flush=True,
        )
        return False

    consecutive_failures = 0
    skipped_remaining_shakes = False
    for i in range(cycles):
        if _task_cancelled(context):
            print("[统一收宝石] 收到任务停止信号，安全退出摇晃循环", flush=True)
            return False

        ok = _run_mumu_shake(
            manager_path, vm_index, timeout=GEM_SHAKE_RPC_TIMEOUT_SECONDS
        )
        if ok:
            consecutive_failures = 0
            print(f"[统一收宝石] Shake/Sweep ({i + 1}/{cycles})：shake 成功", flush=True)
        else:
            consecutive_failures += 1
            print(
                f"[统一收宝石] Shake/Sweep ({i + 1}/{cycles})：shake 失败 "
                f"({consecutive_failures}/{GEM_SHAKE_MAX_CONSECUTIVE_FAILURES})",
                flush=True,
            )
            if consecutive_failures >= GEM_SHAKE_MAX_CONSECUTIVE_FAILURES:
                print(
                    "[统一收宝石] 警告: 连续 3 次 shake RPC 失败，"
                    "跳过本轮剩余摇晃并扫底后继续挂机",
                    flush=True,
                )
                skipped_remaining_shakes = True
                break

        if delay_between > 0:
            print(f"[统一收宝石] Shake/Sweep ({i + 1}/{cycles})：等待宝石下落 {delay_between:.1f}s", flush=True)
            steps = int(delay_between / 0.1)
            remainder = delay_between - steps * 0.1
            cancelled = False
            for _ in range(steps):
                if _task_cancelled(context):
                    print("[统一收宝石] 等待宝石下落期间收到停止信号，安全退出", flush=True)
                    cancelled = True
                    break
                time.sleep(0.1)
            if cancelled:
                return False
            if remainder > 0:
                if _task_cancelled(context):
                    print("[统一收宝石] 等待宝石下落期间收到停止信号，安全退出", flush=True)
                    return False
                time.sleep(remainder)

        if _task_cancelled(context):
            print("[统一收宝石] 收到任务停止信号，终止滑动", flush=True)
            return False

        # 每次摇晃后紧跟一次扫底
        print(f"[统一收宝石] Shake/Sweep ({i + 1}/{cycles})：执行底部扫宝", flush=True)
        perform_fish_tank_bottom_sweep(ctrl)

    # 循环结束后再等待充分沉降，给迟到的掉落物留出收取时间
    if skipped_remaining_shakes:
        print("[统一收宝石] 本轮摇晃提前结束，进入最终沉降等待...", flush=True)
    else:
        print(f"[统一收宝石] {cycles}/{cycles} 摇晃扫底完成，进入最终沉降等待...", flush=True)
    if final_delay > 0:
        print(f"[统一收宝石] 等待最终批次宝石下落 {final_delay:.1f}s", flush=True)
        steps = int(final_delay / 0.1)
        remainder = final_delay - steps * 0.1
        cancelled = False
        for _ in range(steps):
            if _task_cancelled(context):
                print("[统一收宝石] 最终沉降等待期间收到停止信号，终止最终滑动", flush=True)
                cancelled = True
                break
            time.sleep(0.1)
        if cancelled:
            return False
        if remainder > 0:
            if _task_cancelled(context):
                print("[统一收宝石] 最终沉降等待期间收到停止信号，终止最终滑动", flush=True)
                return False
            time.sleep(remainder)

    if _task_cancelled(context):
        print("[统一收宝石] 收到任务停止信号，终止最终滑动", flush=True)
        return False

    print("[统一收宝石] 执行最终底部扫宝 (补刀)", flush=True)
    perform_fish_tank_bottom_sweep(ctrl)
    if skipped_remaining_shakes:
        print(
            "[统一收宝石] 最终扫底完成，本轮摇晃因 RPC 连续失败提前结束，挂机继续",
            flush=True,
        )
    else:
        print(
            f"[统一收宝石] 最终扫底完成，本鱼缸 SHAKE 收宝结束 "
            f"(共 {cycles} 次摇晃 + {cycles + 1} 次扫底)",
            flush=True,
        )
    return True


@AgentServer.custom_action("SetGemCollectModeAction")
class SetGemCollectModeAction(CustomAction):
    """设置收宝石模式: IMAGE 或 SHAKE"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(argv.custom_action_param)
        mode = str(param.get("mode", "IMAGE")).strip().upper()
        if mode not in ("IMAGE", "SHAKE"):
            mode = "IMAGE"
        gem_collect_state["mode"] = mode
        print(f"[收宝石模式] 当前模式设置为: {mode}", flush=True)
        return True


@AgentServer.custom_action("UnifiedShakeGemCollectAction")
class UnifiedShakeGemCollectAction(CustomAction):
    """
    统一摇晃收宝石动作（单缸挂机 / 巡检各缸）:
    执行标准摇晃循环:
    Shake 1 -> Settle 1 -> Sweep 1 -> ... -> Shake N -> Settle N -> Sweep N -> Final Settle -> Final Sweep (补刀)
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = getattr(getattr(context, "tasker", None), "controller", None)
            if ctrl is None:
                print("[统一摇晃收宝] 错误: 未获取到 Controller", flush=True)
                return False

            param = parse_dict_param(argv.custom_action_param)
            cycles = safe_int(param.get("cycles"), GEM_SHAKE_CYCLES)
            delay = safe_float(param.get("delay"), GEM_SHAKE_SETTLE_DELAY_SECONDS)
            final_delay = safe_float(param.get("final_delay"), GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS)

            print(f"[统一摇晃收宝] 开始执行摇晃扫底收宝 (轮数: {cycles}, 沉降: {delay}s, 最终沉降: {final_delay}s)...", flush=True)
            return execute_shake_gem_collect_cycle(
                context, ctrl, cycles=cycles, delay_between=delay, final_delay=final_delay
            )
        except Exception as e:
            traceback.print_exc()
            print(f"[统一摇晃收宝] 异常: {e}", flush=True)
            return False


@AgentServer.custom_action("MobileAdResetStateAction")
class MobileAdResetStateAction(CustomAction):
    """
    手机/模拟器通用看广告任务状态初始化:
    - 重置 completed_cycles = 0;
    - 重置 reward_recorded = False;
    - 记录 max_cycles (默认 3 轮);
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(argv.custom_action_param)
        max_cycles = safe_int(param.get("max_cycles", 3), 3)
        log_tag = str(param.get("log_tag") or "手机看广告")
        mobile_ad_state["completed_cycles"] = 0
        mobile_ad_state["reward_recorded"] = False
        mobile_ad_state["consecutive_close_count"] = 0
        mobile_ad_state["max_cycles"] = max_cycles
        mobile_ad_state["log_tag"] = log_tag
        if max_cycles <= 0:
            print(f"[{log_tag}] 任务初始化：一直运行，直到用户手动停止", flush=True)
        else:
            print(f"[{log_tag}] 任务初始化，目标看广告轮数: {max_cycles} 轮", flush=True)
        return True


@AgentServer.custom_action("MobileAdRecordRewardAction")
class MobileAdRecordRewardAction(CustomAction):
    """
    识别到结算对号时执行，防重幂等:
    1. 幂等防重: 若当前轮已记录 (reward_recorded == True) 则跳过;
    2. 首次记录: completed_cycles += 1, reward_recorded = True;
    3. 可选：OCR 观察背景中的结算进度比例 (如 (1/20), (10/10) 等，仅日志观察);
    4. 打印当前进度与下一步指示
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        max_cycles = mobile_ad_state.get("max_cycles", 3)
        log_tag = mobile_ad_state.get("log_tag", "手机看广告")

        # 1. 可选：OCR 观察背景中的结算进度比例 (如 (1/20), (10/10) 等)
        try:
            ctrl = getattr(getattr(context, "tasker", None), "controller", None)
            if ctrl is not None:
                img_job = ctrl.post_screencap().wait()
                img = img_job.get()
                if img is not None:
                    h, w = img.shape[:2]
                    scale_x = w / 1600.0
                    scale_y = h / 720.0
                    x1 = int(1250 * scale_x)
                    y1 = int(500 * scale_y)
                    x2 = int(1450 * scale_x)
                    y2 = int(650 * scale_y)
                    crop = img[y1:y2, x1:x2]
                    from rapidocr_onnxruntime import RapidOCR
                    ocr = RapidOCR()
                    res, _ = ocr(crop)
                    if res:
                        txt = "".join(r[1] for r in res)
                        m = re.search(r"(\d+/\d+)", txt)
                        if m:
                            print(f"[{log_tag}][观察] 当前页面进度比例: {m.group(1)}", flush=True)
        except Exception:
            pass

        # 2. 幂等检查：同一个结算页被多次检测到，只记录一次
        if mobile_ad_state.get("reward_recorded", False):
            curr = mobile_ad_state.get("completed_cycles", 0)
            if max_cycles <= 0:
                print(f"[{log_tag}] 当前弹窗已计入 (第 {curr} 轮)，忽略重复记录", flush=True)
            else:
                print(f"[{log_tag}] 当前弹窗已计入 (第 {curr}/{max_cycles} 轮)，忽略重复记录", flush=True)
            return True

        mobile_ad_state["completed_cycles"] = mobile_ad_state.get("completed_cycles", 0) + 1
        mobile_ad_state["reward_recorded"] = True
        mobile_ad_state["consecutive_close_count"] = 0
        curr = mobile_ad_state["completed_cycles"]

        if max_cycles <= 0:
            print(f"[{log_tag}] 广告完成进度：已完成第 {curr} 轮（一直运行）", flush=True)
            print(f"[{log_tag}] 准备拉起第 {curr + 1} 轮广告...", flush=True)
        else:
            print(f"[{log_tag}] 广告完成进度: 第 {curr}/{max_cycles} 轮", flush=True)
            if curr >= max_cycles:
                print(f"[{log_tag}] 已达到设定的安全限制轮数 ({max_cycles} 轮)，准备关闭页面", flush=True)
            else:
                print(f"[{log_tag}] 准备拉起第 {curr + 1} 轮广告...", flush=True)

        return True


@AgentServer.custom_action("MobileAdOnAdStartAction")
class MobileAdOnAdStartAction(CustomAction):
    """
    当手机或模拟器确认新广告已启动播放时执行:
    重置 reward_recorded = False，使后续新的最终奖励弹窗能够正常计数。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        mobile_ad_state["reward_recorded"] = False
        mobile_ad_state["consecutive_close_count"] = 0
        log_tag = mobile_ad_state.get("log_tag", "手机看广告")
        print(f"[{log_tag}] 新广告已确认启动播放，重置奖励弹窗记录标记", flush=True)
        return True


@AgentServer.custom_action("SetCollectFishTankModeAction")
class SetCollectFishTankModeAction(CustomAction):
    """
    设置收鱼鱼缸模式: 'single' | 'dual'
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(argv.custom_action_param)
        mode = str(param.get("tank_mode", "single")).lower()
        collect_fish_state["tank_mode"] = mode
        task_id = argv.task_detail.task_id if argv.task_detail else None
        collect_fish_state["task_id"] = task_id
        collect_fish_state["is_inited"] = False
        collect_fish_state["dual_start_time"] = 0.0
        collect_fish_state["last_switch_slot"] = -1
        collect_fish_state["initial_feed_done"] = False
        collect_fish_state["pending_target_tank"] = None
        collect_fish_state["switch_retry_count"] = 0
        collect_fish_state["starfish_entry_retry_count"] = 0
        starfish_timer_state["task_id"] = None
        starfish_timer_state["last_feed_time"] = 0.0
        starfish_timer_state["attempt_in_progress"] = False
        starfish_timer_state["retry_not_before"] = 0.0
        mode_desc = "双鱼缸轮换（1缸与2缸）" if mode == "dual" else "当前单鱼缸"
        print(f"[收鱼产物] 当前鱼缸模式设置为: {mode_desc}", flush=True)
        return True


@AgentServer.custom_action("CollectFishResetStarfishEntryAction")
class CollectFishResetStarfishEntryAction(CustomAction):
    """每轮海星喂食开始时重置入口重试计数。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        collect_fish_state["starfish_entry_retry_count"] = 0
        return True


@AgentServer.custom_action("CollectFishStarfishEntryRetryAction")
class CollectFishStarfishEntryRetryAction(CustomAction):
    """记录入口失败；是否继续由对应 Recognition 决定。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        retries = collect_fish_state.get("starfish_entry_retry_count", 0) + 1
        collect_fish_state["starfish_entry_retry_count"] = retries
        print(f"[收鱼-海星] 进入鱼缸管理未通过验证 ({retries}/3)，重新确认当前鱼缸", flush=True)
        return True


@AgentServer.custom_action("CollectFishStarfishEntryFailedAction")
class CollectFishStarfishEntryFailedAction(CustomAction):
    """海星流程失败后释放计时器，短暂退避并继续收宝主流程。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(getattr(argv, "custom_action_param", None))
        message = str(
            param.get("message")
            or "[收鱼-海星] 无法进入鱼缸管理，本轮跳过海星喂食，继续收宝。"
        )
        starfish_timer_state["attempt_in_progress"] = False
        starfish_timer_state["retry_not_before"] = time.time() + 60.0
        print(message, flush=True)
        return True


@AgentServer.custom_action("SetCollectFishSwitchIntervalAction")
class SetCollectFishSwitchIntervalAction(CustomAction):
    """
    设置双缸轮换切换间隔（秒）
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(argv.custom_action_param)
        interval = safe_float(param.get("switch_interval", 120.0), 120.0)
        collect_fish_state["switch_interval_sec"] = interval
        mins = interval / 60.0
        print(f"[收鱼-双缸] 双缸切换间隔设置为: {interval} 秒 ({mins:.1f} 分钟)", flush=True)
        return True


@AgentServer.custom_action("CollectFishDualStartAction")
class CollectFishDualStartAction(CustomAction):
    """
    双缸模式启动归一完成:
    已验证位于鱼缸 1，正式记录 dual_start_time (monotonic) 为 t0，
    开始双缸轮换主循环。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        collect_fish_state["dual_start_time"] = time.monotonic()
        collect_fish_state["current_tank"] = 1
        collect_fish_state["last_switch_slot"] = 0
        collect_fish_state["is_inited"] = True
        collect_fish_state["switch_retry_count"] = 0
        collect_fish_state["pending_target_tank"] = None
        interval = int(collect_fish_state.get("switch_interval_sec", 120))
        print("=" * 55, flush=True)
        print(f"[收鱼-双缸] 已归一到鱼缸 1，双缸轮换计时开始（间隔 {interval} 秒）。", flush=True)
        print("=" * 55, flush=True)
        return True


@AgentServer.custom_action("CollectFishSingleStartAction")
class CollectFishSingleStartAction(CustomAction):
    """
    单缸模式启动就绪:
    记录当前所在鱼缸并开始主循环。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(argv.custom_action_param)
        tank = safe_int(param.get("tank", 1), 1)
        collect_fish_state["current_tank"] = tank
        collect_fish_state["is_inited"] = True
        collect_fish_state["switch_retry_count"] = 0
        print(f"[收鱼-单缸] 单鱼缸模式就绪，当前位于鱼缸 {tank}，开始收宝", flush=True)
        return True


@AgentServer.custom_action("CollectFishRecordSwitchedTankAction")
class CollectFishRecordSwitchedTankAction(CustomAction):
    """
    切缸成功后记录状态:
    更新 current_tank，重置重试计数，计算最新 slot。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_dict_param(argv.custom_action_param)
        target_tank = safe_int(param.get("target_tank", 1), 1)
        collect_fish_state["current_tank"] = target_tank
        collect_fish_state["switch_retry_count"] = 0
        collect_fish_state["pending_target_tank"] = None

        dual_start = collect_fish_state.get("dual_start_time", 0.0)
        if dual_start > 0:
            now = time.monotonic()
            elapsed = max(0.0, now - dual_start)
            interval = max(10.0, float(collect_fish_state.get("switch_interval_sec", 120.0)))
            slot = int(elapsed // interval)
            collect_fish_state["last_switch_slot"] = slot
        elif collect_fish_state.get("tank_mode") == "dual":
            collect_fish_state["dual_start_time"] = time.monotonic()
            collect_fish_state["last_switch_slot"] = 0
            collect_fish_state["is_inited"] = True

        print(f"[收鱼-双缸] 已从上一鱼缸成功切换并确认进入鱼缸 {target_tank}，继续收宝", flush=True)
        return True


@AgentServer.custom_action("CollectFishSwitchRetryAction")
class CollectFishSwitchRetryAction(CustomAction):
    """
    切缸重试计数器:
    若连续 3 次未能识别到目标鱼缸编号，安全停止任务。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        collect_fish_state["switch_retry_count"] = collect_fish_state.get("switch_retry_count", 0) + 1
        retries = collect_fish_state["switch_retry_count"]
        print(f"[收鱼-双缸] 切缸验证未通过 (第 {retries}/3 次重试)...", flush=True)
        if retries >= 3:
            print("[收鱼-双缸] 错误: 切缸连续 3 次验证失败，触发安全停止！", flush=True)
            return False
        return True


@AgentServer.custom_action("CollectFishAfterStarfishAction")
class CollectFishAfterStarfishAction(CustomAction):
    """
    通用三海星喂食完成返回主鱼缸后执行:
    - 单缸模式: 保持原鱼缸，继续收宝;
    - 双缸模式: 重新依据 monotonic 绝对时间计算 expected_tank。
      若当前鱼缸与 expected_tank 一致，继续收宝;
      若当前鱼缸 != expected_tank (海星喂食耗时跨过了切缸时间窗口)，标记需要切缸。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        collect_fish_state["initial_feed_done"] = True
        collect_fish_state["starfish_entry_retry_count"] = 0
        starfish_timer_state["last_feed_time"] = time.time()
        starfish_timer_state["attempt_in_progress"] = False
        starfish_timer_state["retry_not_before"] = 0.0
        param = parse_dict_param(argv.custom_action_param)
        returned_tank = safe_int(param.get("returned_tank", 1), 1)

        mode = collect_fish_state.get("tank_mode", "single")
        if mode != "dual":
            collect_fish_state["current_tank"] = returned_tank
            print(f"[收鱼-海星] 三只海星处理完成，已返回原鱼缸 {returned_tank}", flush=True)
            return True

        # 双缸模式: 检查当前时间是否已跨越切缸窗口
        dual_start = collect_fish_state.get("dual_start_time", 0.0)
        if dual_start <= 0:
            collect_fish_state["current_tank"] = returned_tank
            return True

        now = time.monotonic()
        elapsed = max(0.0, now - dual_start)
        interval = max(10.0, float(collect_fish_state.get("switch_interval_sec", 120.0)))
        slot = int(elapsed // interval)
        expected_tank = 1 if (slot % 2 == 0) else 2

        collect_fish_state["current_tank"] = returned_tank
        if returned_tank == expected_tank:
            print(f"[收鱼-海星] 三只海星处理完成，已返回鱼缸 {returned_tank} (仍在当前时间窗口内，slot={slot})", flush=True)
        else:
            collect_fish_state["pending_target_tank"] = expected_tank
            print(
                f"[收鱼-双缸] 海星操作跨过切缸边界 (slot={slot}, 已挂机 {int(elapsed)} 秒)，"
                f"当前位于鱼缸 {returned_tank}，需纠正切换至鱼缸 {expected_tank}",
                flush=True,
            )
        return True


@AgentServer.custom_action("DailyMagicPuzzleSolveAction")
class DailyMagicPuzzleSolveAction(CustomAction):
    """读取 MFA 中的图片块位置，完整求解后在已门禁的拼图页执行。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            param = parse_dict_param(getattr(argv, "custom_action_param", None))
            grid_size = safe_int(param.get("grid_size", param.get("board_size")), 4, 1, 99)
            specs = {4: PUZZLE_SPEC_4X4, 5: PUZZLE_SPEC_5X5, 6: PUZZLE_SPEC_6X6}
            spec = specs.get(grid_size)
            if spec is None:
                print(
                    f"[每日魔幻拼图] ERROR: 当前仅支持 4×4、5×5 或 6×6 棋盘，收到 {grid_size}×{grid_size}",
                    flush=True,
                )
                return False
            target_size = safe_int(param.get("target_size"), spec.target_size, 1, 9)
            piece_count = safe_int(param.get("piece_count"), spec.piece_count, 1, 25)
            if target_size != spec.target_size or piece_count != spec.piece_count:
                print("[每日魔幻拼图] ERROR: 拼图规格参数不一致，已停止且未执行 Swipe", flush=True)
                return False
            defaults = {
                4: (1, 2, 5, 6),
                5: (1, 2, 3, 6, 7, 8, 11, 12, 13),
                6: (1, 2, 3, 4, 7, 8, 9, 10, 13, 14, 15, 16, 19, 20, 21, 22),
            }[grid_size]
            raw_positions = tuple(
                param.get(f"piece{piece}", defaults[piece - 1])
                for piece in range(1, piece_count + 1)
            )
            try:
                positions = parse_piece_positions(raw_positions, grid_size, piece_count)
            except PuzzlePositionError as exc:
                print(f"[每日魔幻拼图] ERROR: {exc}", flush=True)
                return False

            print(
                f"[每日魔幻拼图] 拼图规格：{grid_size}×{grid_size} / "
                f"目标图片：{target_size}×{target_size}",
                flush=True,
            )
            print(f"[每日魔幻拼图] 目标块数量：{piece_count}", flush=True)
            print(
                f"[每日魔幻拼图] 图片块位置：{tuple(position + 1 for position in positions)}",
                flush=True,
            )
            try:
                if grid_size == 4:
                    moves = PuzzleSolver().solve(positions)
                    search_stats = None
                elif grid_size == 5:
                    solver_5x5 = Puzzle5x5Solver(
                        max_expanded_states=safe_int(
                            param.get("max_expanded_states"), 300_000, 1_000, 1_000_000
                        ),
                        max_seconds=float(
                            safe_int(param.get("max_search_seconds"), 8, 1, 30)
                        ),
                    )
                    moves = solver_5x5.solve(positions)
                    search_stats = solver_5x5.last_stats
                else:
                    solver_6x6 = Puzzle6x6Solver(
                        max_expanded_states=safe_int(
                            param.get("max_expanded_states"), 400_000, 1_000, 1_000_000
                        ),
                        max_seconds=float(
                            safe_int(param.get("max_search_seconds"), 12, 1, 30)
                        ),
                    )
                    moves = solver_6x6.solve(positions)
                    search_stats = solver_6x6.last_stats
            except PuzzleSearchBudgetExceeded as exc:
                print(
                    f"[每日魔幻拼图] {grid_size}×{grid_size} 求解超过安全搜索预算，"
                    "未执行任何滑动。"
                    f" expanded={exc.stats.expanded_states}, elapsed={exc.stats.elapsed_seconds:.3f}s",
                    flush=True,
                )
                return False

            if search_stats is not None:
                print(
                    f"[每日魔幻拼图] {grid_size}×{grid_size} 求解完成："
                    f"moves={len(moves)}, expanded={search_stats.expanded_states}, "
                    f"time={search_stats.elapsed_seconds:.3f}s",
                    flush=True,
                )
            else:
                print(f"[每日魔幻拼图] 求解完成，共 {len(moves)} 次 Swipe", flush=True)
            if not moves:
                print("[每日魔幻拼图] 当前排布已经完成", flush=True)
                return True

            print("[每日魔幻拼图] 执行计划：", flush=True)
            for step, move in enumerate(moves, 1):
                print(f"[每日魔幻拼图] {step}. {move.to_chinese()}", flush=True)

            controller = getattr(getattr(context, "tasker", None), "controller", None)
            if controller is None:
                print("[每日魔幻拼图] ERROR: 未获取到 MAA Controller", flush=True)
                return False

            duration_ms = safe_int(param.get("duration_ms"), 400, 100, 2000)
            move_delay_ms = safe_int(param.get("move_delay_ms"), 600, 0, 5000)
            geometry = {
                4: PUZZLE_GEOMETRY_4X4,
                5: PUZZLE_GEOMETRY_5X5,
                6: PUZZLE_GEOMETRY_6X6,
            }[grid_size]
            executor = MaaPuzzleExecutor(
                controller, duration_ms=duration_ms, geometry=geometry
            )
            for step, move in enumerate(moves, 1):
                if _task_cancelled(context):
                    print("[每日魔幻拼图] 已收到停止请求，不再继续 Swipe", flush=True)
                    return False
                executor.execute(move)
                print(f"[每日魔幻拼图] {step}. 已执行 {move.to_chinese()}", flush=True)
                if move_delay_ms:
                    time.sleep(move_delay_ms / 1000.0)
            return True
        except Exception as exc:
            print(f"[每日魔幻拼图] ERROR: 求解失败: {exc}", flush=True)
            traceback.print_exc()
            return False
