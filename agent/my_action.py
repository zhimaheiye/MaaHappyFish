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
from maa.context import Context
from maa.pipeline import JActionType, JLongPress

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
    )

try:
    from param_utils import parse_dict_param, safe_float, safe_int
except ImportError:
    from agent.param_utils import parse_dict_param, safe_float, safe_int


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


def _recognition_number(context: Context, node_name: str, frame):
    if frame is None or not hasattr(context, "run_recognition"):
        return None
    result = context.run_recognition(node_name, frame)
    best = getattr(result, "best_result", None) if result and result.hit else None
    text = getattr(best, "text", "").strip()
    # Maa OCR 在这个白底数量框里会把单独的“1”稳定识别成右括号笔画。
    # 该兼容只作用于数量专用 ROI，避免把同形字符扩散到其他 OCR 节点。
    if node_name == "BuyFishFoodQuantity" and text == "」":
        text = "1"
    digits = "".join(char for char in text if char.isdigit())
    return int(digits) if digits else None


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
            if any(_recognition_box(context, node, frame) is None for node in required_nodes):
                print("[购买鱼食] 廉价鱼食详情页门禁不完整，未执行购买", flush=True)
                return False

            current_quantity = _recognition_number(context, "BuyFishFoodQuantity", frame)
            if current_quantity is None or current_quantity < 1 or current_quantity > bags:
                print("[购买鱼食] 当前购买数量无法安全确认，未执行购买", flush=True)
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
            min_clicks = safe_int(param.get("min_clicks"), 30, 30, 120)
            max_clicks = safe_int(param.get("max_clicks"), 120, min_clicks, 300)
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

                if click_count >= min_clicks and _recognition_box(
                    context, "ManateeExhausted", frame
                ) is not None:
                    manatee_state["last_feed_count"] = click_count
                    print(
                        f"[海牛先生] 已投喂 {click_count} 次并识别到刷新体力，喂食完成",
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
                time.sleep(0.1)

            print(
                f"[海牛先生] 已达到 {max_clicks} 次安全上限但仍未识别到刷新体力，停止操作",
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
            if not hit and time.perf_counter() - t_start >= early_after_sec:
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
            sea_otter_gem_state["completion_reason"] = None
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
    钓鱼达人结算并安全返回主鱼缸动作:
    1. 判断业务状态: cast_count >= max_casts 判定为 DONE，否则判定为 NO_STAMINA (鱼饵耗尽/购买弹窗关闭);
    2. 若处于 DailyRoutineTask 流程中，同步状态并推进至 BAND_FISH_PASS2;
    3. 当前节点已由钓场业务状态门禁确认，直接点击钓场右上角退出 [1235, 45]；由 Pipeline 再确认主鱼缸。
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

            # 钓场左上角会退回地点地图，继续点击可能再次选中默认的“星河”。
            # 此处按钓场已确认状态直接点击右上角退出，不再跨页面盲点。
            ctrl.post_click(1235, 45).wait()
            time.sleep(1.8)

            print("[钓鱼退出] 已点击钓场右上角退出，正在验证是否返回主鱼缸...", flush=True)
            return True
        except Exception as e:
            traceback.print_exc()
            print(f"[钓鱼退出] 异常: {e}", flush=True)
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

GOLDEN_DOLPHIN_HEART_FALLBACK_DELAY_SECONDS = 1.0

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

    star_templates = tuple(
        template
        for template in (_load_tpl("金海豚_经验星1.png"), _load_tpl("金海豚_经验星2.png"))
        if template is not None and template.size > 0
    )
    return {
        "tpl_dir": tpl_dir,
        "entrance": _load_tpl("游乐园入口.png"),
        "dolphin": _load_tpl("金海豚_图标.png"),
        "confirm": _load_tpl("金海豚_确定按钮.png"),
        "coin": _load_tpl("金海豚_贝币.png"),
        "heart": _load_tpl("金海豚_爱心.png"),
        "stars": star_templates,
        "cancel": _load_tpl("金海豚_结束取消.png"),
    }


def _find_golden_dolphin_coin(frame, template, threshold: float = 0.70):
    """返回模板识别到的贝币中心与置信度；未命中时不猜坐标。"""
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


def _find_golden_dolphin_hearts(frame, template, threshold: float = 0.70):
    """在完整画面识别爱心并合并同一目标周围的重复命中。"""
    if frame is None or template is None or template.size == 0:
        return []
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))
    template_h, template_w = template.shape[:2]
    if template_h > frame.shape[0] or template_w > frame.shape[1]:
        return []

    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= threshold)
    raw = sorted(
        (
            (int(x + template_w // 2), int(y + template_h // 2), float(result[y, x]))
            for y, x in zip(ys, xs)
        ),
        key=lambda candidate: candidate[2],
        reverse=True,
    )
    candidates = []
    for candidate in raw:
        x, y, _ = candidate
        if any(
            abs(x - selected_x) < template_w * 0.65
            and abs(y - selected_y) < template_h * 0.65
            for selected_x, selected_y, _ in candidates
        ):
            continue
        candidates.append(candidate)
    return sorted(candidates, key=lambda candidate: (candidate[1], candidate[2]), reverse=True)


def _select_golden_dolphin_frame_targets(
    frame,
    coin_template,
    star_templates,
    heart_template,
    xp_started: bool,
    xp_quiet_seconds: float,
):
    """每帧优先全屏经验；XP 阶段静默一段时间后用全屏爱心补充。"""
    xp_candidates = _find_golden_dolphin_xp(frame, star_templates)
    if xp_candidates:
        return "xp", xp_candidates[:4]
    if not xp_started:
        coin = _find_golden_dolphin_coin(frame, coin_template)
        if coin is not None:
            return "coin", [coin]
    elif xp_quiet_seconds >= GOLDEN_DOLPHIN_HEART_FALLBACK_DELAY_SECONDS:
        heart_candidates = _find_golden_dolphin_hearts(frame, heart_template)
        if heart_candidates:
            return "heart", heart_candidates[:4]
    return "wait", []


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


@AgentServer.custom_action("GoldenDolphinInitAction")
class GoldenDolphinInitAction(CustomAction):
    """为本次任务重置三局连续执行状态。"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        golden_dolphin_state["status"] = "IDLE"
        golden_dolphin_state["completed_rounds"] = 0
        golden_dolphin_state["max_rounds"] = 3
        print("[金海豚] 任务开始：计划连续执行 3 局；中途无次数则正常结束", flush=True)
        return True


@AgentServer.custom_action("GoldenDolphinPlayGameAction")
class GoldenDolphinPlayGameAction(CustomAction):
    """
    金海豚小游戏拾取动作 (职责 2):
    仅负责游戏画面内的微观交互:
    1. 经验星出现前持续识别并点击贝币
    2. 首次识别到经验星后执行高频批量拾取
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
            tpl_coin = tpls.get("coin")
            tpl_heart = tpls.get("heart")
            tpl_stars = tpls.get("stars", ())
            tpl_cancel = tpls.get("cancel")

            if tpl_coin is None or tpl_coin.size == 0:
                print("[金海豚游戏] ERROR: 缺少金海豚_贝币.png，安全终止任务", flush=True)
                return False
            if len(tpl_stars) < 2:
                print("[金海豚游戏] ERROR: 金海豚_经验星1.png / 经验星2.png 未完整加载，安全终止任务", flush=True)
                return False
            if tpl_heart is None or tpl_heart.size == 0:
                print("[金海豚游戏] ERROR: 缺少金海豚_爱心.png，安全终止任务", flush=True)
                return False

            print(
                "[金海豚游戏] 当前策略：先点贝币；XP 阶段全屏经验优先，连续 1 秒无经验时全屏点爱心补充",
                flush=True,
            )
            t_game_start = time.monotonic()
            game_done = False
            coin_clicks = 0
            xp_clicks = 0
            heart_clicks = 0
            loop_count = 0
            xp_started = False
            last_xp_seen_at = None

            while time.monotonic() - t_game_start < 55.0:
                if _task_cancelled(context):
                    print("[金海豚游戏] 收到停止请求，立即停止经验点击", flush=True)
                    return False
                elapsed = time.monotonic() - t_game_start
                img = _capture_720p(ctrl)
                if img is None:
                    time.sleep(0.02)
                    continue
                loop_count += 1

                # 结算模板只需降频轮询，避免它阻塞每一帧经验检测。
                if elapsed > 20.0 and loop_count % 5 == 0 and tpl_cancel is not None:
                    res_cancel = cv2.matchTemplate(img, tpl_cancel, cv2.TM_CCOEFF_NORMED)
                    _, max_cancel, _, loc_cancel = cv2.minMaxLoc(res_cancel)
                    if max_cancel >= 0.70:
                        print(f"[金海豚游戏] 检测到游戏结束结算弹窗 (score={max_cancel:.3f})，跳出游戏循环", flush=True)
                        game_done = True
                        break

                now = time.monotonic()
                xp_quiet_seconds = (now - last_xp_seen_at) if last_xp_seen_at is not None else 0.0
                phase, candidates = _select_golden_dolphin_frame_targets(
                    img, tpl_coin, tpl_stars, tpl_heart, xp_started, xp_quiet_seconds
                )
                if phase == "xp":
                    last_xp_seen_at = now
                    if not xp_started:
                        xp_started = True
                        print(
                            f"[金海豚游戏] 首次识别到经验星，停止点击贝币并切换为高频经验收集；"
                            f"此前点击贝币 {coin_clicks} 次",
                            flush=True,
                        )
                    for target_x, target_y, _ in candidates:
                        if _task_cancelled(context):
                            print("[金海豚游戏] 收到停止请求，立即停止经验点击", flush=True)
                            return False
                        ctrl.post_click(target_x, target_y)
                        xp_clicks += 1
                    time.sleep(0.01)
                elif phase == "heart":
                    for target_x, target_y, _ in candidates:
                        if _task_cancelled(context):
                            print("[金海豚游戏] 收到停止请求，立即停止爱心点击", flush=True)
                            return False
                        ctrl.post_click(target_x, target_y)
                        heart_clicks += 1
                    if heart_clicks == len(candidates) or heart_clicks % 20 == 0:
                        print(
                            f"[金海豚游戏] 已连续 {xp_quiet_seconds:.1f} 秒未识别到经验，"
                            f"点击爱心补充 (累计 {heart_clicks} 次)",
                            flush=True,
                        )
                    time.sleep(0.01)
                elif phase == "coin":
                    coin_x, coin_y, score = candidates[0]
                    job = ctrl.post_click(coin_x, coin_y)
                    if job:
                        job.wait()
                    coin_clicks += 1
                    if coin_clicks == 1 or coin_clicks % 10 == 0:
                        print(
                            f"[金海豚游戏] 经验星尚未出现，持续点击识别到的贝币 "
                            f"(第 {coin_clicks} 次, score={score:.3f})",
                            flush=True,
                        )
                    time.sleep(0.02)

            duration = time.monotonic() - t_game_start
            average_fps = loop_count / duration if duration > 0 else 0.0
            print(
                f"[金海豚游戏] 小游戏循环完成 (耗时 {duration:.1f}s, 检测 {loop_count} 帧/{average_fps:.1f} FPS, "
                f"点击贝币 {coin_clicks} 次, 点击 XP {xp_clicks} 次, 点击爱心 {heart_clicks} 次, "
                f"XP阶段={xp_started}, 弹窗就绪={game_done})",
                flush=True,
            )
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


@AgentServer.custom_action("InitDailyRoutineAction")
class InitDailyRoutineAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            daily_routine_state["active"] = True
            daily_routine_state["tasks"] = {
                "FreeGift": {"status": "IDLE"},
                "ReindeerFish": {"status": "IDLE"},
                "BandFish": {"status": "IDLE", "stage": "PASS1"},
                "GoldenDolphin": {"status": "IDLE"},
                "ShakeGame": {"status": "IDLE"},
                "Fishing": {"status": "IDLE"},
                "RomanticHouse": {"status": "IDLE"},
            }

            # 1. 优先从 custom_action_param 解析配置 (支持测试与外部传参)
            param = parse_dict_param(argv.custom_action_param)
            has_param = any(k in param for k in ("free_gift", "reindeer_fish", "band_fish", "golden_dolphin", "shake_game", "fishing", "romantic_house"))

            if has_param:
                enable_fg = bool(param.get("free_gift", False))
                enable_rf = bool(param.get("reindeer_fish", False))
                enable_bf = bool(param.get("band_fish", False))
                enable_gd = bool(param.get("golden_dolphin", False))
                enable_sg = bool(param.get("shake_game", False))
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

                enable_fg = _is_node_enabled("DailyRoutineEnableFreeGift")
                enable_rf = _is_node_enabled("DailyRoutineEnableReindeerFish")
                enable_bf = _is_node_enabled("DailyRoutineEnableBandFish")
                enable_gd = _is_node_enabled("DailyRoutineEnableGoldenDolphin")
                enable_sg = _is_node_enabled("DailyRoutineEnableShakeGame")
                enable_fi = _is_node_enabled("DailyRoutineEnableFishing")
                enable_rh = _is_node_enabled("DailyRoutineEnableRomanticHouse")

            # 3. 按固定安全顺序构建待执行队列。
            queue = []
            if enable_bf:
                _reset_band_fish_state()
                queue.append("BAND_FISH_PASS1")
            if enable_fg:
                queue.append("FREE_GIFT")
            if enable_rf:
                queue.append("REINDEER_FISH")
            if enable_gd:
                queue.append("GOLDEN_DOLPHIN")
            if enable_sg:
                queue.append("SHAKE_GAME")
            if enable_fi:
                queue.append("FISHING")
            if enable_rh:
                queue.append("ROMANTIC_HOUSE")
            if enable_bf:
                queue.append("BAND_FISH_PASS2")

            print("=" * 60, flush=True)
            print("[日常收尾] DailyRoutineTask 初始化成功，勾选子任务配置:", flush=True)
            print(f"  - 每日免费礼包 : {'[ON]' if enable_fg else '[OFF]'}", flush=True)
            print(f"  - 驯鹿鱼送收礼 : {'[ON]' if enable_rf else '[OFF]'}", flush=True)
            print(f"  - 乐队鱼演出   : {'[ON]' if enable_bf else '[OFF]'}", flush=True)
            print(f"  - 金海豚小游戏 : {'[ON]' if enable_gd else '[OFF]'}", flush=True)
            print(f"  - 摇一摇小游戏 : {'[ON]' if enable_sg else '[OFF]'}", flush=True)
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
            fg_st = tasks.get("FreeGift", {}).get("status", "SKIPPED")
            rf_st = tasks.get("ReindeerFish", {}).get("status", "SKIPPED")
            bf_st = tasks.get("BandFish", {}).get("status", "SKIPPED")
            gd_st = tasks.get("GoldenDolphin", {}).get("status", "SKIPPED")
            sg_st = tasks.get("ShakeGame", {}).get("status", "SKIPPED")
            fi_st = tasks.get("Fishing", {}).get("status", "SKIPPED")
            rh_st = tasks.get("RomanticHouse", {}).get("status", "SKIPPED")

            print("=" * 60, flush=True)
            print("  【日常收尾 DailyRoutineTask】全部勾选子任务执行完毕！", flush=True)
            print(f"  - 每日免费礼包 (FreeGift)     : {fg_st}", flush=True)
            print(f"  - 驯鹿鱼送收礼 (ReindeerFish) : {rf_st}", flush=True)
            print(f"  - 乐队鱼演出 (BandFish)       : {bf_st}", flush=True)
            print(f"  - 金海豚小游戏 (GoldenDolphin) : {gd_st}", flush=True)
            print(f"  - 摇一摇小游戏 (ShakeGame)     : {sg_st}", flush=True)
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
SWEEP_BOTTOM_BEGIN = (221, 663)
SWEEP_BOTTOM_END = (1007, 663)
SWEEP_BOTTOM_DURATION_MS = 250
SWEEP_BOTTOM_POST_DELAY_SECONDS = 0.12


def perform_fish_tank_bottom_sweep(ctrl, post_delay_seconds: float = SWEEP_BOTTOM_POST_DELAY_SECONDS) -> None:
    """在鱼缸底部执行扫底收宝滑动 (221, 663) -> (1007, 663)，耗时 250ms"""
    ctrl.post_swipe(
        SWEEP_BOTTOM_BEGIN[0],
        SWEEP_BOTTOM_BEGIN[1],
        SWEEP_BOTTOM_END[0],
        SWEEP_BOTTOM_END[1],
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
    连续 3 次 shake 失败触发安全熔断；检测到任务取消立即退出。
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
    for i in range(cycles):
        if _task_cancelled(context):
            print("[统一收宝石] 收到任务停止信号，安全退出摇晃循环", flush=True)
            return False

        ok = _run_mumu_shake(manager_path, vm_index, timeout=2.0)
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
                print("[统一收宝石] ERROR: 连续 3 次 shake RPC 失败，触发安全熔断！", flush=True)
                return False

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
    print(f"[统一收宝石] 最终扫底完成，本鱼缸 SHAKE 收宝结束 (共 {cycles} 次摇晃 + {cycles + 1} 次扫底)", flush=True)
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
    统一摇晃收宝石动作 (单缸挂机 / 巡检各缸 / 好友摸宝):
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


@AgentServer.custom_action("FriendGemShakeAndAdvanceAction")
class FriendGemShakeAndAdvanceAction(CustomAction):
    """
    好友摸宝摇晃动作 (别名/专用包装):
    执行标准摇晃循环，完成后由 Pipeline 流向 FriendGemNextFriend。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            ctrl = getattr(getattr(context, "tasker", None), "controller", None)
            if ctrl is None:
                print("[好友摇晃摸宝] 错误: 未获取到 Controller", flush=True)
                return False

            param = parse_dict_param(argv.custom_action_param)
            cycles = safe_int(param.get("cycles"), GEM_SHAKE_CYCLES)
            delay = safe_float(param.get("delay"), GEM_SHAKE_SETTLE_DELAY_SECONDS)
            final_delay = safe_float(param.get("final_delay"), GEM_SHAKE_FINAL_SETTLE_DELAY_SECONDS)

            print(f"[好友摇晃摸宝] 开始执行摇晃扫底收宝 (轮数: {cycles}, 沉降: {delay}s, 最终沉降: {final_delay}s)...", flush=True)
            return execute_shake_gem_collect_cycle(
                context, ctrl, cycles=cycles, delay_between=delay, final_delay=final_delay
            )
        except Exception as e:
            traceback.print_exc()
            print(f"[好友摇晃摸宝] 异常: {e}", flush=True)
            return False



