import json
try:
    from param_utils import parse_dict_param, safe_float, safe_int
except ImportError:
    from agent.param_utils import parse_dict_param, safe_float, safe_int
import math
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType

try:
    from runtime_state import (
        friend_gem_state,
        fish_baby_state,
        manatee_state,
        sea_otter_gem_state,
        band_fish_state,
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
        wishing_lamp_state,
    )
except ImportError:
    from agent.runtime_state import (
        friend_gem_state,
        fish_baby_state,
        manatee_state,
        sea_otter_gem_state,
        band_fish_state,
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
        wishing_lamp_state,
    )

timer_state = starfish_timer_state

try:
    from fish_baby import PREFERENCES, classify_sky, group_preferences, resolve_preferences
except ImportError:
    from agent.fish_baby import PREFERENCES, classify_sky, group_preferences, resolve_preferences


@AgentServer.custom_recognition("FishBabyHomePageReco")
class FishBabyHomePageReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        return (0, 0, 10, 10) if classify_sky(argv.image) == "HOME" else None


@AgentServer.custom_recognition("FishBabyMainTankSkyReco")
class FishBabyMainTankSkyReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        return (0, 0, 10, 10) if classify_sky(argv.image) == "MAIN_TANK" else None


@AgentServer.custom_recognition("FishBabyHasTargetsReco")
class FishBabyHasTargetsReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        preferences = resolve_preferences(
            fish_baby_state["preferences"],
            fish_baby_state["uniform_preferences"]["play"],
            PREFERENCES,
        )
        groups = group_preferences(preferences)
        return (0, 0, 10, 10) if len(groups["SKIP"]) < 8 else None

patrol_timer_state = {
    "task_id": None,
    "last_cycle_time": 0.0,
    "interval_seconds": 1800.0,
    "last_ui_log_time": 0.0,
    "ui_log_interval": 300.0,
    "wait_focus_visible": False,
    "cycle_in_progress": False,
}

patrol_feature_timer_state = {}


def _show_patrol_wait_status(context: Context, now: float, interval: float) -> None:
    patrol_timer_state["last_cycle_time"] = now
    patrol_timer_state["last_ui_log_time"] = now
    patrol_timer_state["wait_focus_visible"] = True
    wake_time = datetime.fromtimestamp(now + interval).strftime("%H:%M:%S")
    message = (
        f"[巡检] 本轮多鱼缸巡检已完成，正在等待；"
        f"下次主巡检 {wake_time}（约 {int(math.ceil(interval))} 秒后）。"
    )
    print(message, flush=True)
    try:
        context.override_pipeline({
            "PatrolWaitLoop": {
                "focus": {"Node.Action.Succeeded": message}
            }
        })
    except Exception:
        pass

duty_state = {
    "mode": "IDLE",
    "active_start_time": 0.0,
    "idle_start_time": 0.0,
    "idle_interval": 0.0,
    "active_duration": 120.0,
    "is_inited": False,
    "last_ui_log_time": 0.0,      # 上次向 MFA UI 注入 focus 消息的时间戳
    "ui_log_interval": 60.0,      # UI 播报最小间隔（秒）
}

screen_stall_state = {
    "task_id": None,
    "last_sample": None,
    "last_change_time": 0.0,
}

open_shell_loop_state = {
    "task_id": None,
    "completed": 0,
    "target": 1,
}

open_shell_entry_retry_state = {
    "task_id": None,
    "retries": 0,
}


def _make_screen_sample(image: np.ndarray, sample_step: int) -> np.ndarray:
    if image is None or image.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    sample_step = max(1, sample_step)
    sample = image[::sample_step, ::sample_step]
    if sample.ndim == 3:
        sample = sample[..., :3]
    return sample.astype(np.uint8, copy=True)


def _screen_changed(previous: np.ndarray, current: np.ndarray, threshold: float) -> bool:
    if previous.shape != current.shape:
        return True

    difference = np.abs(current.astype(np.int16) - previous.astype(np.int16))
    return float(difference.mean()) > threshold


@AgentServer.custom_recognition("CheckScreenStallReco")
class CheckScreenStallReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global screen_stall_state

        param = parse_dict_param(argv.custom_recognition_param)

        static_seconds = max(5.0, float(param.get("static_seconds", 30)))
        difference_threshold = max(0.0, float(param.get("difference_threshold", 0.5)))
        sample_step = max(1, int(param.get("sample_step", 8)))
        task_id = argv.task_detail.task_id
        now = time.monotonic()
        sample = _make_screen_sample(argv.image, sample_step)

        if screen_stall_state["task_id"] != task_id:
            screen_stall_state = {
                "task_id": task_id,
                "last_sample": sample,
                "last_change_time": now,
            }
            return None

        previous = screen_stall_state["last_sample"]
        if previous is None or _screen_changed(previous, sample, difference_threshold):
            screen_stall_state["last_sample"] = sample
            screen_stall_state["last_change_time"] = now
            return None

        screen_stall_state["last_sample"] = sample
        stalled_for = now - screen_stall_state["last_change_time"]
        if stalled_for < static_seconds:
            return None

        print(
            f"[运行保护] 画面已连续 {int(stalled_for)} 秒无明显变化，正在停止任务。",
            flush=True,
        )
        return (0, 0, 10, 10)

@AgentServer.custom_recognition("CalcFishingFoodReco")
class CalcFishingFoodReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        param = parse_dict_param(argv.custom_recognition_param)

        try:
            capacity = float(param.get("capacity", 100))
            current_duration = float(param.get("current_duration", 120))
            target_hour = int(param.get("target_hour", 8))

            now = datetime.now()
            target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)

            diff_minutes = (target_time - now).total_seconds() / 60.0
            total_hours = diff_minutes / 60.0

            if current_duration <= 0:
                extra_food = 0
                extra_mins = diff_minutes
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮为0，请及时为海星喂食！"
            elif diff_minutes <= current_duration:
                extra_food = 0
                bags = 0
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 存粮充足(可用 {int(current_duration)} 分钟)，无需补充"
            else:
                rate_per_min = capacity / current_duration
                extra_mins = max(0.0, diff_minutes - current_duration)
                extra_food = int(round(extra_mins * rate_per_min + 0.4999))
                bags = math.ceil(extra_food / 30.0)
                ui_msg = f"[鱼食预算] 挂机至 {target_time.strftime('%H:%M')} (共 {total_hours:.1f}h) | 缺口 {int(extra_mins)}分钟 | 需备鱼食: {extra_food}粒 (约 {bags}袋)"

            print("=" * 55, flush=True)
            print("[鱼食预算] 海星挂机鱼食规划结果:", flush=True)
            print(f"[鱼食预算] 当前时间: {now.strftime('%H:%M')} | 计划挂机至: {target_time.strftime('%H:%M')} (共 {total_hours:.1f} 小时)", flush=True)
            print(f"[鱼食预算] 当前存粮可用: {int(current_duration)} 分钟 | 缺口时长: {max(0, int(diff_minutes - current_duration))} 分钟", flush=True)
            print(f"[鱼食预算] 至少需额外准备/购买: {extra_food} 粒 ~= {bags} 袋 (30粒/袋)", flush=True)
            print("=" * 55, flush=True)

            focus_dict = {
                "Node.Action.Succeeded": ui_msg
            }

            try:
                context.override_pipeline({
                    "CollectFishTask": {
                        "focus": focus_dict
                    }
                })
            except Exception:
                pass

        except Exception as e:
            print(f"[鱼食预算] 计算异常: {e}", flush=True)

        return (0, 0, 10, 10)

@AgentServer.custom_recognition("CheckStarfishTimerReco")
class CheckStarfishTimerReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global timer_state

        param = parse_dict_param(argv.custom_recognition_param)
        if "interval" in param:
            timer_state["interval_seconds"] = safe_float(
                param.get("interval"),
                timer_state["interval_seconds"],
            )

        interval = timer_state["interval_seconds"]
        task_id = argv.task_detail.task_id
        is_new_task = timer_state["task_id"] != task_id
        now = time.time()

        if is_new_task:
            timer_state["task_id"] = task_id
            timer_state["last_feed_time"] = 0.0
            timer_state["attempt_in_progress"] = False
            timer_state["retry_not_before"] = 0.0

        if interval <= 0:
            return None

        if timer_state.get("attempt_in_progress", False):
            return None

        if now < timer_state.get("retry_not_before", 0.0):
            return None

        last_feed_time = timer_state.get("last_feed_time", 0.0)
        is_initial_feed = last_feed_time <= 0
        elapsed = now - last_feed_time if last_feed_time > 0 else 0.0

        if is_initial_feed or elapsed >= interval:
            mins = int(interval / 60) if interval >= 60 else int(interval)
            unit = "分钟" if interval >= 60 else "秒"
            print("=" * 55, flush=True)
            if is_initial_feed:
                print("[海星喂食] 首轮喂食尚未完成，正在自动补充鱼食。", flush=True)
            else:
                print(f"[海星喂食] 定时已达! 距上次喂食 {int(elapsed)} 秒 (设定间隔: {int(interval)} 秒)", flush=True)
            print("[海星喂食] 正在触发海星自动补充鱼食...", flush=True)
            print("=" * 55, flush=True)
            timer_state["attempt_in_progress"] = True
            feed_msg = (
                "[海星喂食] 任务已启动，正在先补充一次鱼食..."
                if is_initial_feed
                else f"[海星喂食] 设定间隔({mins}{unit})已到达，正在自动补充鱼食..."
            )
            try:
                context.override_pipeline({
                    "TriggerStarfishFeed": {
                        "focus": {
                            "Node.Action.Succeeded": feed_msg
                        }
                    }
                })
            except Exception:
                pass
            return (0, 0, 10, 10)

        return None


@AgentServer.custom_recognition("CheckCollectFishStarfishEntryRetryReco")
class CheckCollectFishStarfishEntryRetryReco(CustomRecognition):
    """入口失败不足 3 次时允许重新确认当前鱼缸并重试。"""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if collect_fish_state.get("starfish_entry_retry_count", 0) < 3:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckDutyCycleReco")
class CheckDutyCycleReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global duty_state

        param = argv.custom_recognition_param
        if isinstance(param, str) and param:
            try:
                p = json.loads(param)
                if "idle_interval" in p:
                    duty_state["idle_interval"] = float(p["idle_interval"])
                if "active_duration" in p:
                    duty_state["active_duration"] = float(p["active_duration"])
            except Exception:
                pass

        # 双鱼缸轮换模式固定持续实时收宝，跳过 CheckDutyCycle 的休眠占空比
        if collect_fish_state.get("tank_mode") == "dual":
            return None

        idle_interval = duty_state["idle_interval"]
        active_duration = duty_state["active_duration"]

        now_time = time.time()
        now_dt = datetime.now()

        # 首次初始化
        if not duty_state["is_inited"]:
            duty_state["is_inited"] = True
            if idle_interval > 0:
                duty_state["mode"] = "IDLE"
                duty_state["idle_start_time"] = now_time
                duty_state["last_ui_log_time"] = now_time   # 初始播报时间，60 秒内静默
                target_dt = now_dt + timedelta(seconds=idle_interval)
                mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                unit = "分钟" if idle_interval >= 60 else "秒"
                msg = f"[巡检收宝] 待机休眠中（间隔 {mins}{unit}），预计 {target_dt.strftime('%H:%M:%S')} 开启首轮收宝"
                print("-" * 55, flush=True)
                print(f"[巡检收宝] 任务启动, 默认进入【待机休眠】模式 (间隔 {mins} {unit})", flush=True)
                print(f"[巡检收宝] 预计在 {target_dt.strftime('%H:%M:%S')} 开启第一轮收宝巡检", flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                time.sleep(1)
                return (0, 0, 10, 10)
            else:
                duty_state["mode"] = "ACTIVE"
                duty_state["active_start_time"] = now_time
                msg = "[巡检收宝] 模式:【持续实时】，全天候不间断监控鱼缸收宝！"
                print("-" * 55, flush=True)
                print(msg, flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                return (0, 0, 10, 10)

        # 如果是持续实时模式
        if idle_interval <= 0:
            return None

        if duty_state["mode"] == "ACTIVE":
            elapsed_active = now_time - duty_state["active_start_time"]
            if elapsed_active >= active_duration:
                duty_state["mode"] = "IDLE"
                duty_state["idle_start_time"] = now_time
                duty_state["last_ui_log_time"] = now_time
                target_dt = now_dt + timedelta(seconds=idle_interval)
                mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                unit = "分钟" if idle_interval >= 60 else "秒"
                msg = f"[巡检收宝] 本轮收宝完成！进入待机休眠，预计 {target_dt.strftime('%H:%M:%S')} 开始下一轮"
                print("-" * 55, flush=True)
                print(f"[巡检收宝] 本轮 {int(active_duration)} 秒密集收宝完成!", flush=True)
                print(f"[巡检收宝] 进入休眠等待, 预计在 {target_dt.strftime('%H:%M:%S')} 开启下一轮...", flush=True)
                print("-" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                return (0, 0, 10, 10)
            else:
                return None

        elif duty_state["mode"] == "IDLE":
            elapsed_idle = now_time - duty_state["idle_start_time"]
            if elapsed_idle >= idle_interval:
                duty_state["mode"] = "ACTIVE"
                duty_state["active_start_time"] = now_time
                duty_state["last_ui_log_time"] = now_time
                target_dt = now_dt + timedelta(seconds=active_duration)
                msg = f"[巡检收宝] 休眠结束！开始收宝，本轮持续至 {target_dt.strftime('%H:%M:%S')}"
                print("=" * 55, flush=True)
                print(f"[巡检收宝] 休眠结束! 现在开始收宝!", flush=True)
                print(f"[巡检收宝] 本轮密集收宝持续至 {target_dt.strftime('%H:%M:%S')}", flush=True)
                print("=" * 55, flush=True)
                try:
                    context.override_pipeline({
                        "CheckDutyCycle": {
                            "focus": {
                                "Node.Action.Succeeded": msg
                            }
                        }
                    })
                except Exception:
                    pass
                return (0, 0, 10, 10)
            else:
                # 节流：每 ui_log_interval 秒才更新一次 UI 播报，其余时间静默
                since_last_log = now_time - duty_state["last_ui_log_time"]
                if since_last_log >= duty_state["ui_log_interval"]:
                    duty_state["last_ui_log_time"] = now_time
                    remaining = idle_interval - elapsed_idle
                    wake_dt = now_dt + timedelta(seconds=remaining)
                    mins = int(idle_interval / 60) if idle_interval >= 60 else int(idle_interval)
                    unit = "分钟" if idle_interval >= 60 else "秒"
                    msg = f"[巡检收宝] 待机休眠中（间隔 {mins}{unit}），预计 {wake_dt.strftime('%H:%M:%S')} 开始收宝"
                    print(f"[巡检收宝] 休眠中 | 剩余 {int(remaining)} 秒 | 预计 {wake_dt.strftime('%H:%M:%S')} 开始收宝", flush=True)
                    try:
                        context.override_pipeline({
                            "CheckDutyCycle": {
                                "focus": {
                                    "Node.Action.Succeeded": msg
                                }
                            }
                        })
                    except Exception:
                        pass
                else:
                    # 静默期间清空 focus，避免重复播报
                    try:
                        context.override_pipeline({"CheckDutyCycle": {"focus": {}}})
                    except Exception:
                        pass
                time.sleep(2)
                return (0, 0, 10, 10)


@AgentServer.custom_recognition("CheckPatrolTimerReco")
class CheckPatrolTimerReco(CustomRecognition):
    """Wait between completed multi-tank patrol cycles.

    The first patrol cycle is performed by the pipeline before this recognition
    is reached. Therefore a new task initializes the clock and waits; it must
    not immediately start a duplicate cycle.
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global patrol_timer_state

        param = parse_dict_param(argv.custom_recognition_param)
        interval = safe_float(
            param.get("interval"),
            patrol_timer_state["interval_seconds"],
            min_val=1.0,
        )
        patrol_timer_state["interval_seconds"] = interval

        task_id = argv.task_detail.task_id
        now = time.time()
        if patrol_timer_state["task_id"] != task_id:
            patrol_timer_state["task_id"] = task_id
            patrol_timer_state["cycle_in_progress"] = False
            _show_patrol_wait_status(context, now, interval)
            return None

        if patrol_timer_state["cycle_in_progress"]:
            patrol_timer_state["cycle_in_progress"] = False
            _show_patrol_wait_status(context, now, interval)
            return None

        elapsed = now - patrol_timer_state["last_cycle_time"]
        if elapsed < interval:
            if patrol_timer_state["wait_focus_visible"]:
                patrol_timer_state["wait_focus_visible"] = False
                try:
                    context.override_pipeline({"PatrolWaitLoop": {"focus": {}}})
                except Exception:
                    pass
            elif now - patrol_timer_state["last_ui_log_time"] >= patrol_timer_state["ui_log_interval"]:
                remaining = max(0.0, interval - elapsed)
                wake_time = datetime.fromtimestamp(now + remaining).strftime("%H:%M:%S")
                message = (
                    f"[巡检] 正在等待；下次主巡检 {wake_time}"
                    f"（剩余约 {int(math.ceil(remaining))} 秒）。"
                )
                patrol_timer_state["last_ui_log_time"] = now
                patrol_timer_state["wait_focus_visible"] = True
                print(message, flush=True)
                try:
                    context.override_pipeline({
                        "PatrolWaitLoop": {
                            "focus": {"Node.Action.Succeeded": message}
                        }
                    })
                except Exception:
                    pass
            return None

        patrol_timer_state["cycle_in_progress"] = True
        patrol_timer_state["last_ui_log_time"] = now
        patrol_timer_state["wait_focus_visible"] = False
        print(
            "[巡检] 间隔已到，开始新一轮多鱼缸收宝与海星喂食。",
            flush=True,
        )
        try:
            context.override_pipeline({
                "PatrolTimerDue": {
                    "focus": {
                        "Node.Recognition.Succeeded": "[巡检] 间隔已到，开始新一轮巡检。"
                    }
                }
            })
        except Exception:
            pass
        return (0, 0, 10, 10)


@AgentServer.custom_recognition("CheckPatrolFeatureTimerReco")
class CheckPatrolFeatureTimerReco(CustomRecognition):
    """Schedule optional patrol features independently from the main cycle."""

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global patrol_feature_timer_state

        param = parse_dict_param(argv.custom_recognition_param)
        feature = str(param.get("feature", "")).strip()
        if not feature:
            return None

        interval = safe_float(param.get("interval"), 3600.0, min_val=1.0)
        task_id = argv.task_detail.task_id
        now = time.time()
        state = patrol_feature_timer_state.get(feature)

        if state is None or state["task_id"] != task_id:
            patrol_feature_timer_state[feature] = {
                "task_id": task_id,
                "last_run_time": now,
                "interval_seconds": interval,
            }
            return (0, 0, 10, 10)

        state["interval_seconds"] = interval
        if now - state["last_run_time"] < interval:
            return None

        state["last_run_time"] = now
        return (0, 0, 10, 10)


@AgentServer.custom_recognition("CheckOpenShellLoopReco")
class CheckOpenShellLoopReco(CustomRecognition):

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global open_shell_loop_state

        param = parse_dict_param(argv.custom_recognition_param)

        try:
            target_count = max(1, int(param.get("target_count", 1)))
        except (TypeError, ValueError):
            target_count = 1

        task_id = argv.task_detail.task_id
        if open_shell_loop_state["task_id"] != task_id:
            open_shell_loop_state = {
                "task_id": task_id,
                "completed": 0,
                "target": target_count,
            }

        open_shell_loop_state["target"] = target_count
        open_shell_loop_state["completed"] += 1
        completed = open_shell_loop_state["completed"]

        if completed < target_count:
            print(f"[开贝壳] 已完成 {completed}/{target_count} 轮，继续下一轮", flush=True)
            return (0, 0, 10, 10)
        else:
            print(f"[开贝壳] 已完成 {completed}/{target_count} 轮，任务完成", flush=True)
            return None


@AgentServer.custom_recognition("CheckOpenShellEntryRetryReco")
class CheckOpenShellEntryRetryReco(CustomRecognition):
    # 仅统计"点击入口后经 OpenShellEntryRetryOnMainTank 模板确认仍在主鱼缸"的重试；
    # Pipeline 中该门禁必须排在主鱼缸模板门禁之后，未知页面不得进入本计数。

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global open_shell_entry_retry_state

        param = parse_dict_param(argv.custom_recognition_param)

        try:
            max_retries = max(1, int(param.get("max_retries", 15)))
        except (TypeError, ValueError):
            max_retries = 15

        task_id = argv.task_detail.task_id
        if open_shell_entry_retry_state["task_id"] != task_id:
            open_shell_entry_retry_state = {
                "task_id": task_id,
                "retries": 0,
            }

        open_shell_entry_retry_state["retries"] += 1
        retries = open_shell_entry_retry_state["retries"]

        if retries <= max_retries:
            print(
                f"[开贝壳] 入口点击未生效，仍在主鱼缸，准备第 {retries} 次尝试",
                flush=True,
            )
            return (0, 0, 10, 10)

        print(
            f"[开贝壳] 入口重试已达上限 ({max_retries})，仍未能从主鱼缸进入贝壳分类页，安全停止",
            flush=True,
        )
        return None


@AgentServer.custom_recognition("CheckWishingLampContinueReco")
class CheckWishingLampContinueReco(CustomRecognition):
    # LoopRouter 首次到达在第一次点击之前，因此每次评估先 +1 得到"即将点击的序号"，
    # 序号 <= target 时命中继续；点击 target 次后的下一次评估返回 None 流向退出链。
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        global wishing_lamp_state

        param = parse_dict_param(argv.custom_recognition_param)

        try:
            target_count = max(1, int(param.get("target_count", 10)))
        except (TypeError, ValueError):
            target_count = 10

        task_id = argv.task_detail.task_id
        if wishing_lamp_state["task_id"] != task_id:
            wishing_lamp_state = {
                "task_id": task_id,
                "completed": 0,
                "target": target_count,
            }

        wishing_lamp_state["target"] = target_count
        wishing_lamp_state["completed"] += 1
        completed = wishing_lamp_state["completed"]

        if completed <= target_count:
            print(f"[许愿神灯] 准备进行第 {completed}/{target_count} 次许愿", flush=True)
            return (0, 0, 10, 10)
        print(f"[许愿神灯] 已完成 {target_count}/{target_count} 次许愿，开始退出神灯", flush=True)
        return None


@AgentServer.custom_recognition("CheckFriendGemLimitReco")
class CheckFriendGemLimitReco(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        max_att = friend_gem_state.get("max_attempts", 30)
        if friend_gem_state["attempts"] >= max_att:
            print(
                f"[好友摸宝] 【安全兜底】当前好友尝试已达安全上限 "
                f"({friend_gem_state['attempts']}/{max_att})，触发防死锁兜底，准备切换下一位",
                flush=True,
            )
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckFriendGemBubbleMissLimitReco")
class CheckFriendGemBubbleMissLimitReco(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        max_misses = friend_gem_state.get("max_bubble_misses", 12)
        if friend_gem_state.get("bubble_miss_count", 0) >= max_misses:
            print(
                f"[好友摸宝] 当前好友连续 {friend_gem_state.get('bubble_miss_count', 0)} 次未发现气泡，判定水面无可收气泡，切换下一位",
                flush=True,
            )
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckManateeStateReco")
class CheckManateeStateReco(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        param = parse_dict_param(getattr(argv, "custom_recognition_param", None))
        condition = param.get("condition")
        if condition == "weekend":
            matched = datetime.now().weekday() >= 5
        elif condition == "standalone":
            matched = manatee_state.get("return_mode") == "standalone"
        elif condition == "friend_gem":
            matched = manatee_state.get("return_mode") == "friend_gem"
        else:
            matched = False
        return (0, 0, 10, 10) if matched else None



@AgentServer.custom_recognition("CheckFishingCastLimitReco")
class CheckFishingCastLimitReco(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        max_casts = fishing_state.get("max_casts", 0)
        if max_casts > 0 and fishing_state.get("cast_count", 0) >= max_casts:
            print(
                f"[钓鱼达人] 判定已达最大安全甩杆上限 ({fishing_state['cast_count']}/{fishing_state['max_casts']})，安全停止任务",
                flush=True,
            )
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckFishingDailyReselectOrdinaryReco")
class CheckFishingDailyReselectOrdinaryReco(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        if not fishing_state.get("force_ordinary_bait", False):
            return None
        try:
            result = context.run_recognition("FishingBaitAlreadySelected", argv.image)
            if not result or not result.hit:
                return None
            box = tuple(int(value) for value in result.box)
            print("[钓鱼达人] 日常收尾检测到当前已有鱼饵，准备重新选择普通饵食", flush=True)
            return box
        except Exception as e:
            print(f"[钓鱼达人] 日常普通饵食重选门禁异常: {e}", flush=True)
            return None


@AgentServer.custom_recognition("CheckSeaOtterLimitReco")
class CheckSeaOtterLimitReco(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Optional[RectType]:
        if sea_otter_gem_state.get("normal_completion"):
            completion_reason = sea_otter_gem_state.get("completion_reason")
            print(f"[海獭摸宝] 已到达好友边界，任务正常完成 ({completion_reason})", flush=True)
            return (0, 0, 10, 10)

        cur = sea_otter_gem_state.get("total_harvests", 0)
        limit = sea_otter_gem_state.get("max_harvests", 1000)
        if cur >= limit:
            sea_otter_gem_state["completion_reason"] = "SAFETY_MAX_HARVESTS"
            print(f"[海獭摸宝] 达到摸宝上限安全保护 ({cur}/{limit})，任务安全停止 (Safety Limit Triggered)", flush=True)
            return (0, 0, 10, 10)

        consec = sea_otter_gem_state.get("consecutive_exhausted", 0)
        max_consec = sea_otter_gem_state.get("max_consecutive_exhausted", 30)
        if consec >= max_consec:
            sea_otter_gem_state["completion_reason"] = "SAFETY_CONSECUTIVE_EXHAUSTED"
            print(f"[海獭摸宝] 连续检测到 {consec} 位好友体力耗尽，达到防死循环上限，任务安全停止 (Safety Limit Triggered)", flush=True)
            return (0, 0, 10, 10)

        return None


@AgentServer.custom_recognition("CheckBandFishReadyReco")
class CheckBandFishReadyReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if band_fish_state.get("status") == "READY_TO_PERFORM":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishNeedSlot1Reco")
class CheckBandFishNeedSlot1Reco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if band_fish_state.get("slots", {}).get(1, {}).get("state") == "EMPTY":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishNeedSlot2Reco")
class CheckBandFishNeedSlot2Reco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if band_fish_state.get("slots", {}).get(2, {}).get("state") == "EMPTY":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishNeedSlot4Reco")
class CheckBandFishNeedSlot4Reco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if band_fish_state.get("slots", {}).get(4, {}).get("state") == "EMPTY":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishNeedSlot5Reco")
class CheckBandFishNeedSlot5Reco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if band_fish_state.get("slots", {}).get(5, {}).get("state") == "EMPTY":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishNeedRefreshReco")
class CheckBandFishNeedRefreshReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        slots = band_fish_state.get("slots", {})
        has_empty = any(slots.get(s, {}).get("state") == "EMPTY" for s in (1, 2, 4, 5))
        all_accepted = all(slots.get(s, {}).get("state") == "ACCEPTED" for s in (1, 2, 4, 5))
        if not has_empty and not all_accepted:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckDailyRoutineActiveReco")
class CheckDailyRoutineActiveReco(CustomRecognition):
    """
    检查当前是否处于日常收尾总控任务容器 (DailyRoutineTask) 中。
    active == True 返回 (0, 0, 10, 10)，否则返回 None。
    职责仅限于判断当前是否属于日常收尾容器，不负责具体的 step 分发。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if daily_routine_state.get("active"):
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckGreenWildDailyPendingReco")
class CheckGreenWildDailyPendingReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not daily_routine_state.get("active"):
            return None
        if daily_routine_state.get("step") != "GREEN_WILD_DAILY":
            return None
        if green_wild_daily_state.get("pending_buy_fish"):
            return (0, 0, 10, 10)
        return None


def _hangup_now(param):
    raw = param.get("now")
    if raw:
        try:
            return datetime.fromisoformat(str(raw))
        except Exception:
            pass
    return datetime.now()


@AgentServer.custom_recognition("CheckHangupNoonDailyDueReco")
class CheckHangupNoonDailyDueReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(getattr(argv, "custom_recognition_param", None))
        if not bool(param.get("enabled", False)):
            return None
        if daily_routine_state.get("active"):
            return None
        now = _hangup_now(param)
        if now.hour < 12:
            return None
        today = now.date().isoformat()
        if hangup_schedule_state.get("noon_daily_last_date") == today:
            return None
        return (0, 0, 10, 10)


@AgentServer.custom_recognition("CheckHangupFriendGemDueReco")
class CheckHangupFriendGemDueReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(getattr(argv, "custom_recognition_param", None))
        if not bool(param.get("enabled", False)):
            return None
        if daily_routine_state.get("active"):
            return None
        now = _hangup_now(param)
        today = now.date().isoformat()
        hour = now.hour
        if 10 <= hour < 12 and hangup_schedule_state.get("friend_gem_morning_date") != today:
            return (0, 0, 10, 10)
        if hour >= 22 and hangup_schedule_state.get("friend_gem_evening_date") != today:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckHangupResumeReco")
class CheckHangupResumeReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(getattr(argv, "custom_recognition_param", None))
        target = param.get("target")
        stack = hangup_schedule_state.get("resume_stack") or []
        if target and stack and stack[-1] == target:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckDailyRoutineStepReco")
class CheckDailyRoutineStepReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not daily_routine_state.get("active"):
            return None
        param = parse_dict_param(argv.custom_recognition_param)
        expected = param.get("expected_step")
        if daily_routine_state.get("step") == expected:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishPass2NeededReco")
class CheckBandFishPass2NeededReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not daily_routine_state.get("active"):
            return None
        bf_status = daily_routine_state.get("tasks", {}).get("BandFish", {}).get("status")
        if bf_status == "PENDING":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishPass2SkipReco")
class CheckBandFishPass2SkipReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not daily_routine_state.get("active"):
            return None
        bf_status = daily_routine_state.get("tasks", {}).get("BandFish", {}).get("status")
        if bf_status != "PENDING":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishDailyRoutineReco")
class CheckBandFishDailyRoutineReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if daily_routine_state.get("active"):
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishStandalonePendingReco")
class CheckBandFishStandalonePendingReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not daily_routine_state.get("active") and band_fish_state.get("status") == "PENDING":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckBandFishStandaloneDoneReco")
class CheckBandFishStandaloneDoneReco(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not daily_routine_state.get("active") and (
            band_fish_state.get("status") == "DONE"
            or band_fish_state.get("performance_finished", False)
        ):
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckGoldenDolphinCanPlayReco")
class CheckGoldenDolphinCanPlayReco(CustomRecognition):
    """
    检查金海豚是否进入小游戏:
    若导航阶段判定可进入游戏 (READY_TO_PLAY)，返回匹配区域执行游戏动作；
    若机会已用完 (NO_STAMINA) 或导航异常，返回 None 跳过游戏动作直接流向 Done。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if golden_dolphin_state.get("status") == "READY_TO_PLAY":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckGoldenDolphinRepeatReco")
class CheckGoldenDolphinRepeatReco(CustomRecognition):
    """一局结算后仍未达到三局时，重新进入导航。"""
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if golden_dolphin_state.get("status") == "NEXT_ROUND":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckShakeGameCanPlayReco")
class CheckShakeGameCanPlayReco(CustomRecognition):
    """
    检查摇一摇小游戏是否进入小游戏:
    若导航阶段判定可进入游戏 (READY_TO_PLAY)，返回匹配区域执行游戏动作；
    若机会已用完 (NO_STAMINA) 或导航异常，返回 None 跳过游戏动作直接流向 Done。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if shake_game_state.get("status") == "READY_TO_PLAY":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckShakeGameRepeatReco")
class CheckShakeGameRepeatReco(CustomRecognition):
    """
    检查摇一摇是否需要继续下一局:
    若状态为 NEXT_ROUND，返回区域触发 Repeat 重新导航；
    否则返回 None 流向 Done。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if shake_game_state.get("status") == "NEXT_ROUND":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckGemCollectModeReco")
class CheckGemCollectModeReco(CustomRecognition):
    """
    检查当前收宝石模式:
    若当前模式为 SHAKE，返回匹配区域执行摇晃收宝流水线；
    若当前模式为 IMAGE（默认），返回 None，使流水线跌入原有的图像识别收宝。
    支持 custom_recognition_param: {"mode": "SHAKE"} 直接覆盖，默认读取 gem_collect_state。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(getattr(argv, "custom_recognition_param", None))
        mode = param.get("mode") if param and "mode" in param else gem_collect_state.get("mode", "IMAGE")
        if str(mode).strip().upper() == "SHAKE":
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("MobileAdCheckCycleLimitReco")
class MobileAdCheckCycleLimitReco(CustomRecognition):
    """
    检查看广告任务是否已达到目标轮数 (max_cycles):
    - 若已达到 (completed_cycles >= max_cycles)，返回 (0, 0, 10, 10)，命中该节点走向关闭弹窗;
    - 若未达到，返回 None，让流水线顺位评估下一个候选节点 MobileAdClickContinueCheck (点击绿色对号)。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(getattr(argv, "custom_recognition_param", None))
        max_cycles = safe_int(param.get("max_cycles", mobile_ad_state.get("max_cycles", 3)), 3)
        curr = mobile_ad_state.get("completed_cycles", 0)

        if max_cycles <= 0:
            return None

        if curr >= max_cycles:
            return (0, 0, 10, 10)

        return None


@AgentServer.custom_recognition("CheckGoldShellPageReco")
class CheckGoldShellPageReco(CustomRecognition):
    """
    金贝壳主页专属门禁：
    1. 正向门禁：必须命中 `金贝壳_识别.png`（ROI [515,360,232,195]）；
    2. 负向门禁：贝壳分类页小章鱼、分类页“进入”、主鱼缸特征命中时一律拒绝；
    3. 仅有左上角返回按钮不能当作金贝壳主页，避免海星宠物页等误判。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        try:
            gold_res = context.run_recognition("GoldShellCouponGoldPageIdentity", argv.image)
            if not gold_res or not gold_res.hit:
                return None

            cat_res = context.run_recognition("GoldShellCouponVerifyCategoryPage", argv.image)
            if cat_res and cat_res.hit:
                return None

            enter_res = context.run_recognition("GoldShellCouponEnterGold", argv.image)
            if enter_res and enter_res.hit:
                return None

            tank_res = context.run_recognition("GoldShellCouponVerifyTankInternal", argv.image)
            if tank_res and tank_res.hit:
                return None

            box = tuple(int(v) for v in gold_res.box) if gold_res.box else (515, 360, 232, 195)
            return box
        except Exception as e:
            print(f"[兑换金贝壳券] 金贝壳主页专属门禁识别异常: {e}", flush=True)
            return None


@AgentServer.custom_recognition("CheckExchangeDisappearedReco")
class CheckExchangeDisappearedReco(CustomRecognition):
    """
    检查金贝壳兑换按钮是否已经消失 (方案 A 状态验证):
    检查 ROI [1136, 41, 91, 35] 是否还存在 '兑换/兌換'。
    - 若仍检测到兑换按钮，说明状态未变，返回 None；
    - 若未检测到兑换按钮，说明状态已变（兑换成功/已领走），返回 (0, 0, 10, 10)。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        try:
            res = context.run_recognition("GoldShellCouponCheckExchange", argv.image)
            if res and res.hit:
                # 兑换按钮依然存在，未消失
                return None
            # 兑换按钮已消失，验证通过
            return (0, 0, 10, 10)
        except Exception as e:
            print(f"[兑换金贝壳券] 检查兑换按钮消失状态异常: {e}", flush=True)
            return None


@AgentServer.custom_recognition("CheckCollectFishTankSwitchReco")
class CheckCollectFishTankSwitchReco(CustomRecognition):
    """
    检查是否到达双缸轮换切缸时间窗口:
    仅在 tank_mode == "dual" 且已初始化启动时生效。
    基于 monotonic 绝对时钟计算当前时间窗口 slot:
    slot = int((now - dual_start_time) // switch_interval_sec)
    expected_tank = 1 if (slot % 2 == 0) else 2
    若当前所在鱼缸 current_tank != expected_tank，则返回 (0, 0, 10, 10) 触发切缸。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if collect_fish_state.get("tank_mode") != "dual":
            return None

        if not collect_fish_state.get("is_inited"):
            return None

        dual_start = collect_fish_state.get("dual_start_time", 0.0)
        if dual_start <= 0:
            return None

        now = time.monotonic()
        elapsed = max(0.0, now - dual_start)
        interval = max(10.0, float(collect_fish_state.get("switch_interval_sec", 120.0)))
        slot = int(elapsed // interval)
        expected_tank = 1 if (slot % 2 == 0) else 2

        current_tank = collect_fish_state.get("current_tank", 1)
        if current_tank == expected_tank:
            return None

        # 需要切缸
        collect_fish_state["pending_target_tank"] = expected_tank
        print("-" * 55, flush=True)
        print(
            f"[收鱼-双缸] 时间窗口变更 (slot={slot}, 已挂机 {int(elapsed)} 秒)，"
            f"当前位于鱼缸 {current_tank}，准备切换至目标鱼缸 {expected_tank}...",
            flush=True,
        )
        print("-" * 55, flush=True)
        return (0, 0, 10, 10)


@AgentServer.custom_recognition("CheckCollectFishTargetTankReco")
class CheckCollectFishTargetTankReco(CustomRecognition):
    """
    在切缸路由中判断目标鱼缸:
    参数 {"target_tank": 1 | 2}
    当 pending_target_tank 或 expected_tank 等于 target_tank 时返回 (0, 0, 10, 10)。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(argv.custom_recognition_param)
        target_tank = safe_int(param.get("target_tank", 1), 1)

        pending = collect_fish_state.get("pending_target_tank")
        if pending is None:
            dual_start = collect_fish_state.get("dual_start_time", 0.0)
            if dual_start > 0:
                now = time.monotonic()
                elapsed = max(0.0, now - dual_start)
                interval = max(10.0, float(collect_fish_state.get("switch_interval_sec", 120.0)))
                slot = int(elapsed // interval)
                pending = 1 if (slot % 2 == 0) else 2
            else:
                pending = 1

        if pending == target_tank:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckCollectFishTankModeReco")
class CheckCollectFishTankModeReco(CustomRecognition):
    """
    判断当前收鱼模式是否为指定模式:
    参数 {"mode": "single" | "dual"}
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        param = parse_dict_param(argv.custom_recognition_param)
        expected_mode = str(param.get("mode", "single")).lower()
        current_mode = str(collect_fish_state.get("tank_mode", "single")).lower()
        if current_mode == expected_mode:
            return (0, 0, 10, 10)
        return None


@AgentServer.custom_recognition("CheckCollectFishNeedsInitReco")
class CheckCollectFishNeedsInitReco(CustomRecognition):
    """
    检查收鱼产物任务是否尚未完成启动初始化:
    纯读识别器，判断 collect_fish_state["is_inited"] 是否为 False。
    - 若尚未初始化 (False)，返回 (0, 0, 10, 10) 导向初始化流程；
    - 若已完成初始化 (True)，返回 None 直通继续收宝 (ResumeHarvest)。
    """
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg) -> Optional[RectType]:
        if not collect_fish_state.get("is_inited", False):
            return (0, 0, 10, 10)
        return None
